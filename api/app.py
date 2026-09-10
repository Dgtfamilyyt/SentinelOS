import asyncio
import json
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
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    center = request.app.state.command_center
    command_lock = request.app.state.command_lock

    try:
        async with command_lock:
            result = await run_in_threadpool(
                center.process,
                payload.message
            )

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
    ollama_runtime=None
):
    @asynccontextmanager
    async def lifespan(app):
        app.state.command_center = (
            command_center
            if command_center is not None
            else CommandCenter()
        )
        app.state.command_lock = asyncio.Lock()
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
