"""Contract, routing, failure, and data-policy tests for OmniRoute integration."""

import asyncio
import json
import logging

import httpx
import pytest

from ai.streaming import stream_model
from config.settings import RoutingSettings
from models.omniroute import BackendFailure, OmniRouteBackend, sanitize_remote_messages
from models.router import ModelRoute, ModelRouter, ModelRoutingError


def settings(policy="local", *, enabled=False, models=None, fallback=True, data_policy="redact", api_key=None):
    return RoutingSettings(
        policy=policy,
        omniroute_enabled=enabled,
        base_url="http://127.0.0.1:20128/v1",
        api_key=api_key,
        remote_models=models or {},
        fallback_to_local=fallback,
        data_policy=data_policy,
    )


def remote_route(*, fallback=False, data_policy="redact", api_key=None):
    return ModelRoute(
        backend="omniroute", task="chat", model="openai/example-model",
        local_model="qwen3:4b", provider="openai",
        base_url="http://127.0.0.1:20128/v1", api_key=api_key,
        fallback_to_local=fallback, data_policy=data_policy,
    )


def test_local_policy_keeps_existing_ollama_routing():
    router = ModelRouter(settings())
    route = router.resolve("chat")
    assert route.backend == "local"
    assert route.model == "qwen3:4b"
    assert router.resolve("planning").model == "WhiteRabbitNeo/WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B:latest"
    assert router.resolve("cyber").model == "CyberCrew/notmythos-8b:latest"
    assert router.resolve("research").model == "qwen3.6:latest"


def test_omniroute_adapter_calls_openai_compatible_endpoint_with_allowlisted_model():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "remote answer"}}]})

    settings_ = settings("omniroute", enabled=True, models={"chat": "openai/example-model"}, api_key="test-api-key")
    router = ModelRouter(settings_, OmniRouteBackend(httpx.MockTransport(handler)))
    route = router.resolve("chat")
    assert router.generate("chat", route.model, [{"role": "user", "content": "hello"}],
                           lambda *_: pytest.fail("remote route used local backend"), route=route) == "remote answer"
    assert captured["url"].endswith("/chat/completions")
    assert captured["authorization"] == "Bearer test-api-key"
    assert captured["body"]["model"] == "openai/example-model"
    assert captured["body"]["stream"] is False


def test_auto_uses_remote_only_for_enabled_and_configured_tasks():
    router = ModelRouter(settings(
        "auto", enabled=True, models={"chat": "openai/example-model"}
    ))
    assert router.resolve("chat").backend == "omniroute"
    assert router.resolve("coding").backend == "local"
    assert router.resolve("chat", "qwen3:4b").backend == "local"


def test_local_policy_rejects_remote_model_selection():
    router = ModelRouter(settings(
        "local", enabled=True, models={"chat": "openai/example-model"}
    ))
    with pytest.raises(ModelRoutingError) as caught:
        router.resolve("chat", "openai/example-model")
    assert caught.value.code == "model_backend_mismatch"


def test_remote_failure_falls_back_to_local_and_records_metadata(caplog):
    def handler(request):
        raise httpx.ConnectError("private endpoint detail", request=request)

    router = ModelRouter(
        settings("omniroute", enabled=True, models={"chat": "openai/example-model"}, fallback=True),
        OmniRouteBackend(httpx.MockTransport(handler)),
    )
    local_calls = []
    with caplog.at_level(logging.INFO, logger="Sentinel"):
        result = router.generate(
            "chat", "qwen3:4b", [{"role": "user", "content": "hello"}],
            lambda model, messages: local_calls.append(model) or "local answer",
        )
    assert result == "local answer"
    assert local_calls == ["qwen3:4b"]
    assert '"fallback_used": true' in caplog.text
    assert "private endpoint detail" not in caplog.text


def test_remote_errors_do_not_expose_api_key_or_provider_response(caplog):
    secret = "sentinel-private-api-key"

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {secret}"
        return httpx.Response(401, text=f"invalid {secret}")

    router = ModelRouter(
        settings("omniroute", enabled=True, models={"chat": "openai/example-model"},
                 fallback=False, api_key=secret),
        OmniRouteBackend(httpx.MockTransport(handler)),
    )
    route = router.resolve("chat")
    with caplog.at_level(logging.INFO, logger="Sentinel"):
        with pytest.raises(BackendFailure) as caught:
            router.generate("chat", route.model, [], lambda *_: None, route=route)
    assert caught.value.code == "omniroute_auth_failed"
    assert secret not in str(caught.value)
    assert secret not in repr(route)
    assert secret not in caplog.text
    assert "invalid " + secret not in caplog.text


def test_invalid_configuration_is_structured_without_startup_failure(monkeypatch):
    monkeypatch.setenv("SENTINEL_AI_BACKEND", "provider-from-user-input")
    router = ModelRouter()
    with pytest.raises(ModelRoutingError) as caught:
        router.resolve("chat")
    assert caught.value.code == "invalid_configuration"
    assert router.health()["status"] == "configuration_error"


def test_health_check_reports_endpoint_provider_and_model_separately(monkeypatch):
    router = ModelRouter(settings(
        "auto", enabled=True, models={"chat": "openai/example-model"}
    ))

    def response(url, **kwargs):
        assert url.endswith("/v1/models")
        assert kwargs["trust_env"] is False
        return httpx.Response(200, json={"data": [{"id": "openai/example-model"}]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr("models.router.httpx.get", response)
    health = router.health()
    assert health["installed"] is True
    assert health["enabled"] is True
    assert health["configured"] is True
    assert health["endpoint_reachable"] is True
    assert health["provider_available"] is True
    assert health["model_available"] is True
    assert health["status"] == "healthy"


def test_data_policy_redacts_credentials_and_private_paths():
    original = [{"role": "user", "content": (
        "Read C:\\Users\\Davin\\secrets.txt API_KEY=abcdef012345 "
        "Authorization: Bearer abcdefghijklmnop"
    )}]
    sanitized = sanitize_remote_messages(original)
    assert "C:\\Users\\Davin" not in sanitized[0]["content"]
    assert "abcdef012345" not in sanitized[0]["content"]
    assert "abcdefghijklmnop" not in sanitized[0]["content"]
    assert original[0]["content"].startswith("Read C:")
    with pytest.raises(BackendFailure) as caught:
        sanitize_remote_messages(original, "deny")
    assert caught.value.code == "remote_data_denied"


def test_remote_streaming_emits_deltas_and_backend_metrics():
    def handler(request):
        body = "\n".join([
            'data: {"choices":[{"delta":{"content":"Hello "}}]}',
            'data: {"choices":[{"delta":{"content":"there"}}]}',
            "data: [DONE]", "",
        ])
        return httpx.Response(200, text=body)

    route = remote_route()

    async def run():
        return [event async for event in stream_model(
            None, route.model, [{"role": "user", "content": "hello"}],
            route=route, transport=httpx.MockTransport(handler),
        )]

    events = asyncio.run(run())
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "Hello there"
    metrics = next(event for event in events if event["type"] == "metrics")
    assert metrics["backend"] == "omniroute"
    assert metrics["provider"] == "openai"


def test_remote_stream_failure_falls_back_through_existing_local_stream(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("private connection detail", request=request)

    route = remote_route(fallback=True)

    async def local_fallback(runtime, model, messages, *, planning=False, transport=None):
        assert model == "qwen3:4b"
        yield {"type": "delta", "text": "local fallback"}
        yield {"type": "metrics", "model": model}

    monkeypatch.setattr("ai.streaming._stream_local_model", local_fallback)

    async def combined_run():
        return [event async for event in stream_model(
            None, route.model, [{"role": "user", "content": "hello"}],
            route=route, transport=httpx.MockTransport(handler),
        )]

    events = asyncio.run(combined_run())
    assert any(event.get("stage") == "fallback" for event in events)
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "local fallback"
