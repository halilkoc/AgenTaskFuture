"""Katalog Tasarımcısı uçları (docs/09 drafts). Yalnız taslak deposuna yazar; yayın P5'tedir."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.domain.catalog import OperationDraft
from agentask.domain.identity import Capability, Principal
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


async def _designer(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.DESIGN_CATALOG):
        raise Forbidden()
    return principal


Designer = Annotated[Principal, Depends(_designer)]


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateDraft(_Req):
    application_id: str
    operation_id: str
    title: str
    description: str = ""
    intent_phrases: list[str] = Field(default_factory=list)


class Revisioned(_Req):
    expected_revision: int


class PatchDraft(Revisioned):
    title: str | None = None
    description: str | None = None
    intent_phrases: list[str] | None = None


class AddParameter(Revisioned):
    name: str
    title: str
    max_length: int
    required: bool = True
    source: str
    constant: str | None = None
    secret_ref: str | None = None
    prior_step: int | None = None


class AddStep(Revisioned):
    intent_text: str = Field(min_length=1, max_length=500)


class Propose(_Req):
    session_id: str


class SelectTarget(Revisioned):
    session_id: str
    candidate_id: str
    element_id: str
    meaning: str
    provenance: Literal["observed", "human_verified"] = "observed"
    include_region: bool = True


class PatchStep(Revisioned):
    op: str | None = None
    value_template: str | None = None
    choice_template: str | None = None
    key_template: str | None = None
    navigation: Literal["none", "paged", "scroll"] | None = None
    action_id: str | None = None
    action_params: dict[str, str] | None = None
    success_check: Literal["auto", "none"] | None = None
    standard_text: str | None = None


class ConfirmStep(Revisioned):
    meaning: bool
    target: bool
    effect: bool
    params: bool


class Trial(Revisioned):
    session_id: str
    args: dict[str, str] = Field(default_factory=dict)
    acknowledge_effect: bool = False


class FreshTest(Revisioned):
    args: dict[str, str] = Field(default_factory=dict)
    entry_url: str = Field(min_length=1, max_length=2048)


def _out(c: Any, draft: OperationDraft) -> dict[str, Any]:
    actions = c.designer.actions
    data = draft.model_dump(mode="json")
    data["content_hash"] = draft.content_hash()
    data["issues"] = draft.validation_issues(actions)
    for step, raw in zip(draft.steps, data["steps"], strict=True):
        raw["effect"] = step.effect(actions)
    return data


@router.post("", status_code=201)
async def create(body: CreateDraft, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(c, c.designer.create_draft(p.user_id, **body.model_dump()))


@router.get("")
async def list_drafts(p: Designer, c: ContainerDep) -> list[dict[str, Any]]:
    return [
        {
            "draft_id": d.draft_id,
            "operation_id": d.operation_id,
            "title": d.title,
            "revision": d.revision,
            "steps": len(d.steps),
            "ready": d.is_ready_for_review,
            "updated_at": d.updated_at.isoformat(),
        }
        for d in c.designer.list_drafts(p.user_id)
    ]


@router.get("/{draft_id}")
async def get_draft(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(c, c.designer.get(p.user_id, draft_id))


@router.patch("/{draft_id}")
async def patch_draft(draft_id: str, body: PatchDraft, p: Designer, c: ContainerDep) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.update_meta(p.user_id, draft_id, body.expected_revision, **fields))


@router.post("/{draft_id}/parameters")
async def add_parameter(draft_id: str, body: AddParameter, p: Designer, c: ContainerDep) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.add_parameter(p.user_id, draft_id, body.expected_revision, **fields))


@router.post("/{draft_id}/steps")
async def add_step(draft_id: str, body: AddStep, p: Designer, c: ContainerDep) -> dict[str, Any]:
    draft, _ = c.designer.add_step(p.user_id, draft_id, body.expected_revision, body.intent_text)
    return _out(c, draft)


@router.delete("/{draft_id}/steps/{step_id}")
async def remove_step(
    draft_id: str, step_id: str, p: Designer, c: ContainerDep, expected_revision: Annotated[int, Query()]
) -> dict[str, Any]:
    return _out(c, c.designer.remove_step(p.user_id, draft_id, expected_revision, step_id))


@router.post("/{draft_id}/steps/{step_id}/propose")
async def propose(draft_id: str, step_id: str, body: Propose, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return await c.designer.propose_targets(p.user_id, draft_id, step_id, body.session_id)


@router.post("/{draft_id}/steps/{step_id}/select-target")
async def select_target(
    draft_id: str, step_id: str, body: SelectTarget, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    draft = await c.designer.select_target(
        p.user_id,
        draft_id,
        body.expected_revision,
        step_id,
        body.session_id,
        body.candidate_id,
        element_id=body.element_id,
        meaning=body.meaning,
        provenance=body.provenance,
        include_region=body.include_region,
    )
    return _out(c, draft)


@router.patch("/{draft_id}/steps/{step_id}")
async def patch_step(
    draft_id: str, step_id: str, body: PatchStep, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    fields = body.model_dump(exclude={"expected_revision"}, exclude_none=True)
    return _out(c, c.designer.configure_step(p.user_id, draft_id, body.expected_revision, step_id, **fields))


@router.post("/{draft_id}/steps/{step_id}/confirm")
async def confirm(
    draft_id: str, step_id: str, body: ConfirmStep, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    return _out(
        c,
        c.designer.confirm_step(
            p.user_id,
            draft_id,
            body.expected_revision,
            step_id,
            meaning=body.meaning,
            target=body.target,
            effect=body.effect,
            params=body.params,
        ),
    )


@router.post("/{draft_id}/steps/{step_id}/trial")
async def trial(draft_id: str, step_id: str, body: Trial, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(
        c,
        await c.designer.trial_step(
            p.user_id,
            draft_id,
            body.expected_revision,
            step_id,
            body.session_id,
            body.args,
            acknowledge_effect=body.acknowledge_effect,
        ),
    )


@router.post("/{draft_id}/steps/{step_id}/confirm-outcome")
async def confirm_outcome(
    draft_id: str, step_id: str, body: Revisioned, p: Designer, c: ContainerDep
) -> dict[str, Any]:
    return _out(c, c.designer.confirm_outcome(p.user_id, draft_id, body.expected_revision, step_id))


@router.post("/{draft_id}/fresh-test")
async def fresh_test(draft_id: str, body: FreshTest, p: Designer, c: ContainerDep) -> dict[str, Any]:
    return _out(
        c,
        await c.designer.fresh_session_test(
            p.user_id, draft_id, body.expected_revision, body.args, body.entry_url
        ),
    )


@router.post("/{draft_id}/validate")
async def validate(draft_id: str, p: Designer, c: ContainerDep) -> dict[str, Any]:
    issues = c.designer.validate(p.user_id, draft_id)
    return {"issues": issues, "ready": not issues}
