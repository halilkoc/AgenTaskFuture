"""İşlem Asistanı uçları (USE_ASSISTANT). Plan sunucuda yayından derlenir; istemci planı kabul edilmez.

Her istek yapılandırılmış bir uygulama kimliği taşır (AUTOMATION_APPLICATIONS_JSON); katalog, plan ve run o
uygulamanın yayınıyla kapsamlanır. Listede olmak yetki vermez: rol kontrolü ayrıca yapılır.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.application.services.assistant import interpretation_dict
from agentask.domain.applications import APPLICATION_ID_PATTERN
from agentask.domain.identity import Capability, Principal
from agentask.presentation.api.runs import RunOut
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


async def _operator(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.USE_ASSISTANT):
        raise Forbidden()
    return principal


Operator = Annotated[Principal, Depends(_operator)]
ApplicationId = Annotated[str, Field(pattern=APPLICATION_ID_PATTERN)]


class _Scoped(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: ApplicationId


class InterpretRequest(_Scoped):
    prompt: str = Field(min_length=1, max_length=2000)
    # None: kurum politikası (LLM_ENABLED ve model erişilebilirliği) karar verir; çalışan seçmez. Model
    # önerisi her zaman onay ister ve yalnız yayındaki onaylı işlemlere referans verebilir. False: bu
    # istekte model kullanılmaz.
    use_model: bool | None = None


class PlanRequest(_Scoped):
    release_id: str
    operation_id: str
    arguments: dict[str, str] = Field(default_factory=dict)


class ExecuteRequest(PlanRequest):
    session_id: str
    request_id: str = Field(min_length=1, max_length=64)
    acknowledge_effect: bool = False


class ParameterOptionsRequest(_Scoped):
    release_id: str
    operation_id: str
    parameter: str = Field(min_length=1, max_length=61)
    session_id: str
    open_list: bool = False


@router.post("/parameter-options")
async def parameter_options(body: ParameterOptionsRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    """Açık ekrandaki güncel seçenekler. Hedef yayımlanmış tanımdan gelir; seçim yapılmaz."""
    target = await c.assistant.choice_target(
        body.release_id, body.operation_id, body.parameter, body.application_id
    )
    return await c.observation.choice_options(p.user_id, body.session_id, target, body.open_list)


@router.get("/catalog")
async def catalog(
    p: Operator, c: ContainerDep, application_id: Annotated[str, Query(pattern=APPLICATION_ID_PATTERN)]
) -> dict[str, Any]:
    ops = await c.assistant.catalog(application_id)
    return {
        "application_id": application_id,
        "llm_available": c.llm.availability().available,
        "operations": [o.model_dump() for o in ops],
    }


@router.post("/interpret")
async def interpret(body: InterpretRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    use_model = c.llm.availability().available if body.use_model is None else body.use_model
    return interpretation_dict(
        await c.assistant.interpret(p.user_id, body.prompt, use_model, body.application_id)
    )


@router.post("/preview")
async def preview(body: PlanRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return await c.assistant.preview(
        p.user_id, body.release_id, body.operation_id, body.arguments, body.application_id
    )


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
        body.application_id,
    )
    return RunOut.of(run)


class CompositeRequest(_Scoped):
    plan: dict[str, Any]


class CompositeExecute(CompositeRequest):
    session_id: str
    release_id: str
    request_id: str = Field(min_length=1, max_length=64)
    acknowledge_effect: bool = False


@router.post("/composite/preview")
async def composite_preview(body: CompositeRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return await c.assistant.composite_preview(p.user_id, body.plan, body.application_id)


@router.post("/composite/execute", status_code=202, response_model=RunOut)
async def composite_execute(body: CompositeExecute, p: Operator, c: ContainerDep) -> RunOut:
    run = await c.assistant.composite_execute(
        p.user_id,
        body.session_id,
        body.release_id,
        body.plan,
        body.request_id,
        body.acknowledge_effect,
        body.application_id,
    )
    return RunOut.of(run)


# ---- F: modelin yayımlanmış işlemlerden sıralı plan önerisi (öneri; yürütme ayrı ve açık) ----------


class ProposeRequest(_Scoped):
    prompt: str = Field(min_length=1, max_length=2000)


class SequenceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=61)
    arguments: dict[str, str] = Field(default_factory=dict)


class SequenceRequest(_Scoped):
    release_id: str
    steps: list[SequenceStep] = Field(min_length=1, max_length=5)


class SequenceExecute(SequenceRequest):
    session_id: str
    request_id: str = Field(min_length=1, max_length=64)
    acknowledge_effect: bool = False


@router.post("/plan/propose")
async def plan_propose(body: ProposeRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    return await c.assistant.propose_plan(p.user_id, body.prompt, body.application_id)


@router.post("/plan/preview")
async def plan_preview(body: SequenceRequest, p: Operator, c: ContainerDep) -> dict[str, Any]:
    steps = [s.model_dump() for s in body.steps]
    return await c.assistant.plan_preview(p.user_id, body.release_id, steps, body.application_id)


@router.post("/plan/execute", status_code=202, response_model=RunOut)
async def plan_execute(body: SequenceExecute, p: Operator, c: ContainerDep) -> RunOut:
    run = await c.assistant.plan_execute(
        p.user_id,
        body.session_id,
        body.release_id,
        [s.model_dump() for s in body.steps],
        body.request_id,
        body.acknowledge_effect,
        body.application_id,
    )
    return RunOut.of(run)
