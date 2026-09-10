from fastapi.testclient import TestClient

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


def build_client():
    center = FakeCommandCenter()
    app = create_app(center)

    return center, TestClient(app)


def test_interface_is_served():
    _, client = build_client()

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Sentinel OS" in response.text
    assert "/static/styles.css" in response.text
    assert "/static/app.js" in response.text


def test_health_reports_discovered_tools():
    _, client = build_client()

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
    }


def test_chat_uses_command_center():
    center, client = build_client()

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
    center, client = build_client()
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
    _, client = build_client()

    with client:
        response = client.post(
            "/api/chat",
            json={"message": "   "},
        )

    assert response.status_code == 422


def test_processing_failure_returns_safe_error():
    center, client = build_client()
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
    center, client = build_client()

    with client:
        response = client.delete("/api/session")

    assert response.status_code == 200
    assert response.json() == {"cleared": True}
    assert center.ai.clear_calls == 1
