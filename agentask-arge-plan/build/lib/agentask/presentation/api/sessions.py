from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel

from agentask.application.errors import Forbidden
from agentask.application.services.browser_sessions import SessionView
from agentask.domain.identity import Capability, Principal
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
    session_id: str
    owner_id: str
    created_at: datetime
    last_used_at: datetime
    busy_operation: str | None

    @classmethod
    def of(cls, view: SessionView) -> SessionResponse:
        return cls(
            session_id=view.session_id,
            owner_id=view.owner_id,
            created_at=view.created_at,
            last_used_at=view.last_used_at,
            busy_operation=view.busy_operation,
        )


def _require_browser_capability(principal: Principal) -> None:
    if not (principal.can(Capability.USE_ASSISTANT) or principal.can(Capability.DESIGN_CATALOG)):
        raise Forbidden()


@router.post("", status_code=201, response_model=SessionResponse)
async def open_session(principal: PrincipalDep, container: ContainerDep) -> SessionResponse:
    _require_browser_capability(principal)
    await container.sessions.reap_idle()
    return SessionResponse.of(await container.sessions.open(principal.user_id))


@router.get("", response_model=list[SessionResponse])
async def list_sessions(principal: PrincipalDep, container: ContainerDep) -> list[SessionResponse]:
    _require_browser_capability(principal)
    return [SessionResponse.of(v) for v in container.sessions.list(principal.user_id)]


@router.delete("/{session_id}", status_code=204)
async def close_session(session_id: str, principal: PrincipalDep, container: ContainerDep) -> Response:
    _require_browser_capability(principal)
    await container.sessions.close(principal.user_id, session_id)
    return Response(status_code=204)
