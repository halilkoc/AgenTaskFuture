"""İşlem Asistanı uçları (USE_ASSISTANT). Plan sunucuda yayından derlenir; istemci planı kabul edilmez."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.application.services.assistant import interpretation_dict
from agentask.domain.identity import Capability, Principal
from agentask.presentation.api.runs import RunOut
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


async def _operator(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.USE_ASSISTANT):
        raise Forbidden()
    return principal


Operator = Annotated[Principal, Depends(_operator)]


class InterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2000)
    use_model: bool = False


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_id: str
    operation_id: str
    arguments: dict[str, str] = Field(default_factory=dict)


class ExecuteRequest(PlanRequest):
    session_id: str
    request_id: str = Field(min_length=1, max_length=64)
    acknowledge_effect: bool = False


@router.get("/catalog")
async def catalog(p: Operator, c: ContainerDep) -> dict[str, Any]:
    ops = await c.assistant.catalog()
    return {"llm_available": c.llm.availability().available, "operations": [o.model_dump() for o in ops]}


@router.post("/interpret")
async def interpret(body: InterpretRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return interpretation_dict(await c.assistant.interpret(p.user_id, body.prompt, body.use_model))


@router.post("/preview")
async def preview(body: PlanRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return await c.assistant.preview(p.user_id, body.release_id, body.operation_id, body.arguments)


@router.post("/execute", status_code=202, response_model=RunOut)
async def execute(body: ExecuteRequest, p: Operator, c: ContainerDep) -> RunOut:
    run = await c.assistant.execute(
        p.user_id,
        body.session_id,
        body.release_id,
        body.operation_id,
        body.arguments,
        body.request_id,
        body.acknowledge_effect,
    )
    return RunOut.of(run)


class CompositeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: dict[str, Any]


class CompositeExecute(CompositeRequest):
    session_id: str
    release_id: str
    request_id: str = Field(min_length=1, max_length=64)
    acknowledge_effect: bool = False


@router.post("/composite/preview")
async def composite_preview(body: CompositeRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return await c.assistant.composite_preview(p.user_id, body.plan)


@router.post("/composite/execute", status_code=202, response_model=RunOut)
async def composite_execute(body: CompositeExecute, p: Operator, c: ContainerDep) -> RunOut:
    run = await c.assistant.composite_execute(p.user_id, body.session_id, body.release_id, body.plan,
                                              body.request_id, body.acknowledge_effect)
    return RunOut.of(run)
