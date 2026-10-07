"""Small, OpenAI-compatible adapter for a separately running OmniRoute service."""

from __future__ import annotations

import json
import re
import time
import uuid

import httpx
from models.backend import ModelBackend


class BackendFailure(RuntimeError):
    """A backend error with a safe user-facing message and stable code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b[\w.-]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential)[\w.-]*(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"), r"[REDACTED]\1[REDACTED]"),
)
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\[^\s<>\"|?*]+")
_UNC_PATH = re.compile(r"\\\\[A-Za-z0-9._-]+\\[^\s<>\"|?*]+")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9:/])/(?!/)[^\s<>\"']+")


def sanitize_remote_messages(messages, policy="redact"):
    """Apply Sentinel's remote-model data policy without mutating chat history."""
    if policy == "deny":
        raise BackendFailure("remote_data_denied", "Sentinel's data policy does not allow sending this request to OmniRoute.")
    if policy not in {"redact", "allow"}:
        raise BackendFailure("invalid_configuration", "Sentinel's OmniRoute data policy is invalid.")

    def sanitize(value):
        if isinstance(value, str) and policy == "redact":
            for pattern, replacement in _SECRET_PATTERNS:
                value = pattern.sub(replacement, value)
            value = _WINDOWS_PATH.sub("[LOCAL_PATH_REDACTED]", value)
            value = _UNC_PATH.sub("[LOCAL_PATH_REDACTED]", value)
            value = _POSIX_PATH.sub("[LOCAL_PATH_REDACTED]", value)
            return value
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        return value

    return sanitize(messages)


class OmniRouteBackend(ModelBackend):
    """Transport only: Sentinel continues to own planning and tool execution."""

    name = "omniroute"

    def __init__(self, transport=None):
        self.transport = transport

    @staticmethod
    def _headers(route):
        headers = {"Content-Type": "application/json"}
        if route.api_key:
            headers["Authorization"] = f"Bearer {route.api_key}"
        return headers

    @staticmethod
    def _payload(route, messages, stream=False):
        return {"model": route.model, "messages": messages, "stream": stream}

    def generate(self, route, messages):
        safe_messages = sanitize_remote_messages(messages, route.data_policy)
        try:
            with httpx.Client(timeout=httpx.Timeout(180.0, connect=5.0), trust_env=False,
                              transport=self.transport) as client:
                response = client.post(
                    f"{route.base_url}/chat/completions",
                    headers=self._headers(route),
                    json=self._payload(route, safe_messages),
                )
        except httpx.TimeoutException as error:
            raise BackendFailure("generation_timeout", "OmniRoute did not respond before the request timed out.") from error
        except httpx.RequestError as error:
            raise BackendFailure("omniroute_unavailable", "OmniRoute could not be reached.") from error
        self._check_response(response)
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str):
                raise ValueError("unexpected message content")
            return content
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise BackendFailure("generation_failed", "OmniRoute returned an invalid response.") from error

    async def stream(self, route, messages, *, planning=False, request_id=None):
        safe_messages = sanitize_remote_messages(messages, route.data_policy)
        request_id = request_id or uuid.uuid4().hex
        started = time.monotonic()
        answer_chars = 0
        yield {"type": "status", "stage": "routing", "model": route.model, "backend": "omniroute"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0), trust_env=False,
                                         transport=self.transport) as client:
                async with client.stream(
                    "POST", f"{route.base_url}/chat/completions",
                    headers=self._headers(route),
                    json=self._payload(route, safe_messages, stream=True),
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._check_response(response)
                    yield {"type": "status", "stage": "generating", "model": route.model, "backend": "omniroute"}
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            payload = json.loads(line)
                            delta = payload["choices"][0].get("delta", {}).get("content", "")
                        except (ValueError, KeyError, IndexError, TypeError) as error:
                            raise BackendFailure("generation_failed", "OmniRoute returned an invalid stream event.") from error
                        if isinstance(delta, list):
                            delta = "".join(part.get("text", "") for part in delta if isinstance(part, dict))
                        if delta:
                            if not isinstance(delta, str):
                                raise BackendFailure("generation_failed", "OmniRoute returned an invalid stream event.")
                            answer_chars += len(delta)
                            yield {"type": "delta", "text": delta}
            if not answer_chars:
                raise BackendFailure("generation_failed", "OmniRoute returned no answer.")
            yield {"type": "metrics", "model": route.model, "backend": "omniroute",
                   "provider": route.provider, "request_id": request_id,
                   "duration_ms": round((time.monotonic() - started) * 1000),
                   "finish_reason": "stop"}
        except httpx.TimeoutException as error:
            raise BackendFailure("generation_timeout", "OmniRoute did not respond before the request timed out.") from error
        except httpx.RequestError as error:
            raise BackendFailure("omniroute_unavailable", "OmniRoute could not be reached.") from error

    @staticmethod
    def _check_response(response):
        if response.status_code in {401, 403}:
            raise BackendFailure("omniroute_auth_failed", "OmniRoute rejected the configured authentication.")
        if response.status_code == 404:
            raise BackendFailure("model_unavailable", "OmniRoute could not find the configured provider or model.")
        if response.status_code >= 500:
            raise BackendFailure("provider_unavailable", "The configured OmniRoute provider is unavailable.")
        if response.status_code >= 400:
            raise BackendFailure("generation_failed", "OmniRoute rejected the model request.")
