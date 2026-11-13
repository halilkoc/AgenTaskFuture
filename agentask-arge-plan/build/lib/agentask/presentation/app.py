from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from agentask.bootstrap import Container, build_container
from agentask.config.settings import Settings
from agentask.presentation import pages
from agentask.presentation.api import (
    assistant,
    catalogs,
    changes,
    drafts,
    health,
    me,
    observation,
    public_config,
    runs,
    sessions,
)
from agentask.presentation.errors import install_error_handlers

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
logger = logging.getLogger(__name__)


async def _reap_periodically(container: Container) -> None:
    interval = max(1.0, min(60.0, container.settings.browser_session_idle_seconds / 4))
    while True:
        await asyncio.sleep(interval)
        try:
            await container.sessions.reap_idle()
        except Exception as exc:
            logger.warning("session_reap_failed type=%s", type(exc).__name__)


def _lifespan(container: Container) -> Callable[[FastAPI], contextlib.AbstractAsyncContextManager[None]]:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Yarım kalan run'lar: gönderilmiş adım → outcome_unknown, diğerleri → paused_session.
        container.runs.start_recovery()
        if container.catalog_store is not None:
            try:
                await container.catalog_store.ensure_schema()
            except Exception as exc:  # erişilemezse uygulama açılır; readiness ve yayın uçları 503 döner
                logger.warning("catalog_schema_unavailable type=%s", type(exc).__name__)
        reaper = asyncio.create_task(_reap_periodically(container))
        try:
            yield
        finally:
            reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper
            # Yeni adım/dispatch durdurulur; sonra bütün context'ler ve browser süreci kapatılır.
            await container.runs.shutdown()
            await container.sessions.shutdown()
            if container.catalog_store is not None:
                await container.catalog_store.close()

    return lifespan


def create_app(settings: Settings, container: Container | None = None) -> FastAPI:
    container = container or build_container(settings)
    app = FastAPI(
        title="AgenTask",
        version="0.1.0",
        # Production'da etkileşimli API dokümanı kapalı; OpenAPI şeması development/test için.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=_lifespan(container),
    )
    app.state.container = container

    @app.middleware("http")
    async def correlation_and_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-correlation-id", "")
        correlation_id = incoming if _CORRELATION_ID.fullmatch(incoming) else str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        )
        return response

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(public_config.router)
    app.include_router(sessions.router)
    app.include_router(observation.router)
    app.include_router(runs.router)
    app.include_router(drafts.router)
    app.include_router(catalogs.router)
    app.include_router(assistant.router)
    app.include_router(changes.router)
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    return app
