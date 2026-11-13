from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agentask.presentation.dependencies import PrincipalDep

router = APIRouter(prefix="/api", tags=["identity"])


class MeResponse(BaseModel):
    user_id: str
    display_name: str
    roles: list[str]
    capabilities: list[str]
    identity_source: str


@router.get("/me", response_model=MeResponse)
async def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        display_name=principal.display_name,
        roles=sorted(r.value for r in principal.roles),
        capabilities=sorted(c.value for c in principal.capabilities),
        identity_source=principal.identity_source,
    )
