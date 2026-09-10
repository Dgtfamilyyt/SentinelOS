from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from ai.client import AIClient
from ai.ollama_runtime import (
    OllamaRuntime,
    OllamaRuntimeError,
)
from api.app import create_app


class FakeAI:

    def __init__(self):
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1


class FakeTools:

    def names(self):
        return [
            "read_file",
            "current_directory",
        ]


class FakeCommandCenter:

    def __init__(self):
        self.ai = FakeAI()
        self.tools = FakeTools()
        self.prompts = []
        self.result = "Systems nominal."

    def process(self, prompt):
        self.prompts.append(prompt)

        if isinstance(self.result, Exception):
            raise self.result

        return self.result


class FakeOllamaRuntime:

    def __init__(self, ready=True):
        self.ready = ready
        self.ensure_calls = 0

    def is_ready(self):
        return self.ready

    def ensure_running(self):
        self.ensure_calls += 1
        self.ready = True
        return True


def build_client():
    center = FakeCommandCenter()
    ollama_runtime = FakeOllamaRuntime()
    app = create_app(
        center,
        ollama_runtime=ollama_runtime
    )

    return (
        center,
        ollama_runtime,
        TestClient(app)
    )


def test_interface_is_served():
    _, _, client = build_client()

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Sentinel OS" in response.text
    assert "/static/styles.css" in response.text
    assert "/static/app.js" in response.text


def test_health_reports_discovered_tools():
    _, _, client = build_client()

    with client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "name": "Sentinel OS",
        "version": "0.1.0",
        "tools": [
            "current_directory",
            "read_file",
        ],
        "ollama": "online",
        "automatic_start": True,
    }


def test_chat_uses_command_center():
    center, _, client = build_client()

    with client:
        response = client.post(
            "/api/chat",
            json={"message": "  hello Sentinel  "},
        )

    assert response.status_code == 200
    assert center.prompts == ["hello Sentinel"]
    assert response.json() == {
        "reply": "Systems nominal.",
        "kind": "assistant",
        "details": None,
    }


def test_tool_result_is_normalized():
    center, _, client = build_client()
    center.result = {
        "success": True,
        "tool": "current_directory",
        "result": "C:\\SentinelOS\\workspace",
    }

    with client:
        response = client.post(
            "/api/chat",
            json={"message": "current directory"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "tool"
    assert response.json()["details"] == center.result
    assert response.json()["reply"] == (
        "C:\\SentinelOS\\workspace"
    )


def test_empty_chat_message_is_rejected():
    _, _, client = build_client()

    with client:
        response = client.post(
            "/api/chat",
            json={"message": "   "},
        )

    assert response.status_code == 422


def test_processing_failure_returns_safe_error():
    center, _, client = build_client()
    center.result = RuntimeError(
        "private implementation detail"
    )

    with client:
        response = client.post(
            "/api/chat",
            json={"message": "hello"},
        )

    assert response.status_code == 503
    assert "private implementation detail" not in (
        response.text
    )


def test_clear_session_uses_ai_engine_clear():
    center, _, client = build_client()

    with client:
        response = client.delete("/api/session")

    assert response.status_code == 200
    assert response.json() == {"cleared": True}
    assert center.ai.clear_calls == 1


def test_health_reports_ollama_standby():
    center = FakeCommandCenter()
    runtime = FakeOllamaRuntime(ready=False)
    app = create_app(
        center,
        ollama_runtime=runtime
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ollama"] == "standby"


def test_ai_client_starts_ollama_before_generation(
    monkeypatch
):
    runtime = FakeOllamaRuntime(ready=False)
    monkeypatch.setattr(
        "ai.client.chat",
        lambda **kwargs: {
            "message": {"content": "Online"}
        },
    )
    client = AIClient(runtime=runtime)

    answer = client.generate(
        "test-model",
        [{"role": "user", "content": "hello"}],
    )

    assert answer == "Online"
    assert runtime.ensure_calls == 1


def test_ollama_runtime_does_not_restart_ready_server(
    monkeypatch
):
    runtime = OllamaRuntime()
    monkeypatch.setattr(
        runtime,
        "is_ready",
        lambda: True
    )
    popen = Mock()
    monkeypatch.setattr(
        "ai.ollama_runtime.subprocess.Popen",
        popen,
    )

    assert runtime.ensure_running() is False
    popen.assert_not_called()


def test_ollama_runtime_starts_local_server(
    monkeypatch
):
    runtime = OllamaRuntime(
        executable="ollama",
        startup_timeout=1,
        poll_interval=0,
    )
    readiness = iter([False, False, True])
    monkeypatch.setattr(
        runtime,
        "is_ready",
        lambda: next(readiness)
    )
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    monkeypatch.setattr(
        "ai.ollama_runtime.subprocess.Popen",
        popen,
    )
    monkeypatch.setattr(
        "ai.ollama_runtime.time.sleep",
        lambda _: None,
    )

    assert runtime.ensure_running() is True
    popen.assert_called_once()
    assert popen.call_args.args[0] == [
        "ollama",
        "serve",
    ]


def test_ollama_runtime_will_not_start_for_remote_host(
    monkeypatch
):
    runtime = OllamaRuntime(
        base_url="http://model-host:11434"
    )
    monkeypatch.setattr(
        runtime,
        "is_ready",
        lambda: False
    )

    with pytest.raises(
        OllamaRuntimeError,
        match="limited to localhost"
    ):
        runtime.ensure_running()
