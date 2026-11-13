"""Onay, yayın ve yayımlanmış katalog inceleme uçları (PUBLISH_CATALOG / görüntüleme)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import DependencyUnavailable, Forbidden
from agentask.application.services.publishing import PublishService
from agentask.domain.identity import Capability, Principal
from agentask.domain.release import ReleaseManifest
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(tags=["catalogs"])


async def _publisher(principal: PrincipalDep) -> Principal:
    if not principal.can(Capability.PUBLISH_CATALOG):
        raise Forbidden()
    return principal


async def _viewer(principal: PrincipalDep) -> Principal:
    if not (principal.capabilities):
        raise Forbidden()
    return principal


Publisher = Annotated[Principal, Depends(_publisher)]
Viewer = Annotated[Principal, Depends(_viewer)]


def _service(c: Any) -> PublishService:
    if c.publishing is None:
        raise DependencyUnavailable("Katalog yayını devre dışı (CATALOG_BACKEND=disabled).")
    service: PublishService = c.publishing
    return service


class Approve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int


class Publish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=64)


def _release(m: ReleaseManifest, active_id: str | None) -> dict[str, Any]:
    data = m.model_dump(mode="json")
    data["active"] = m.release_id == active_id
    return data


@router.post("/api/drafts/{draft_id}/approve")
async def approve(draft_id: str, body: Approve, p: Publisher, c: ContainerDep) -> dict[str, Any]:
    draft = _service(c).approve(p.user_id, draft_id, body.expected_revision)
    return {
        "draft_id": draft.draft_id,
        "revision": draft.revision,
        "approval": draft.approval.model_dump(mode="json") if draft.approval else None,
    }


@router.post("/api/drafts/{draft_id}/publish", status_code=201)
async def publish(draft_id: str, body: Publish, p: Publisher, c: ContainerDep) -> dict[str, Any]:
    manifest = await _service(c).publish(p.user_id, draft_id, body.request_id)
    return _release(manifest, manifest.release_id)


@router.get("/api/catalogs/releases")
async def releases(
    p: Viewer, c: ContainerDep, application_id: Annotated[str, Query()] = "lab"
) -> dict[str, Any]:
    service = _service(c)
    active = await service.active_release(application_id)
    active_id = active.release_id if active else None
    return {
        "application_id": application_id,
        "environment": service.environment,
        "active_release_id": active_id,
        "releases": [_release(r, active_id) for r in await service.releases(application_id)],
    }


@router.get("/api/catalogs/releases/{release_id}")
async def release(release_id: str, p: Viewer, c: ContainerDep) -> dict[str, Any]:
    service = _service(c)
    manifest = await service.release(release_id)
    if manifest is None:
        raise DependencyUnavailable("Yayın bulunamadı.")
    active = await service.active_release(manifest.application_id)
    ops = []
    for entry in manifest.operations:
        rev = await service.operation(manifest.application_id, entry)
        ops.append(
            {
                **entry.model_dump(),
                "title": rev.definition.get("title") if rev else None,
                "steps": len(rev.definition.get("steps", [])) if rev else None,
            }
        )
    return {**_release(manifest, active.release_id if active else None), "operation_details": ops}
