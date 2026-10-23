"""
tests/test_provider_integration.py
==================================
Tests for the modular model provider layer and Model Hub API endpoints.

Verifies:
  - Runtime availability checks (available, unavailable, not_configured)
  - Discovering models (handling empty inventory gracefully)
  - Model status and readiness reporting
  - Independent health reporting (backend online even when AI runtime is offline)
  - MockProvider behavior for isolated automated tests
  - No models are downloaded or pulled during tests
"""

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from models.provider import (
    BaseModelProvider,
    MockProvider,
    ModelInventoryItem,
    OllamaProvider,
    ProviderError,
    ProviderRuntimeStatus,
)
from models.router import ModelRouter, ModelRoute


class DummyCommandCenter:
    def __init__(self, router=None):
        from unittest.mock import Mock
        self.router = router or ModelRouter()
        self.ai = Mock()
        self.ai.router = self.router
        self.tools = Mock()
        self.tools.names.return_value = ["ping", "read_file", "list_processes"]


def test_mock_provider_lifecycle():
    provider = MockProvider(available=True, models=["test-model:latest"], canned_response="Verified response")
    status = provider.check_runtime()
    assert status.status == "available"
    assert status.name == "mock"

    models = provider.list_models()
    assert len(models) == 1
    assert models[0].id == "test-model:latest"
    assert models[0].name == "test-model:latest"

    assert provider.get_model_status("test-model:latest") == "ready"
    assert provider.get_model_status("nonexistent-model") == "unavailable"
    assert provider.get_model_status(None) == "not_configured"

    response = provider.generate("test-model:latest", [{"role": "user", "content": "hi"}])
    assert response == "Verified response"


def test_mock_provider_unavailable():
    provider = MockProvider(available=False)
    status = provider.check_runtime()
    assert status.status == "unavailable"
    assert provider.list_models() == []
    assert provider.get_model_status("any-model") == "unavailable"

    with pytest.raises(ProviderError) as exc:
        provider.generate("any-model", [])
    assert exc.value.code == "runtime_unavailable"


def test_ollama_provider_handles_offline_gracefully():
    # Use an unreachable local port
    provider = OllamaProvider(base_url="http://127.0.0.1:59999", timeout_seconds=0.1)
    status = provider.check_runtime()
    assert status.status == "unavailable"
    assert len(status.message) > 0

    # Empty model list returned, not an exception
    models = provider.list_models()
    assert models == []

    # Model status is unavailable
    assert provider.get_model_status("qwen3:4b") == "unavailable"


def test_model_router_with_mock_provider():
    router = ModelRouter()
    mock_provider = MockProvider(available=True, models=["custom-test-model"])
    router.set_provider(mock_provider)

    assert router.get_provider() is mock_provider
    assert router.check_runtime_availability().status == "available"

    models = router.discover_installed_models()
    assert len(models) == 1
    assert models[0].name == "custom-test-model"


def test_api_models_endpoint_empty_inventory():
    router = ModelRouter()
    # Offline mock provider simulating uninstalled/unconfigured state
    router.set_provider(MockProvider(available=False))
    center = DummyCommandCenter(router=router)

    app = create_app(command_center=center)
    with TestClient(app) as client:
        res = client.get("/api/models")
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "mock"
        assert data["runtime"]["status"] == "unavailable"
        assert data["model_status"] == "unavailable"
        assert data["installed_models"] == []
        assert "roles" in data


def test_api_models_endpoint_configured_runtime_empty_models():
    router = ModelRouter()
    # Runtime available, but 0 models installed
    router.set_provider(MockProvider(available=True, models=[]))
    center = DummyCommandCenter(router=router)

    app = create_app(command_center=center)
    with TestClient(app) as client:
        res = client.get("/api/models")
        assert res.status_code == 200
        data = res.json()
        assert data["runtime"]["status"] == "available"
        assert data["model_status"] == "not_configured"
        assert data["installed_models"] == []


def test_api_models_status_summary():
    router = ModelRouter()
    router.set_provider(MockProvider(available=True, models=[]))
    center = DummyCommandCenter(router=router)

    app = create_app(command_center=center)
    with TestClient(app) as client:
        res = client.get("/api/models/status")
        assert res.status_code == 200
        data = res.json()
        assert data["runtime_status"] == "available"
        assert data["model_status"] == "not_configured"
        assert data["models_count"] == 0
        assert "AI models not configured yet" in data["message"]


def test_api_models_select_endpoint():
    router = ModelRouter()
    router.set_provider(MockProvider(available=True, models=["test-model-1", "test-model-2"]))
    center = DummyCommandCenter(router=router)

    app = create_app(command_center=center)
    with TestClient(app) as client:
        # Valid model
        res = client.post("/api/models/select", json={"model": "test-model-1", "role": "general"})
        assert res.status_code == 200
        assert res.json()["success"] is True

        # Invalid model rejection
        res = client.post("/api/models/select", json={"model": "nonexistent-model", "role": "general"})
        assert res.status_code == 400


def test_backend_health_independent_of_ai_runtime():
    """SentinelOS backend health remains online regardless of model availability."""
    router = ModelRouter()
    router.set_provider(MockProvider(available=False))
    center = DummyCommandCenter(router=router)

    from ai.ollama_runtime import OllamaRuntime
    fake_runtime = OllamaRuntime(base_url="http://127.0.0.1:59999")

    app = create_app(command_center=center, ollama_runtime=fake_runtime)
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        # Backend itself is online
        assert data["status"] == "online"
        # Tool inventory reported
        assert "ping" in data["tools"]
        # AI runtime reported as standby/offline
        assert data["ollama"] == "standby"


def test_chat_deterministic_commands():
    router = ModelRouter()
    router.set_provider(MockProvider(available=False))
    center = DummyCommandCenter(router=router)
    center.authorized_targets = [
        {"auth_level": "lab", "label": "metasploitable", "targets": ["192.168.1.100"]}
    ]
    center.agent_state = {"is_running": False, "task_history_count": 2}
    center.stop_agent = lambda: False

    app = create_app(command_center=center)
    with TestClient(app) as client:
        # /targets works without AI runtime
        res = client.post("/api/chat", json={"message": "/targets"})
        assert res.status_code == 200
        assert "192.168.1.100" in res.json()["reply"]

        # /status works without AI runtime
        res = client.post("/api/chat", json={"message": "/status"})
        assert res.status_code == 200
        assert "IDLE" in res.json()["reply"]

        # /stop works without AI runtime
        res = client.post("/api/chat", json={"message": "/stop"})
        assert res.status_code == 200
        assert "No agent currently running" in res.json()["reply"]


def test_chat_reports_unconfigured_model_honestly():
    router = ModelRouter()
    router.set_provider(MockProvider(available=False))
    center = DummyCommandCenter(router=router)
    # When no model is configured and someone prompts AI
    def fail_process(msg):
        raise ProviderError("model_not_configured", "AI models not configured yet.")
    center.process = fail_process

    app = create_app(command_center=center)
    with TestClient(app) as client:
        res = client.post("/api/chat", json={"message": "explain this code"})
        assert res.status_code == 503
        data = res.json()
        assert "detail" in data
