"""
api/agent.py
============
Agent API endpoints — expose the agentic loop over FastAPI.

Endpoints:
    POST   /api/agent/run       — submit a goal, get streaming SSE events
    GET    /api/agent/status    — current agent state
    POST   /api/agent/stop      — interrupt the running task
    POST   /api/agent/targets   — add an authorized lab target
    GET    /api/agent/targets   — list authorized targets

Streaming uses Server-Sent Events (text/event-stream).
"""

from __future__ import annotations

import json
import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from core.logger import logger


router = APIRouter(prefix="/api/agent")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    goal:    str  = Field(max_length=10_000)
    mode:    str  = "chat"
    context: dict = {}


class LabTargetRequest(BaseModel):
    label:   str
    targets: list[str]
    notes:   str = ""


class AgentStatusResponse(BaseModel):
    is_running:        bool
    active_task:       dict | None = None
    task_history_count:int


class StopResponse(BaseModel):
    stopped: bool


# ---------------------------------------------------------------------------
# Streaming SSE helper
# ---------------------------------------------------------------------------

def _event_stream(generator):
    """Convert an event generator to SSE text/event-stream format."""
    for event in generator:
        data = json.dumps(event, default=str)
        yield f"data: {data}\n\n"
    yield "data: {\"type\": \"stream_end\"}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
async def agent_run(payload: AgentRunRequest, request: Request):
    """
    Submit a goal to the agent and receive streaming execution events.

    Response: text/event-stream (Server-Sent Events)
    Each event is a JSON object with a ``type`` field.
    """
    center = request.app.state.command_center

    def _generate():
        yield from center.run_agent_stream(
            goal    = payload.goal,
            context = payload.context,
            mode    = payload.mode,
        )

    return StreamingResponse(
        _event_stream(_generate()),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/run/sync")
async def agent_run_sync(payload: AgentRunRequest, request: Request):
    """
    Submit a goal and wait for the final result (non-streaming).
    Suitable for simple programmatic use. Prefer /run for interactive use.
    """
    center = request.app.state.command_center
    result = await run_in_threadpool(
        center.run_agent,
        payload.goal,
        payload.context,
        payload.mode,
    )
    return result


@router.get("/status", response_model=AgentStatusResponse)
async def agent_status(request: Request):
    """Return the current agent state."""
    center = request.app.state.command_center
    state  = center.agent_state
    return AgentStatusResponse(
        is_running         = state["is_running"],
        active_task        = state.get("active_task"),
        task_history_count = state.get("task_history_count", 0),
    )


@router.post("/stop", response_model=StopResponse)
async def agent_stop(request: Request):
    """Request graceful stop of the running agent task."""
    center  = request.app.state.command_center
    stopped = await run_in_threadpool(center.stop_agent)
    return StopResponse(stopped=stopped)


@router.get("/targets")
async def list_targets(request: Request):
    """List currently authorized lab targets."""
    center = request.app.state.command_center
    return {"targets": center.authorized_targets}


@router.post("/targets")
async def add_target(payload: LabTargetRequest, request: Request):
    """Add an authorized lab target at runtime."""
    center = request.app.state.command_center
    await run_in_threadpool(
        center.add_lab_target,
        payload.label,
        payload.targets,
        payload.notes,
    )
    return {"added": True, "label": payload.label, "targets": payload.targets}
