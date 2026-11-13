from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from agentask.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"]


class ComponentStatus(BaseModel):
    name: str
    required: bool
    status: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    components: list[ComponentStatus]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(container: ContainerDep, response: Response) -> ReadyResponse:
    llm = container.llm.availability()
    components = [
        # LLM kapalı/erişilemez olması readiness'i bozmaz (docs/08).
        ComponentStatus(name="llm", required=False, status="available" if llm.available else llm.reason),
        ComponentStatus(name="identity", required=True, status=container.identity.source),
    ]
    if container.catalog_store is not None:
        ok = await container.catalog_store.ping()
        components.append(
            ComponentStatus(name="catalog_mongo", required=True, status="available" if ok else "unavailable")
        )
    not_ready = any(c.required and c.status in {"unconfigured", "unavailable"} for c in components)
    if not_ready:
        response.status_code = 503
    return ReadyResponse(status="not_ready" if not_ready else "ready", components=components)
