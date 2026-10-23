"""
api/models.py
=============
Model Hub & Provider API endpoints for SentinelOS.

Exposes clean, provider-agnostic endpoints for the frontend to:
  1. Inspect runtime availability (Ollama, OmniRoute, etc.)
  2. Discover actual installed models (empty list if none installed)
  3. Query model readiness independently of SentinelOS backend status
  4. Select and assign models to task roles
  5. Maintain backward-compatible schema for SentinelOS legacy web interface
"""

from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/models", tags=["models"])


class ModelSelectRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="general", max_length=50)


class ModelSelectResponse(BaseModel):
    success: bool
    role: str
    model: str
    message: str


class RuntimeStatusResponse(BaseModel):
    name: str
    status: Literal["available", "unavailable", "not_configured"]
    endpoint: str | None = None
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ModelInventoryResponse(BaseModel):
    online: bool
    models: list[dict[str, Any]]
    provider: str
    runtime: RuntimeStatusResponse
    model_status: Literal["ready", "loading", "unavailable", "not_configured"]
    installed_models: list[dict[str, Any]]
    active_models: dict[str, str | None]
    roles: list[str]


class ModelStatusSummaryResponse(BaseModel):
    runtime_status: Literal["available", "unavailable", "not_configured"]
    model_status: Literal["ready", "loading", "unavailable", "not_configured"]
    models_count: int
    provider: str
    active_model: str | None = None
    message: str = ""


@router.get("", response_model=ModelInventoryResponse)
async def list_models(request: Request):
    """Return model runtime status and real installed model inventory."""
    center = getattr(request.app.state, "command_center", None)
    model_router = getattr(getattr(center, "ai", None), "router", None)

    if model_router is None:
        from models.router import ModelRouter
        model_router = ModelRouter()

    provider = model_router.get_provider()
    runtime_status = provider.check_runtime()
    installed = provider.list_models()

    if runtime_status.status != "available":
        model_status = "unavailable" if runtime_status.status == "unavailable" else "not_configured"
    elif not installed:
        model_status = "not_configured"
    else:
        model_status = "ready"

    registry = model_router.registry
    active_models = {
        role: registry.model_name(role)
        for role in registry.roles()
    }

    installed_dicts = [m.to_dict() for m in installed]
    legacy_models = [
        {"name": m["name"], "installed": True, "backend": provider.name}
        for m in installed_dicts
    ]

    return ModelInventoryResponse(
        online=runtime_status.status == "available",
        models=legacy_models,
        provider=provider.name,
        runtime=RuntimeStatusResponse(
            name=runtime_status.name,
            status=runtime_status.status,
            endpoint=runtime_status.endpoint,
            message=runtime_status.message,
            details=runtime_status.details,
        ),
        model_status=model_status,
        installed_models=installed_dicts,
        active_models=active_models,
        roles=registry.roles(),
    )


@router.get("/status", response_model=ModelStatusSummaryResponse)
async def model_status_summary(request: Request):
    """Quick model status summary for UI polling and readiness indicators."""
    center = getattr(request.app.state, "command_center", None)
    model_router = getattr(getattr(center, "ai", None), "router", None)

    if model_router is None:
        from models.router import ModelRouter
        model_router = ModelRouter()

    provider = model_router.get_provider()
    runtime_status = provider.check_runtime()
    installed = provider.list_models()

    if runtime_status.status != "available":
        model_status = "unavailable" if runtime_status.status == "unavailable" else "not_configured"
        message = runtime_status.message or "AI model runtime is unavailable."
    elif not installed:
        model_status = "not_configured"
        message = "AI models not configured yet. Runtime is ready, but no models are installed."
    else:
        model_status = "ready"
        message = f"{len(installed)} model(s) available."

    active_model = model_router.choose("chat") if model_status == "ready" else None

    return ModelStatusSummaryResponse(
        runtime_status=runtime_status.status,
        model_status=model_status,
        models_count=len(installed),
        provider=provider.name,
        active_model=active_model,
        message=message,
    )


@router.post("/select", response_model=ModelSelectResponse)
async def select_model_role(payload: ModelSelectRequest, request: Request):
    """Assign an installed model to a specific task role."""
    center = getattr(request.app.state, "command_center", None)
    model_router = getattr(getattr(center, "ai", None), "router", None)

    if model_router is None:
        from models.router import ModelRouter
        model_router = ModelRouter()

    provider = model_router.get_provider()
    installed = provider.list_models()
    installed_ids = {m.id for m in installed} | {m.name for m in installed}

    if installed and payload.model not in installed_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{payload.model}' is not in the installed model inventory.",
        )

    if hasattr(model_router.registry, "set_role_model"):
        model_router.registry.set_role_model(payload.role, payload.model)

    return ModelSelectResponse(
        success=True,
        role=payload.role,
        model=payload.model,
        message=f"Role '{payload.role}' assigned to model '{payload.model}'.",
    )
