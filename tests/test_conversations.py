"""Persistent sessions and real ASGI disconnect behavior, without Ollama calls."""
import asyncio
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from ai.streaming import ModelFailure, bounded_messages
from api.app import create_app
from memory.session_store import SessionStore


class FakeCenter:
    def __init__(self):
        self.tools = Mock()
        self.tools.names.return_value = []
        self.calls = []
        self.failure = None

    async def process_stream(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        yield {"type": "status", "stage": "routing"}
        yield {"type": "delta", "text": "Hello "}
        if self.failure:
            raise self.failure
        yield {"type": "delta", "text": "Sentinel"}
        yield {"type": "metrics", "input_tokens": 8, "output_tokens": 2, "model": "test"}


def build_app(tmp_path, center=None):
    center = center or FakeCenter()
    runtime = Mock()
    runtime.base_url = "http://127.0.0.1:11434"
    return create_app(center, ollama_runtime=runtime, session_store=SessionStore(tmp_path)), center


def test_sessions_reload_isolate_and_delete_without_cross_talk(tmp_path):
    store = SessionStore(tmp_path)
    first, second = store.create(), store.create()
    store.append_turn(first["id"], "A private question", "A private reply")
    reloaded = SessionStore(tmp_path)
    assert reloaded.get(first["id"])["messages"][1]["content"] == "A private reply"
    assert reloaded.get(second["id"])["messages"] == []
    assert len(reloaded.list_sessions()) == 2
    reloaded.delete(first["id"])
    with pytest.raises(KeyError):
        store.get(first["id"])
    assert reloaded.get(second["id"])["messages"] == []


def test_remember_is_explicit_persistent_deduplicated_and_forgettable(tmp_path):
    store = SessionStore(tmp_path)
    session = store.create()
    store.append_turn(session["id"], "My preference is tea", "Understood")
    assert store.memories() == []
    memory = store.remember("I prefer tea")
    assert store.remember("I prefer tea") == memory
    reloaded = SessionStore(tmp_path)
    assert reloaded.memories() == [memory]
    reloaded.forget(memory["id"])
    assert store.memories() == []


def test_streamed_response_events_and_persistent_session_context(tmp_path):
    app, center = build_app(tmp_path)
    with TestClient(app) as client:
        first = client.post("/api/sessions").json()["id"]
        second = client.post("/api/sessions").json()["id"]
        client.post("/api/memories", json={"content": "Keep answers brief"})
        response = client.post("/api/chat/stream", json={
            "message": "  hello  ", "session_id": first, "model": "test",
        })
        events = [json.loads(line) for line in response.text.splitlines()]
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        assert [event["type"] for event in events] == ["status", "delta", "delta", "result", "done"]
        assert events[-2]["reply"] == "Hello Sentinel"
        assert events[-1]["metrics"]["input_tokens"] == 8
        assert events[-1]["metrics"]["model_calls"] == 1
        assert events[-1]["session_id"] == first
        assert center.calls[0][0] == "hello"
        assert center.calls[0][1]["model"] == "test"
        assert center.calls[0][1]["memories"][0]["content"] == "Keep answers brief"
        assert center.calls[0][1]["history"] == []
        client.post("/api/chat/stream", json={"message": "again", "session_id": first})
        assert len(center.calls[-1][1]["history"]) == 2
        client.post("/api/chat/stream", json={"message": "separate", "session_id": second})
        assert center.calls[-1][1]["history"] == []
        assert len(client.get(f"/api/sessions/{first}").json()["messages"]) == 4
        assert not app.state.command_lock.locked()
        assert app.state.active_sessions == set()


@pytest.mark.parametrize("session_id,status", [("../outside", 422), ("g" * 32, 422), ("a" * 32, 404)])
def test_invalid_and_unknown_session_ids_are_rejected(tmp_path, session_id, status):
    app, center = build_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/chat/stream", json={"message": "hello", "session_id": session_id})
        assert response.status_code == status
        assert center.calls == []
    assert list(tmp_path.iterdir()) == []


def test_active_request_returns_409_without_starting_or_deleting(tmp_path):
    app, center = build_app(tmp_path)
    with TestClient(app) as client:
        session_id = client.post("/api/sessions").json()["id"]
        client.portal.call(app.state.command_lock.acquire)
        app.state.active_sessions.add(session_id)
        try:
            response = client.post("/api/chat/stream", json={"message": "hello", "session_id": session_id})
            assert response.status_code == 409
            assert client.delete(f"/api/sessions/{session_id}").status_code == 409
            assert center.calls == []
            assert client.get(f"/api/sessions/{session_id}").json()["messages"] == []
        finally:
            client.portal.call(app.state.command_lock.release)
            app.state.active_sessions.clear()


@pytest.mark.parametrize("failure,code", [
    (ModelFailure("model_missing", "Select an installed model", "missing"), "model_missing"),
    (ModelFailure("ollama_unavailable", "Start Ollama", "test"), "ollama_unavailable"),
    (RuntimeError("private implementation detail"), "generation_failed"),
])
def test_stream_errors_keep_partial_response_but_exclude_it_from_context(tmp_path, failure, code):
    app, center = build_app(tmp_path)
    center.failure = failure
    with TestClient(app) as client:
        session_id = client.post("/api/sessions").json()["id"]
        response = client.post("/api/chat/stream", json={"message": "hello", "session_id": session_id})
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]["type"] == "error"
        assert events[-1]["code"] == code
        assert "private implementation detail" not in response.text
        assert not any(event["type"] == "done" for event in events)
        history = client.get(f"/api/sessions/{session_id}").json()["messages"]
        assert history[-1]["content"] == "Hello "
        assert all(item["status"] == "error" for item in history)
        assert len(bounded_messages("system", history, "retry")) == 2
        assert not app.state.command_lock.locked()
        assert not app.state.active_sessions


def test_memory_api_validates_and_forgets_saved_note(tmp_path):
    app, _ = build_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/memories", json={"content": "   "}).status_code == 422
        memory = client.post("/api/memories", json={"content": "  Use Celsius  "}).json()
        assert memory["content"] == "Use Celsius"
        assert client.get("/api/memories").json()["memories"] == [memory]
        assert client.delete(f"/api/memories/{memory['id']}").status_code == 200
        assert client.get("/api/memories").json()["memories"] == []


def test_asgi_disconnect_cancels_waiting_producer_saves_partial_and_releases_lock(tmp_path):
    async def run():
        waiting, closed = asyncio.Event(), asyncio.Event()

        class WaitingCenter(FakeCenter):
            async def process_stream(self, prompt, **kwargs):
                try:
                    yield {"type": "delta", "text": "Interrupted text"}
                    waiting.set()
                    await asyncio.sleep(60)
                finally:
                    closed.set()

        app, _ = build_app(tmp_path, WaitingCenter())
        async with app.router.lifespan_context(app):
            session_id = app.state.session_store.create()["id"]
            payload = json.dumps({"message": "hello", "session_id": session_id}).encode()
            first_receive = True
            sent = []

            async def receive():
                nonlocal first_receive
                if first_receive:
                    first_receive = False
                    return {"type": "http.request", "body": payload, "more_body": False}
                await waiting.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                sent.append(message)

            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                     "http_version": "1.1", "method": "POST", "scheme": "http",
                     "path": "/api/chat/stream", "raw_path": b"/api/chat/stream", "query_string": b"",
                     "root_path": "", "headers": [(b"host", b"testserver"),
                     (b"content-type", b"application/json")], "client": ("127.0.0.1", 1234),
                     "server": ("testserver", 80)}
            await asyncio.wait_for(app(scope, receive, send), 2)
            assert closed.is_set(), "Stop must close the producer even while waiting for tokens"
            assert not app.state.command_lock.locked()
            assert app.state.active_sessions == set()
            history = SessionStore(tmp_path).get(session_id)["messages"]
            assert [item["status"] for item in history] == ["cancelled", "cancelled"]
            assert history[-1]["content"] == "Interrupted text"
            assert len(bounded_messages("system", history, "next")) == 2
            assert any(message.get("status") == 200 for message in sent)

    asyncio.run(run())
