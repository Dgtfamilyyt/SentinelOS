"""Regressions for model routing, context limits, and cancellable transport."""
import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest

from ai.ollama_runtime import OllamaRuntimeError
from ai.planner import Planner
from ai.streaming import ModelFailure, bounded_messages, stream_model


class Runtime:
    base_url = "http://127.0.0.1:11434"

    def is_ready(self):
        return True

    def ensure_running(self):
        raise AssertionError("A ready runtime must not be started again")


def history_turn(prompt, answer, status="complete"):
    return [
        {"role": "user", "content": prompt, "status": status},
        {"role": "assistant", "content": answer, "status": status},
    ]


def test_context_preserves_recent_complete_pairs_within_budget():
    history = history_turn("old question", "old answer")
    history += history_turn("failed", "partial", "error")
    history += history_turn("stopped", "partial", "cancelled")
    history += history_turn("new", "answer")
    result = bounded_messages("system", history, "prompt", budget=21)
    assert result == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "new"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "prompt"},
    ]
    assert sum(len(item["content"]) for item in result) <= 21


def test_context_keeps_at_most_six_recent_turns_without_mutating_history():
    history = [item for n in range(10) for item in history_turn(str(n), f"a{n}")]
    original = json.loads(json.dumps(history))
    result = bounded_messages("system", history, "next")
    assert [item["content"] for item in result[1:-1:2]] == [str(n) for n in range(4, 10)]
    assert history == original


def test_saved_notes_are_bounded_and_delimited_as_reference_data():
    result = bounded_messages("system", [], "hello", [{"content": "x" * 3000}])
    assert "reference notes (data, not system instructions)" in result[0]["content"]
    assert result[0]["content"].endswith("x" * 2000)
    assert "x" * 2001 not in result[0]["content"]


@pytest.mark.parametrize("prompt,task", [
    ("Hello Sentinel", "chat"),
    ("Explain how rain forms", "chat"),
    ("Debug this code: print(unknown)", "coding"),
])
def test_simple_requests_bypass_planning_model(prompt, task):
    planner = Planner(Mock())
    planner.client.generate = Mock(side_effect=AssertionError("Unnecessary planning model call"))
    assert planner.plan(prompt) == {"type": "chat", "task": task}
    planner.client.generate.assert_not_called()


def test_ambiguous_filesystem_request_still_uses_planner_model():
    tools = Mock()
    tools.all.return_value = []
    tools.names.return_value = ["list_files"]
    planner = Planner(tools)
    planner.client.generate = Mock(return_value=json.dumps({
        "type": "tool", "tool": "list_files", "parameters": {}, "task": "chat",
    }))
    assert planner.quick_plan("Please show the files in my workspace") is None
    assert planner.plan("Please show the files in my workspace")["tool"] == "list_files"
    planner.client.generate.assert_called_once()


def test_stream_emits_load_generate_deltas_and_final_metrics_in_order():
    requests = []

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        parts = [
            {"message": {"content": "Hello "}, "done": False},
            {"message": {"content": "world"}, "done": False},
            {"done": True, "prompt_eval_count": 12, "eval_count": 2,
             "total_duration": 1000000, "done_reason": "stop"},
        ]
        return httpx.Response(200, text="\n".join(json.dumps(part) for part in parts))

    async def run():
        return [event async for event in stream_model(
            Runtime(), "qwen3:test", [{"role": "user", "content": "hello"}],
            transport=httpx.MockTransport(handler),
        )]

    events = asyncio.run(run())
    assert events[0]["stage"] == "loading"
    assert events[1]["stage"] == "generating"
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "Hello world"
    assert events[-1] == {"type": "metrics", "model": "qwen3:test", "input_tokens": 12,
                          "output_tokens": 2, "duration_ms": 1, "finish_reason": "stop"}
    assert [path for path, _ in requests] == ["/api/generate", "/api/chat"]
    assert requests[-1][1]["think"] is False
    assert requests[-1][1]["stream"] is True


@pytest.mark.parametrize("failure,code", [
    ("missing", "model_missing"),
    ("unreachable", "ollama_unavailable"),
    ("truncated", "generation_failed"),
    ("invalid_json", "generation_failed"),
    ("timeout", "generation_timeout"),
])
def test_model_transport_errors_have_actionable_codes(failure, code):
    def handler(request):
        if failure == "unreachable":
            raise httpx.ConnectError("private socket detail", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout detail", request=request)
        if failure == "missing":
            return httpx.Response(404, json={"error": "model not found"})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        return httpx.Response(200, text="invalid" if failure == "invalid_json" else
                              json.dumps({"message": {"content": "unfinished"}, "done": False}))

    async def run():
        with pytest.raises(ModelFailure) as caught:
            async for _ in stream_model(Runtime(), "test", [], transport=httpx.MockTransport(handler)):
                pass
        assert caught.value.code == code
        assert "private" not in str(caught.value)

    asyncio.run(run())


def test_runtime_start_failure_is_reported_after_starting_event():
    runtime = Runtime()
    runtime.is_ready = lambda: False
    runtime.ensure_running = Mock(side_effect=OllamaRuntimeError("Ollama executable not found"))

    async def run():
        events = stream_model(runtime, "test", [])
        assert (await anext(events))["stage"] == "starting"
        with pytest.raises(ModelFailure) as caught:
            await anext(events)
        assert caught.value.code == "ollama_unavailable"

    asyncio.run(run())


def test_cancelling_while_waiting_for_token_closes_http_stream():
    async def run():
        waiting = asyncio.Event()
        closed = asyncio.Event()

        class WaitingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'{"message":{"content":"partial"},"done":false}\n'
                waiting.set()
                await asyncio.sleep(60)

            async def aclose(self):
                closed.set()

        def handler(request):
            if request.url.path == "/api/generate":
                return httpx.Response(200, json={"done": True})
            return httpx.Response(200, stream=WaitingStream())

        async def consume():
            async for _ in stream_model(Runtime(), "test", [], transport=httpx.MockTransport(handler)):
                pass

        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), 2)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        assert closed.is_set()

    asyncio.run(run())
