"""Geçici admin girişi uçları (AUTH_MODE=local_admin). Diğer kimlik kiplerinde bulunmaz (404)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from agentask.application.errors import ApplicationError
from agentask.infrastructure.identity.local_admin import COOKIE_NAME
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


class _NotAvailable(ApplicationError):
    code = "not_found"
    safe_message = "Kaynak bulunamadı."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", status_code=204)
async def login(body: LoginRequest, request: Request, c: ContainerDep) -> Response:
    if c.admin_auth is None:
        raise _NotAvailable()
    client = request.client.host if request.client else None
    token = await c.admin_auth.login(body.username, body.password, client)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=c.admin_auth.session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=c.settings.admin_cookie_secure,
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, _: PrincipalDep, c: ContainerDep) -> Response:
    if c.admin_auth is None:
        raise _NotAvailable()
    c.admin_auth.logout(request.headers.get("cookie"))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return response
