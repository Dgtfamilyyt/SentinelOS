import os
import shutil
import subprocess
import time
from threading import Lock
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OllamaRuntimeError(RuntimeError):
    """Raised when Sentinel cannot reach or start Ollama."""


class OllamaRuntime:
    """Checks Ollama readiness and starts a local server on demand."""

    LOCAL_HOSTS = {
        "127.0.0.1",
        "localhost",
        "::1",
    }

    def __init__(
        self,
        base_url=None,
        executable=None,
        startup_timeout=20.0,
        poll_interval=0.25,
    ):
        configured_url = (
            base_url
            or os.getenv(
                "OLLAMA_HOST",
                "http://127.0.0.1:11434"
            )
        )

        if "://" not in configured_url:
            configured_url = f"http://{configured_url}"
            parsed = urlparse(configured_url)
            if parsed.port is None:
                configured_url = configured_url.rstrip("/") + ":11434"

        self.base_url = configured_url.rstrip("/")
        self.executable = executable
        self.startup_timeout = startup_timeout
        self.poll_interval = poll_interval
        self._start_lock = Lock()
        self._managed_process = None

    def is_ready(self):
        request = Request(
            f"{self.base_url}/api/tags",
            headers={"User-Agent": "SentinelOS"},
        )

        try:
            with urlopen(request, timeout=0.75) as response:
                return 200 <= response.status < 300

        except (OSError, URLError, ValueError):
            return False

    def ensure_running(self):
        """Return True when this call started Ollama."""

        if self.is_ready():
            return False

        with self._start_lock:
            if self.is_ready():
                return False

            hostname = urlparse(
                self.base_url
            ).hostname

            if hostname not in self.LOCAL_HOSTS:
                raise OllamaRuntimeError(
                    "Configured Ollama host is unavailable. "
                    "Automatic startup is limited to localhost."
                )

            executable = (
                self.executable
                or shutil.which("ollama")
            )

            if not executable:
                raise OllamaRuntimeError(
                    "Ollama executable was not found. "
                    "Install Ollama or add it to PATH."
                )

            creation_flags = 0

            if os.name == "nt":
                creation_flags = (
                    subprocess.CREATE_NO_WINDOW
                )

            try:
                process = subprocess.Popen(
                    [executable, "serve"],
                    env={**os.environ, "OLLAMA_HOST": self.base_url},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    creationflags=creation_flags,
                )

            except OSError as error:
                raise OllamaRuntimeError(
                    "Sentinel could not start Ollama."
                ) from error

            self._managed_process = process
            deadline = (
                time.monotonic()
                + self.startup_timeout
            )

            while time.monotonic() < deadline:
                if self.is_ready():
                    return True

                if process.poll() is not None:
                    raise OllamaRuntimeError(
                        "Ollama stopped before becoming ready."
                    )

                time.sleep(self.poll_interval)

            if process.poll() is None:
                process.terminate()

            raise OllamaRuntimeError(
                "Ollama did not become ready before timeout."
            )


_runtime = None
_runtime_lock = Lock()


def get_ollama_runtime():
    global _runtime

    with _runtime_lock:
        if _runtime is None:
            _runtime = OllamaRuntime()

        return _runtime
