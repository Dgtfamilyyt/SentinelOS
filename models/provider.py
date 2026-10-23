"""
models/provider.py
==================
Modular model provider integration layer for SentinelOS.

Supports:
  - Checking runtime availability (available, unavailable, not_configured)
  - Discovering installed models (real inventory from runtime)
  - Selecting and querying model status
  - Executing chat requests and streaming responses
  - Safe error reporting, timeouts, and loading states
  - Preserving Sentinel's existing model router architecture
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger("Sentinel.Provider")


class ProviderError(RuntimeError):
    """Base exception for model provider errors."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class ProviderRuntimeStatus:
    name: str
    status: str  # "available" | "unavailable" | "not_configured"
    endpoint: str | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelInventoryItem:
    id: str
    name: str
    size_bytes: int | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    family: str | None = None
    modified_at: str | None = None
    status: str = "ready"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseModelProvider(ABC):
    """Abstract interface for SentinelOS model providers."""

    name: str = "base"

    @abstractmethod
    def check_runtime(self) -> ProviderRuntimeStatus:
        """Check whether the model runtime engine is reachable and configured."""
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[ModelInventoryItem]:
        """Discover actually installed models. Returns an empty list if none are present."""
        raise NotImplementedError

    @abstractmethod
    def get_model_status(self, model_id: str | None) -> str:
        """Return readiness status: 'ready', 'loading', 'unavailable', or 'not_configured'."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Execute a completion/chat request."""
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream completion tokens and events when supported."""
        raise NotImplementedError


class OllamaProvider(BaseModelProvider):
    """Provider adapter for local Ollama runtimes."""

    name: str = "ollama"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 2.0):
        import os
        configured = base_url or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        if "://" not in configured:
            configured = f"http://{configured}"
        self.base_url = configured.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check_runtime(self) -> ProviderRuntimeStatus:
        """Probe Ollama endpoint without modifying state."""
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if 200 <= res.status_code < 300:
                    data = res.json()
                    models_count = len(data.get("models", []))
                    return ProviderRuntimeStatus(
                        name=self.name,
                        status="available",
                        endpoint=self.base_url,
                        message="Ollama runtime is reachable and responsive.",
                        details={"installed_count": models_count},
                    )
                return ProviderRuntimeStatus(
                    name=self.name,
                    status="unavailable",
                    endpoint=self.base_url,
                    message=f"Ollama returned HTTP status {res.status_code}.",
                )
        except httpx.ConnectError:
            return ProviderRuntimeStatus(
                name=self.name,
                status="unavailable",
                endpoint=self.base_url,
                message="Cannot connect to Ollama runtime at configured endpoint. Daemon may be stopped.",
            )
        except httpx.TimeoutException:
            return ProviderRuntimeStatus(
                name=self.name,
                status="unavailable",
                endpoint=self.base_url,
                message="Connection to Ollama runtime timed out.",
            )
        except Exception as err:
            return ProviderRuntimeStatus(
                name=self.name,
                status="unavailable",
                endpoint=self.base_url,
                message=f"Runtime probe failed: {err}",
            )

    def list_models(self) -> list[ModelInventoryItem]:
        """Fetch real model inventory from Ollama /api/tags. Never invents models."""
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code != 200:
                    return []
                data = res.json()
                raw_models = data.get("models", [])
                inventory: list[ModelInventoryItem] = []
                for item in raw_models:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or item.get("model") or ""
                    if not name:
                        continue
                    details = item.get("details", {})
                    inventory.append(
                        ModelInventoryItem(
                            id=name,
                            name=name,
                            size_bytes=item.get("size"),
                            parameter_size=details.get("parameter_size"),
                            quantization=details.get("quantization_level"),
                            family=details.get("family"),
                            modified_at=item.get("modified_at"),
                            status="ready",
                        )
                    )
                return inventory
        except Exception as err:
            logger.debug("Failed to list models from Ollama: %s", err)
            return []

    def get_model_status(self, model_id: str | None) -> str:
        if not model_id:
            return "not_configured"
        models = self.list_models()
        model_names = {m.name for m in models} | {m.id for m in models}
        if model_id in model_names:
            return "ready"
        runtime = self.check_runtime()
        if runtime.status != "available":
            return "unavailable"
        return "unavailable"

    def generate(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call Ollama /api/chat with the configured model."""
        runtime = self.check_runtime()
        if runtime.status != "available":
            raise ProviderError(
                "runtime_unavailable",
                f"Ollama runtime at {self.base_url} is currently unavailable.",
                {"endpoint": self.base_url},
            )
        models = self.list_models()
        if not any(m.name == model or m.id == model for m in models):
            raise ProviderError(
                "model_not_found",
                f"Model '{model}' is not installed in the Ollama runtime.",
                {"requested_model": model, "installed_models": [m.name for m in models]},
            )

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        try:
            with httpx.Client(timeout=120.0, trust_env=False) as client:
                res = client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code != 200:
                    raise ProviderError(
                        "generation_failed",
                        f"Ollama returned HTTP error {res.status_code}: {res.text}",
                    )
                data = res.json()
                return data.get("message", {}).get("content", "")
        except httpx.TimeoutException as err:
            raise ProviderError(
                "generation_timeout",
                f"Model '{model}' timed out while generating a response.",
            ) from err
        except httpx.RequestError as err:
            raise ProviderError(
                "runtime_disconnected",
                f"Network error while communicating with Ollama: {err}",
            ) from err

    async def stream(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        runtime = self.check_runtime()
        if runtime.status != "available":
            yield {"type": "error", "code": "runtime_unavailable", "message": f"Ollama is unreachable at {self.base_url}."}
            return

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code != 200:
                        yield {"type": "error", "code": "generation_failed", "message": f"Ollama HTTP {response.status_code}"}
                        return
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield {"type": "delta", "text": content}
                            if data.get("done"):
                                yield {"type": "metrics", "finish_reason": "stop"}
                        except Exception:
                            continue
        except Exception as err:
            yield {"type": "error", "code": "stream_failed", "message": str(err)}


class OmniRouteProvider(BaseModelProvider):
    """Provider adapter for remote/federated models managed via OmniRoute."""

    name: str = "omniroute"

    def __init__(self, backend=None):
        if backend is None:
            from models.omniroute import OmniRouteBackend
            backend = OmniRouteBackend()
        self.backend = backend

    def check_runtime(self) -> ProviderRuntimeStatus:
        from models.router import ModelRouter
        router = ModelRouter()
        health = router.health()
        if not health.get("enabled"):
            return ProviderRuntimeStatus(
                name=self.name,
                status="not_configured",
                message="OmniRoute is not enabled in Sentinel settings.",
            )
        status = health.get("status", "unavailable")
        is_avail = status == "healthy" or health.get("endpoint_reachable", False)
        return ProviderRuntimeStatus(
            name=self.name,
            status="available" if is_avail else "unavailable",
            message=f"OmniRoute status: {status}",
            details=health,
        )

    def list_models(self) -> list[ModelInventoryItem]:
        from config.settings import RoutingSettings
        try:
            settings = RoutingSettings.from_env()
        except Exception:
            return []
        if not settings.omniroute_enabled:
            return []
        try:
            headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
            with httpx.Client(timeout=2.0, trust_env=False) as client:
                res = client.get(f"{settings.base_url}/models", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    items = []
                    for entry in data.get("data", []):
                        if isinstance(entry, dict) and "id" in entry:
                            items.append(ModelInventoryItem(id=entry["id"], name=entry["id"]))
                    return items
        except Exception:
            pass
        return []

    def get_model_status(self, model_id: str | None) -> str:
        if not model_id:
            return "not_configured"
        models = self.list_models()
        return "ready" if any(m.id == model_id for m in models) else "unavailable"

    def generate(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        route = kwargs.get("route")
        if route is None:
            from models.router import ModelRoute
            route = ModelRoute("omniroute", "chat", model, model, "omniroute")
        return self.backend.generate(route, messages)

    async def stream(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        route = kwargs.get("route")
        if route is None:
            from models.router import ModelRoute
            route = ModelRoute("omniroute", "chat", model, model, "omniroute")
        async for evt in self.backend.stream(route, messages):
            yield evt


class MockProvider(BaseModelProvider):
    """Explicit mock provider strictly for automated tests.

    Never presented as real AI output or used in production.
    """

    name: str = "mock"

    def __init__(
        self,
        available: bool = True,
        models: list[str] | None = None,
        canned_response: str = "Mock test response",
    ):
        self.available = available
        self._models = models or []
        self.canned_response = canned_response

    def check_runtime(self) -> ProviderRuntimeStatus:
        return ProviderRuntimeStatus(
            name=self.name,
            status="available" if self.available else "unavailable",
            endpoint="mock://test-runtime",
            message="Mock test provider.",
        )

    def list_models(self) -> list[ModelInventoryItem]:
        if not self.available:
            return []
        return [
            ModelInventoryItem(id=m, name=m, parameter_size="mock", status="ready")
            for m in self._models
        ]

    def get_model_status(self, model_id: str | None) -> str:
        if not model_id:
            return "not_configured"
        if not self.available:
            return "unavailable"
        return "ready" if model_id in self._models else "unavailable"

    def generate(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if not self.available:
            raise ProviderError("runtime_unavailable", "Mock runtime is unavailable.")
        if model not in self._models:
            raise ProviderError("model_not_found", f"Model '{model}' not found in mock.")
        return self.canned_response

    async def stream(
        self, model: str, messages: list[dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        if not self.available:
            yield {"type": "error", "code": "runtime_unavailable", "message": "Mock runtime offline."}
            return
        yield {"type": "delta", "text": self.canned_response}
        yield {"type": "metrics", "finish_reason": "stop"}
