"""Rol kontrollü sayfalar. Yetki kontrolü backend'dedir; menü gizlemek yetki değildir."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from agentask.domain.identity import Capability, Principal
from agentask.presentation.api.public_config import build_public_config
from agentask.presentation.dependencies import ContainerDep, PrincipalDep, require

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(include_in_schema=False)


def _render(
    request: Request, name: str, container: ContainerDep, principal: Principal, **extra: object
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        name,
        {
            **extra,
            "principal": principal,
            "public_config": build_public_config(container),
            "can_assist": principal.can(Capability.USE_ASSISTANT),
            "can_design": principal.can(Capability.DESIGN_CATALOG),
        },
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, container: ContainerDep, principal: PrincipalDep) -> HTMLResponse:
    return _render(request, "index.html", container, principal)


@router.get("/assistant", response_class=HTMLResponse)
async def assistant(
    request: Request,
    container: ContainerDep,
    principal: Annotated[Principal, Depends(require(Capability.USE_ASSISTANT))],
) -> HTMLResponse:
    return _render(
        request,
        "assistant.html",
        container,
        principal,
        lab_origin=container.settings.lab_primary_origin,
        composition_enabled=container.settings.composition_enabled,
    )


@router.get("/designer", response_class=HTMLResponse)
async def designer(
    request: Request,
    container: ContainerDep,
    principal: Annotated[Principal, Depends(require(Capability.DESIGN_CATALOG))],
) -> HTMLResponse:
    return _render(
        request, "designer.html", container, principal, lab_origin=container.settings.lab_primary_origin
    )


@router.get("/designer/targets", response_class=HTMLResponse)
async def target_lab(
    request: Request,
    container: ContainerDep,
    principal: Annotated[Principal, Depends(require(Capability.DESIGN_CATALOG))],
) -> HTMLResponse:
    base_url = str(container.settings.target_base_url).rstrip("/")
    return _render(request, "target_lab.html", container, principal, target_base_url=base_url)


@router.get("/designer/runs", response_class=HTMLResponse)
async def run_lab(
    request: Request,
    container: ContainerDep,
    principal: Annotated[Principal, Depends(require(Capability.DESIGN_CATALOG))],
) -> HTMLResponse:
    settings = container.settings
    return _render(
        request,
        "run_lab.html",
        container,
        principal,
        target_base_url=str(settings.target_base_url).rstrip("/"),
        lab_origin=settings.lab_primary_origin,
    )


@router.get("/catalogs", response_class=HTMLResponse)
async def catalogs(request: Request, container: ContainerDep, principal: PrincipalDep) -> HTMLResponse:
    return _render(request, "catalogs.html", container, principal)


@router.get("/changes", response_class=HTMLResponse)
async def changes(
    request: Request,
    container: ContainerDep,
    principal: Annotated[Principal, Depends(require(Capability.DESIGN_CATALOG))],
) -> HTMLResponse:
    return _render(
        request, "changes.html", container, principal, lab_origin=container.settings.lab_primary_origin
    )


@router.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request, container: ContainerDep, principal: PrincipalDep) -> HTMLResponse:
    return _render(request, "runs.html", container, principal)
