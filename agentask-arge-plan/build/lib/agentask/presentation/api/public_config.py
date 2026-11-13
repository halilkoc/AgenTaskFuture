"""Allowlist public config. Settings dökümü frontend'e verilmez; yalnızca aşağıdaki alanlar."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from agentask.bootstrap import Container
from agentask.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/api/config", tags=["config"])


class PublicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_env: str
    timezone: str
    llm_available: bool
    evidence_screenshots_enabled: bool


def build_public_config(container: Container) -> PublicConfig:
    settings = container.settings
    return PublicConfig(
        app_env=settings.app_env.value,
        timezone=settings.app_timezone,
        llm_available=container.llm.availability().available,
        evidence_screenshots_enabled=settings.evidence_screenshots_enabled,
    )


@router.get("/public", response_model=PublicConfig)
async def public_config(container: ContainerDep) -> PublicConfig:
    return build_public_config(container)
