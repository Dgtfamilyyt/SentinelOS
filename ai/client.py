"""ai/client.py – optional Ollama integration

The AI client is used by the planning components when a language model backend is
available.  In the core test suite (e.g. GoalUnderstandingEngine) the client is
instantiated only when an LLM is required.  Importing this module should never
raise an exception even if the optional ``ollama`` package is missing, because
the rest of SentinelOS (including the test suite) does not depend on it.

We therefore wrap the import in a ``try/except`` block and provide a minimal
fallback ``chat`` function that raises a clear ``NotImplementedError``.  This
behaviour matches the original contract – attempts to generate content without
the real backend will surface an explicit error rather than an ``ImportError``
during module import.
"""

try:
    # The real Ollama client provides the ``chat`` function.
    from ollama import chat  # type: ignore
except Exception:  # pragma: no cover – only exercised when Ollama is absent.
    def chat(*, model: str, messages: list[dict[str, str]]) -> dict:
        """Fallback stub for the Ollama ``chat`` API.

        The function signature matches the real implementation but immediately
        raises ``NotImplementedError``.  This is sufficient for unit tests that
        never invoke the LLM path, while providing a helpful error message for
        developers who attempt to use the client without installing the optional
        dependency.
        """
        raise NotImplementedError(
            "Ollama client is not installed. Install the 'ollama' package "
            "or provide a custom runtime when constructing AIClient."
        )

from ai.ollama_runtime import get_ollama_runtime


class AIClient:
    """Thin wrapper around an Ollama runtime.

    The ``runtime`` argument is optional; when omitted we obtain a runtime via
    ``get_ollama_runtime``.  The runtime is responsible for ensuring the Ollama
    server process is running.  The ``generate`` method forwards the request to
    the ``chat`` function imported above.
    """

    def __init__(self, runtime=None):
        self.runtime = runtime if runtime is not None else get_ollama_runtime()

    def generate(self, model, messages):
        """Generate a response from the configured model.

        If the fallback ``chat`` stub is in use, a ``NotImplementedError`` will be
        raised, making the missing dependency obvious at call time rather than
        during import.
        """
        self.runtime.ensure_running()
        response = chat(model=model, messages=messages)
        return response["message"]["content"]
