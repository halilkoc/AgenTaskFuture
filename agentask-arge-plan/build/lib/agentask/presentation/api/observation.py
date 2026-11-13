"""Gözlem, hedef çözümü, vurgulama ve manuel seçim uçları. Hiçbiri sayfaya iş etkisi oluşturmaz."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import Forbidden
from agentask.application.services.observation import caption_for
from agentask.domain.identity import Capability, Principal
from agentask.domain.observation import ObservedControl, PickEvent, ScanStatus, Snapshot
from agentask.domain.targeting import Resolution, TargetSpec
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/sessions/{session_id}", tags=["observation"])


async def _authorized(principal: PrincipalDep) -> Principal:
    if not (principal.can(Capability.DESIGN_CATALOG) or principal.can(Capability.USE_ASSISTANT)):
        raise Forbidden()
    return principal


Authorized = Annotated[Principal, Depends(_authorized)]


class NavigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)


class NavigateResponse(BaseModel):
    url: str


class ContextOut(BaseModel):
    kind: str
    name: str | None
    key: str | None


class ControlOut(BaseModel):
    candidate_id: str
    kind: str
    role: str
    label: str | None
    accessible_name: str | None
    visible: bool
    enabled: bool
    sensitive: bool
    has_value: bool
    selected_text: str | None
    options: list[str]
    contexts: list[ContextOut]
    frame_ref: str
    frame_titles: list[str]
    caption: str

    @classmethod
    def of(cls, c: ObservedControl) -> ControlOut:
        return cls(
            candidate_id=c.candidate_id,
            kind=c.kind.value,
            role=c.role,
            label=c.label,
            accessible_name=c.accessible_name,
            visible=c.visible,
            enabled=c.enabled,
            sensitive=c.sensitive,
            has_value=c.has_value,
            selected_text=c.selected_text,
            options=list(c.options),
            contexts=[ContextOut(kind=x.kind, name=x.name, key=x.key) for x in c.contexts],
            frame_ref=c.frame_ref,
            frame_titles=list(c.frame_titles),
            caption=caption_for(c),
        )


class FrameOut(BaseModel):
    frame_ref: str
    parent_ref: str | None
    title: str | None
    origin: str | None
    path: str | None
    depth: int
    status: str
    reason: str | None
    detail_scanned: bool
    control_count: int


class SnapshotOut(BaseModel):
    snapshot_revision: str
    coverage: str
    frames: list[FrameOut]
    controls: list[ControlOut]

    @classmethod
    def of(cls, s: Snapshot) -> SnapshotOut:
        incomplete = [f for f in s.frames if f.status is not ScanStatus.COMPLETE]
        return cls(
            snapshot_revision=s.revision,
            coverage="complete" if not incomplete else "incomplete",
            frames=[
                FrameOut(
                    frame_ref=f.frame_ref,
                    parent_ref=f.parent_ref,
                    title=f.title,
                    origin=f.origin,
                    path=f.path,
                    depth=f.depth,
                    status=f.status.value,
                    reason=f.reason,
                    detail_scanned=f.detail_scanned,
                    control_count=f.control_count,
                )
                for f in s.frames
            ],
            controls=[ControlOut.of(c) for c in s.controls],
        )


class ResolutionOut(BaseModel):
    outcome: str
    reason: str
    snapshot_revision: str
    candidate_id: str | None
    candidates: list[dict[str, Any]]
    coverage: dict[str, Any]
    explanation: str

    @classmethod
    def of(cls, r: Resolution) -> ResolutionOut:
        return cls.model_validate(r.to_dict())


class HighlightOut(BaseModel):
    candidate_id: str
    caption: str


class PickOut(BaseModel):
    candidate_id: str | None
    snapshot_revision: str | None
    reason: str
    control: ControlOut | None


class SelectionOut(BaseModel):
    selected: bool
    pick: PickOut | None


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(
    session_id: str, body: NavigateRequest, p: Authorized, c: ContainerDep
) -> NavigateResponse:
    return NavigateResponse(url=await c.observation.navigate(p.user_id, session_id, body.url))


@router.post("/observe", response_model=SnapshotOut)
async def observe(session_id: str, p: Authorized, c: ContainerDep) -> SnapshotOut:
    return SnapshotOut.of(await c.observation.observe(p.user_id, session_id))


@router.post("/resolve", response_model=ResolutionOut)
async def resolve(session_id: str, spec: TargetSpec, p: Authorized, c: ContainerDep) -> ResolutionOut:
    return ResolutionOut.of(await c.observation.resolve(p.user_id, session_id, spec))


@router.post("/candidates/{candidate_id}/highlight", response_model=HighlightOut)
async def highlight(session_id: str, candidate_id: str, p: Authorized, c: ContainerDep) -> HighlightOut:
    control = await c.observation.highlight(p.user_id, session_id, candidate_id)
    return HighlightOut(candidate_id=candidate_id, caption=caption_for(control))


@router.delete("/highlight", status_code=204)
async def clear_highlight(session_id: str, p: Authorized, c: ContainerDep) -> Response:
    await c.observation.clear_highlight(p.user_id, session_id)
    return Response(status_code=204)


@router.post("/picker/start", status_code=204)
async def picker_start(session_id: str, p: Authorized, c: ContainerDep) -> Response:
    await c.observation.start_picker(p.user_id, session_id)
    return Response(status_code=204)


@router.post("/picker/stop", status_code=204)
async def picker_stop(session_id: str, p: Authorized, c: ContainerDep) -> Response:
    await c.observation.stop_picker(p.user_id, session_id)
    return Response(status_code=204)


@router.get("/picker/selection", response_model=SelectionOut)
async def picker_selection(
    session_id: str, p: Authorized, c: ContainerDep, wait_ms: Annotated[int, Query(ge=0)] = 0
) -> SelectionOut:
    event: PickEvent | None = await c.observation.wait_pick(p.user_id, session_id, wait_ms)
    if event is None:
        return SelectionOut(selected=False, pick=None)
    snapshot = c.observation.current_snapshot(p.user_id, session_id)
    control = snapshot.control(event.candidate_id) if snapshot and event.candidate_id else None
    return SelectionOut(
        selected=True,
        pick=PickOut(
            candidate_id=event.candidate_id,
            snapshot_revision=event.snapshot_revision,
            reason=event.reason,
            control=ControlOut.of(control) if control else None,
        ),
    )
