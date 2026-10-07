"""Sentinel's model selection and backend policy boundary."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from core.logger import logger
from config.settings import RoutingConfigurationError, RoutingSettings
from models.registry import ModelRegistry


class ModelRoutingError(RuntimeError):
    """Safe, structured error raised for invalid or incomplete route policy."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ModelRoute:
    backend: str
    task: str
    model: str
    local_model: str
    provider: str
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False, compare=False)
    fallback_to_local: bool = False
    data_policy: str = "redact"

    def metadata(self, request_id: str, *, latency_ms: int, success: bool,
                 failure_reason: str | None = None, fallback_used: bool = False):
        return {
            "request_id": request_id,
            "task_type": self.task,
            "backend": self.backend,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": latency_ms,
            "success": success,
            "failure_reason": failure_reason,
            "fallback_used": fallback_used,
        }


class ModelRouter:
    """Keeps Sentinel task routing while selecting an allowed model backend."""

    def __init__(self, settings=None, omni_backend=None):
        self.registry = ModelRegistry()
        self._local_model_ids = {entry["name"] for entry in self.registry.all().values()}
        self._installed_local_models = set()
        self._installed_local_models_at = 0.0
        self._config_error = None
        try:
            self.settings = settings or RoutingSettings.from_env()
        except RoutingConfigurationError as error:
            self.settings = RoutingSettings()
            self._config_error = ModelRoutingError(error.code, str(error))
        if omni_backend is None:
            from models.omniroute import OmniRouteBackend
            omni_backend = OmniRouteBackend()
        self.omni_backend = omni_backend

    def choose(self, task):
        """Return Sentinel's existing local model choice for compatibility."""
        task = task.lower().strip()
        if task in {"chat", "math", "general"}:
            return self.registry.model_name("general")
        if task in {"planning", "coding", "tool"}:
            return self.registry.model_name("planner")
        if task in {"cyber", "security", "malware", "red", "soc", "blue", "purple"}:
            return self.registry.model_name("cyber")
        return self.registry.model_name("deep")

    @staticmethod
    def infer_task(model):
        name = (model or "").lower()
        if "whiterabbitneo" in name or "coder" in name:
            return "planning"
        if "notmythos" in name or "cybercrew" in name:
            return "cyber"
        if name.startswith("qwen3:4b"):
            return "chat"
        return "deep"

    def resolve(self, task, requested_model=None):
        if self._config_error:
            raise self._config_error
        normalized_task = (task or "chat").strip().lower()
        local_model = self.choose(normalized_task)
        settings = self.settings
        requested = (requested_model or "").strip()

        if settings.policy == "local":
            if requested and requested in set(settings.remote_models.values()):
                raise ModelRoutingError(
                    "model_backend_mismatch",
                    "The selected model is configured for OmniRoute, but Sentinel is set to local routing.",
                )
            if requested and requested not in self._local_model_ids:
                self._require_installed_local_model(requested)
            return ModelRoute("local", normalized_task, requested or local_model, local_model, "ollama")

        configured_remote = self._configured_remote_model(normalized_task)
        configured_remote_ids = set(settings.remote_models.values())
        if settings.policy == "auto" and requested in configured_remote_ids and not settings.omniroute_enabled:
            raise ModelRoutingError("omniroute_disabled", "The requested OmniRoute model is configured, but OmniRoute is disabled.")
        if settings.policy == "auto" and requested and requested not in configured_remote_ids:
            if requested not in self._local_model_ids:
                self._require_installed_local_model(requested)
            return ModelRoute("local", normalized_task, requested, local_model, "ollama")

        remote_model = requested if requested in configured_remote_ids else configured_remote
        use_remote = settings.policy == "omniroute" or (
            settings.policy == "auto" and settings.omniroute_enabled and remote_model is not None
        )
        if not use_remote:
            if settings.policy == "auto":
                return ModelRoute("local", normalized_task, requested or local_model, local_model, "ollama")
            raise ModelRoutingError("omniroute_not_configured", "OmniRoute is not enabled and configured for the requested task.")

        if not settings.omniroute_enabled:
            raise ModelRoutingError("omniroute_disabled", "OmniRoute routing was selected, but OmniRoute is disabled.")
        if not remote_model:
            if settings.policy == "auto":
                return ModelRoute("local", normalized_task, requested or local_model, local_model, "ollama")
            raise ModelRoutingError("omniroute_model_unconfigured", "No OmniRoute model is configured for this task.")
        if requested and requested not in configured_remote_ids and settings.policy == "omniroute":
            # A local model selection is not a remote-provider authorization.
            if requested in self._local_model_ids or self._is_installed_local_model(requested):
                remote_model = configured_remote
            else:
                raise ModelRoutingError("model_not_allowed", "The requested OmniRoute model is not in Sentinel's configured model allowlist.")
        if not remote_model:
            raise ModelRoutingError("omniroute_model_unconfigured", "No OmniRoute model is configured for this task.")

        provider = remote_model.split("/", 1)[0] if "/" in remote_model else "omniroute"
        return ModelRoute(
            "omniroute", normalized_task, remote_model, local_model, provider,
            settings.base_url, settings.api_key, settings.fallback_to_local, settings.data_policy,
        )

    def _require_installed_local_model(self, model):
        if not self._is_installed_local_model(model):
            raise ModelRoutingError(
                "model_not_allowed",
                "The requested local model is not installed in Ollama or permitted by Sentinel.",
            )

    def _is_installed_local_model(self, model):
        if model in self._local_model_ids:
            return True
        now = time.monotonic()
        if now - self._installed_local_models_at > 15:
            from ai.ollama_runtime import get_ollama_runtime
            try:
                runtime = get_ollama_runtime()
                runtime.ensure_running()
                response = httpx.get(f"{runtime.base_url}/api/tags", timeout=2.0, trust_env=False)
                response.raise_for_status()
                self._installed_local_models = {
                    entry["name"] for entry in response.json().get("models", [])
                    if isinstance(entry, dict) and isinstance(entry.get("name"), str)
                }
            except Exception as error:
                self._installed_local_models = set()
                self._installed_local_models_at = now
                raise ModelRoutingError(
                    "ollama_unavailable",
                    "Sentinel could not verify the installed local models.",
                ) from error
            self._installed_local_models_at = now
        return model in self._installed_local_models

    def generate(self, task, model, messages, local_generate, route=None):
        route = route or self.resolve(task or self.infer_task(model), model)
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        fallback_used = False
        try:
            if route.backend == "local":
                result = local_generate(route.model, messages)
            else:
                result = self.omni_backend.generate(route, messages)
            self._log_result(route, request_id, started, True)
            return result
        except Exception as error:
            failure_reason = getattr(error, "code", "generation_failed")
            if route.backend == "omniroute" and route.fallback_to_local:
                fallback_used = True
                fallback_route = ModelRoute("local", route.task, route.local_model, route.local_model, "ollama")
                try:
                    result = local_generate(fallback_route.model, messages)
                    self._log_result(route, request_id, started, True, failure_reason, fallback_used=True)
                    return result
                except Exception:
                    self._log_result(route, request_id, started, False, failure_reason, fallback_used)
                    raise
            self._log_result(route, request_id, started, False, failure_reason, fallback_used)
            raise

    def _log_result(self, route, request_id, started, success, failure_reason=None, fallback_used=False):
        metadata = route.metadata(
            request_id, latency_ms=round((time.monotonic() - started) * 1000),
            success=success, failure_reason=failure_reason, fallback_used=fallback_used,
        )
        logger.info("Model request metadata: %s", json.dumps(metadata, sort_keys=True))

    def health(self):
        omni_root = Path(__file__).resolve().parents[1] / "OmniRoute"
        installed = (omni_root / "package.json").is_file() and (omni_root / "node_modules").is_dir()
        if self._config_error:
            return {"installed": installed, "enabled": False, "configured": False,
                    "provider_available": False, "model_available": False,
                    "endpoint_reachable": False, "status": "configuration_error",
                    "error": self._config_error.code}
        settings = self.settings
        configured = bool(settings.remote_models)
        result = {"installed": installed, "enabled": settings.omniroute_enabled,
                  "configured": configured, "provider_available": False,
                  "model_available": False, "endpoint_reachable": False,
                  "status": "disabled" if not settings.omniroute_enabled else "not_configured"}
        if not settings.omniroute_enabled:
            return result
        try:
            headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
            response = httpx.get(
                f"{settings.base_url}/models", headers=headers, timeout=2.0, trust_env=False
            )
            result["endpoint_reachable"] = response.status_code < 500
            response.raise_for_status()
            result["provider_available"] = True
            body = response.json()
            available = {entry.get("id") for entry in body.get("data", []) if isinstance(entry, dict)}
            result["model_available"] = bool(settings.remote_models) and set(settings.remote_models.values()).issubset(available)
            result["status"] = "healthy" if result["model_available"] else "model_unavailable"
        except (httpx.HTTPError, ValueError, AttributeError):
            result["status"] = "unavailable"
        return result

    def _configured_remote_model(self, task):
        models = self.settings.remote_models
        if task in models:
            return models[task]
        aliases = {
            "chat": ("general",),
            "math": ("general", "chat"),
            "general": ("chat",),
            "planning": ("coding", "tool"),
            "coding": ("planning",),
            "tool": ("planning", "coding"),
            "cyber": ("security",),
            "security": ("cyber",),
            "red": ("cyber", "security"),
            "soc": ("cyber", "security"),
            "blue": ("soc", "cyber", "security"),
            "purple": ("cyber", "security"),
        }
        for alias in aliases.get(task, ()):
            if alias in models:
                return models[alias]
        return None
