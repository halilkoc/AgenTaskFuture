"""Değişiklik/etki ve çalışma metrikleri uçları."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.domain.identity import Capability, Principal
from agentask.domain.metrics import run_metrics
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(tags=["changes"])


async def _designer(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.DESIGN_CATALOG):
        raise Forbidden()
    return principal


async def _any_role(principal: PrincipalDep) -> Principal:
    if not principal.capabilities:
        raise Forbidden()
    return principal


Designer = Annotated[Principal, Depends(_designer)]
AnyRole = Annotated[Principal, Depends(_any_role)]


class Analyze(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    operation_id: str


class Dependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter_kinds: list[str] = Field(default_factory=list, max_length=10)
    action_ids: list[str] = Field(default_factory=list, max_length=20)


class Repair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str
    element_ids: list[str] = Field(min_length=1, max_length=50)


@router.get("/api/changes/operations")
async def operations(p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.impact.operations()


@router.post("/api/changes/analyze")
async def analyze(body: Analyze, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.impact.analyze(p.user_id, body.session_id, body.operation_id)


@router.post("/api/changes/dependency-impact")
async def dependency(body: Dependency, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.impact.dependency_impact(body.adapter_kinds, body.action_ids)


@router.post("/api/changes/repair", status_code=201)
async def repair(body: Repair, p: Designer, c: ContainerDep) -> dict[str, Any]:
    draft = await c.impact.repair(p.user_id, body.operation_id, body.element_ids)
    return {
        "draft_id": draft.draft_id,
        "operation_id": draft.operation_id,
        "issues": draft.validation_issues(),
    }


@router.get("/api/metrics/runs")
async def metrics(p: AnyRole, c: ContainerDep) -> dict[str, Any]:
    return run_metrics(c.runs.list_runs(p.user_id))
