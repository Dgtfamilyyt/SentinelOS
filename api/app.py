import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ai.ollama_runtime import get_ollama_runtime
from core.command_center import CommandCenter
from core.logger import logger
from core.version import NAME, VERSION
from memory.session_store import SessionStore
from api.conversations import router as conversations_router
from api.voice import router as voice_router
from api.agent import router as agent_router
from api.molecular import router as molecular_router
from api.models import router as models_router
from models.router import ModelRoutingError
from models.omniroute import BackendFailure
from models.provider import ProviderError


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"


class ChatRequest(BaseModel):
    message: str = Field(max_length=20_000)

    @field_validator("message")
    @classmethod
    def message_must_have_content(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Message cannot be empty")

        return value


class ChatResponse(BaseModel):
    reply: str
    kind: Literal["assistant", "tool"]
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: Literal["online"]
    name: str
    version: str
    tools: list[str]
    ollama: Literal["online", "standby"]
    automatic_start: bool
    omniroute: dict[str, Any]


class SessionResponse(BaseModel):
    cleared: bool


def format_tool_result(result):
    if result.get("success"):
        value = result.get("result")

        if isinstance(value, str):
            return value

        return json.dumps(
            value,
            indent=2,
            ensure_ascii=False
        )

    error = result.get(
        "error",
        "Tool execution failed"
    )
    details = result.get("details")

    if details:
        detail_text = "; ".join(
            str(item)
            for item in details
        )
        return f"{error}: {detail_text}"

    return str(error)


router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    center = request.app.state.command_center
    ollama_runtime = request.app.state.ollama_runtime
    ollama_ready = await run_in_threadpool(
        ollama_runtime.is_ready
    )
    model_router = getattr(getattr(center, "ai", None), "router", None)
    if model_router is None:
        omniroute = {
            "installed": False, "enabled": False, "configured": False,
            "provider_available": False, "model_available": False,
            "endpoint_reachable": False, "status": "unavailable",
        }
    else:
        omniroute = await run_in_threadpool(model_router.health)

    return HealthResponse(
        status="online",
        name=NAME,
        version=VERSION,
        tools=sorted(center.tools.names()),
        ollama=(
            "online"
            if ollama_ready
            else "standby"
        ),
        automatic_start=True,
        omniroute=omniroute,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    center = request.app.state.command_center
    command_lock = request.app.state.command_lock

    msg = payload.message.strip()
    if msg.lower() == "/clear":
        async with command_lock:
            if hasattr(center.ai, "conversation"):
                center.ai.conversation.clear()
            else:
                center.ai.clear()
        return ChatResponse(reply="Conversation session cleared.", kind="assistant")

    if msg.lower() == "/status":
        state = center.agent_state
        status_line = "RUNNING" if state.get("is_running") else "IDLE"
        history_cnt = state.get("task_history_count", 0)
        return ChatResponse(
            reply=f"Agent Status: {status_line} | Completed Tasks: {history_cnt}",
            kind="tool",
            details=state,
        )

    if msg.lower() == "/targets":
        targets = center.authorized_targets
        if targets:
            formatted = "\n".join(
                f"[{t.get('auth_level', 'LAB').upper()}] {t.get('label', 'target')}: {', '.join(t.get('targets', []))}"
                for t in targets
            )
            return ChatResponse(
                reply=f"Authorized Lab Targets:\n{formatted}",
                kind="tool",
                details={"targets": targets},
            )
        return ChatResponse(
            reply="No lab targets configured. Edit config/authorized_targets.yaml",
            kind="tool",
            details={"targets": []},
        )

    if msg.lower() == "/stop":
        stopped = center.stop_agent()
        reply_txt = "Agent execution stopped." if stopped else "No agent currently running."
        return ChatResponse(reply=reply_txt, kind="assistant")

    try:
        async with command_lock:
            result = await run_in_threadpool(
                center.process,
                payload.message
            )

    except ModelRoutingError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": error.message},
        ) from error
    except BackendFailure as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": str(error)},
        ) from error
    except ProviderError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": error.code, "message": error.message},
        ) from error
    except Exception as error:
        logger.exception(
            "Web command processing failed"
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Sentinel could not complete the request. "
                "Confirm Ollama is running and the configured "
                "model is installed."
            ),
        ) from error

    if isinstance(result, dict):
        return ChatResponse(
            reply=format_tool_result(result),
            kind="tool",
            details=result,
        )

    return ChatResponse(
        reply=str(result),
        kind="assistant",
    )


@router.delete(
    "/session",
    response_model=SessionResponse
)
async def clear_session(request: Request):
    center = request.app.state.command_center
    command_lock = request.app.state.command_lock

    async with command_lock:
        center.ai.clear()

    return SessionResponse(cleared=True)


def create_app(
    command_center=None,
    ollama_runtime=None,
    session_store=None,
):
    @asynccontextmanager
    async def lifespan(app):
        app.state.command_center = (
            command_center
            if command_center is not None
            else CommandCenter()
        )
        app.state.command_lock = asyncio.Lock()
        app.state.active_sessions = set()
        app.state.session_store = session_store or SessionStore(os.getenv("SENTINEL_DATA_DIR", BASE_DIR / "data"))
        app.state.ollama_runtime = (
            ollama_runtime
            if ollama_runtime is not None
            else get_ollama_runtime()
        )
        yield

    app = FastAPI(
        title=f"{NAME} Interface",
        version=VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "127.0.0.1",
            "localhost",
            "testserver",
        ],
    )

    app.include_router(router)
    app.include_router(conversations_router)
    app.include_router(voice_router)
    app.include_router(agent_router)
    app.include_router(molecular_router)
    app.include_router(models_router)
    app.mount(
        "/static",
        StaticFiles(directory=WEB_DIR),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    async def interface():
        return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
