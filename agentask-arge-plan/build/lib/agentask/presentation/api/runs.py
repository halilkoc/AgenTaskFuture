"""İşlem çalıştırma uçları: onaylı aksiyon listesi, run oluşturma (202), durum, iptal ve devam."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.domain.identity import Capability, Principal
from agentask.domain.runtime import Run, RunStatus
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(tags=["runs"])

OUTCOME_LABELS = {
    RunStatus.CREATED: "Hazırlanıyor",
    RunStatus.RUNNING: "Çalışıyor",
    RunStatus.CANCEL_REQUESTED: "İptal talep edildi",
    RunStatus.COMPLETED: "Başarılı",
    RunStatus.FAILED: "Başarısız",
    RunStatus.OUTCOME_UNKNOWN: "Belirsiz",
    RunStatus.PAUSED_SESSION: "Duraklatıldı",
    RunStatus.PAUSED_AMBIGUOUS: "Duraklatıldı",
    RunStatus.PAUSED_BLOCKED: "Duraklatıldı",
    RunStatus.CANCELLED: "İptal edildi",
}
COMMANDS = [
    "read",
    "ensure_value",
    "ensure_choice",
    "activate_tab",
    "find_record",
    "invoke_approved_action",
    "assert_condition",
]


async def _authorized(principal: PrincipalDep) -> Principal:
    if not (principal.can(Capability.DESIGN_CATALOG) or principal.can(Capability.USE_ASSISTANT)):
        raise Forbidden()
    return principal


Authorized = Annotated[Principal, Depends(_authorized)]


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=64)
    steps: list[dict[str, Any]] = Field(max_length=500)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)


class StepOut(BaseModel):
    index: int
    command: dict[str, Any]
    state: str
    attempts: int
    error_class: str | None
    message: str | None
    result: dict[str, Any]
    recoveries: list[str]
    dispatched: bool


class RunOut(BaseModel):
    run_id: str
    session_id: str
    request_id: str
    status: str
    status_reason: str | None
    outcome_label: str
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    binding: dict[str, Any] | None = None
    steps: list[StepOut]

    @classmethod
    def of(cls, run: Run) -> RunOut:
        return cls(
            run_id=run.run_id,
            session_id=run.session_id,
            request_id=run.request_id,
            status=run.status.value,
            status_reason=run.status_reason,
            outcome_label=OUTCOME_LABELS[run.status],
            cancel_requested=run.cancel_requested,
            created_at=run.created_at,
            updated_at=run.updated_at,
            binding=run.binding,
            steps=[
                StepOut(
                    index=s.index,
                    command=s.command,
                    state=s.state.value,
                    attempts=s.attempts,
                    error_class=s.error_class,
                    message=s.message,
                    result=s.result,
                    recoveries=s.recoveries,
                    dispatched=s.intent is not None and s.state.value != "pending",
                )
                for s in run.steps
            ],
        )


@router.get("/api/actions")
async def list_actions(p: Authorized, c: ContainerDep) -> dict[str, Any]:
    actions = c.runs.actions.actions.values()
    return {
        "commands": COMMANDS,
        "actions": [
            {
                "action_id": a.action_id,
                "title": a.title,
                "effect": a.effect,
                "retry_safe": a.retry_safe,
                "params": [{"name": x.name, "title": x.title, "max_length": x.max_length} for x in a.params],
                "target": a.target.model_dump(mode="json", exclude_none=True),
            }
            for a in actions
        ],
    }


@router.post("/api/runs", status_code=202, response_model=RunOut)
async def create_run(body: CreateRunRequest, p: Authorized, c: ContainerDep) -> RunOut:
    return RunOut.of(await c.runs.create(p.user_id, body.session_id, body.request_id, body.steps))


@router.get("/api/runs", response_model=list[RunOut])
async def list_runs(p: Authorized, c: ContainerDep) -> list[RunOut]:
    return [RunOut.of(r) for r in c.runs.list_runs(p.user_id)[:50]]


@router.get("/api/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: str, p: Authorized, c: ContainerDep) -> RunOut:
    return RunOut.of(c.runs.get(p.user_id, run_id))


@router.post("/api/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, p: Authorized, c: ContainerDep) -> RunOut:
    return RunOut.of(await c.runs.cancel(p.user_id, run_id))


@router.post("/api/runs/{run_id}/resume", status_code=202, response_model=RunOut)
async def resume_run(run_id: str, body: ResumeRequest, p: Authorized, c: ContainerDep) -> RunOut:
    return RunOut.of(await c.runs.resume(p.user_id, run_id, body.session_id))
