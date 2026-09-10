"""Persistent sessions and streamed requests for the local command console."""
import asyncio
import json
import time
from contextlib import aclosing

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from starlette.responses import StreamingResponse

from ai.ollama_runtime import OllamaRuntimeError
from ai.streaming import ModelFailure
from models.profiles import MODELS


router = APIRouter(prefix="/api")


class StreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    model: str | None = Field(default=None, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$")

    @field_validator("message")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Message cannot be empty")
        return value.strip()


class MemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Memory cannot be empty")
        return value.strip()


def session_or_404(store, session_id):
    try:
        return store.get(session_id)
    except KeyError as error:
        raise HTTPException(404, "Conversation not found") from error


class CancellableResponse(StreamingResponse):
    """Watch disconnects even while Ollama has not emitted its first token."""
    async def __call__(self, scope, receive, send):
        try:
            async with anyio.create_task_group() as group:
                async def send_body():
                    try:
                        await self.stream_response(send)
                    except OSError:
                        pass  # Socket closed by Stop/navigation.
                    finally:
                        group.cancel_scope.cancel()

                async def watch_disconnect():
                    await self.listen_for_disconnect(receive)
                    group.cancel_scope.cancel()

                group.start_soon(send_body)
                group.start_soon(watch_disconnect)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


@router.get("/sessions")
async def sessions(request: Request):
    return {"sessions": request.app.state.session_store.list_sessions()}


@router.post("/sessions")
async def new_session(request: Request):
    return request.app.state.session_store.create()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    return session_or_404(request.app.state.session_store, session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    if session_id in request.app.state.active_sessions:
        raise HTTPException(409, "Stop the active request before deleting this conversation")
    store = request.app.state.session_store
    session_or_404(store, session_id)
    store.delete(session_id)
    return {"deleted": True}


@router.get("/memories")
async def memories(request: Request):
    return {"memories": request.app.state.session_store.memories()}


@router.post("/memories")
async def remember(payload: MemoryRequest, request: Request):
    try:
        return request.app.state.session_store.remember(payload.content)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.delete("/memories/{memory_id}")
async def forget(memory_id: str, request: Request):
    try:
        request.app.state.session_store.forget(memory_id)
    except KeyError as error:
        raise HTTPException(404, "Memory not found") from error
    return {"deleted": True}


@router.get("/models")
async def models(request: Request):
    runtime = request.app.state.ollama_runtime
    installed = set()
    online = False
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(runtime.base_url + "/api/tags")
            response.raise_for_status()
            installed = {model["name"] for model in response.json()["models"]}
            online = True
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    names = installed | {model["name"] for model in MODELS.values()}
    return {"online": online, "models": [{"name": name, "installed": name in installed}
                                          for name in sorted(names)]}


@router.post("/runtime/start")
async def start_runtime(request: Request):
    try:
        await asyncio.to_thread(request.app.state.ollama_runtime.ensure_running)
    except OllamaRuntimeError as error:
        raise HTTPException(503, {"code": "ollama_unavailable", "message": str(error)}) from error
    return {"online": True}


@router.post("/chat/stream")
async def stream_chat(payload: StreamRequest, request: Request):
    from api.app import format_tool_result

    state = request.app.state
    session = session_or_404(state.session_store, payload.session_id)
    if state.command_lock.locked():
        raise HTTPException(409, "Another request is active. Stop it or wait for it to finish.")
    await state.command_lock.acquire()
    state.active_sessions.add(payload.session_id)

    async def body():
        reply, kind, outcome = "", "assistant", "cancelled"
        metrics = {"input_tokens": 0, "output_tokens": 0, "model_calls": 0}
        started = time.monotonic()
        saved = False

        def encode(event):
            return json.dumps(event, ensure_ascii=False) + "\n"

        try:
            async with aclosing(state.command_center.process_stream(
                payload.message, history=session["messages"], memories=state.session_store.memories(),
                model=payload.model, runtime=state.ollama_runtime
            )) as events:
                async for event in events:
                    if event["type"] == "delta":
                        reply += event["text"]
                    elif event["type"] == "metrics":
                        metrics["input_tokens"] += event.get("input_tokens", 0)
                        metrics["output_tokens"] += event.get("output_tokens", 0)
                        metrics["model_calls"] += 1
                        metrics["model"] = event.get("model")
                        metrics["finish_reason"] = event.get("finish_reason")
                        continue
                    elif event["type"] == "tool_result":
                        kind = "tool"
                        reply = format_tool_result(event["result"])
                        event = {"type": "result", "reply": reply, "kind": kind}
                    yield encode(event)
            outcome = "complete"
            metrics["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            state.session_store.append_turn(payload.session_id, payload.message, reply, outcome, kind, metrics)
            saved = True
            yield encode({"type": "result", "reply": reply, "kind": kind})
            yield encode({"type": "done", "session_id": payload.session_id, "metrics": metrics})
        except ModelFailure as error:
            outcome = "error"
            yield encode(error.event())
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception:
            outcome = "error"
            yield encode({"type": "error", "code": "generation_failed",
                          "message": "The request failed. Retry or select another model."})
        finally:
            try:
                if not saved:
                    metrics["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                    state.session_store.append_turn(payload.session_id, payload.message, reply, outcome, kind, metrics)
            finally:
                state.active_sessions.discard(payload.session_id)
                state.command_lock.release()

    return CancellableResponse(body(), media_type="application/x-ndjson",
                               headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
