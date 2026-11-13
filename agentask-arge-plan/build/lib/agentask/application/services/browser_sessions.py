"""Tarayıcı oturumu kuralları: sahiplik, oturum başına tek işlem, limitler, boşta kalma, kapanış.

Kilit bellek içidir ve yalnızca tek process/tek worker için geçerlidir (ADR 0002). Çok worker'da yeterli
olduğu iddia edilmez.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agentask.application.errors import (
    ServiceShuttingDown,
    SessionBusy,
    SessionLimitReached,
    SessionNotFound,
)
from agentask.application.ports.browser import BrowserContextFactory, BrowserContextHandle

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionLimits:
    max_sessions: int
    max_per_user: int
    idle_seconds: int


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    owner_id: str
    created_at: datetime
    last_used_at: datetime
    busy_operation: str | None


@dataclass(slots=True)
class _Record:
    session_id: str
    owner_id: str
    handle: BrowserContextHandle
    created_at: datetime
    last_used_at: datetime
    busy_operation: str | None = None

    def view(self) -> SessionView:
        return SessionView(
            self.session_id, self.owner_id, self.created_at, self.last_used_at, self.busy_operation
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BrowserSessionService:
    def __init__(
        self,
        factory: BrowserContextFactory,
        limits: SessionLimits,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._factory = factory
        self._limits = limits
        self._clock = clock
        self._records: dict[str, _Record] = {}
        self._reserved: dict[str, int] = {}
        self._shutting_down = False

    # ---- sorgular -------------------------------------------------------------

    def list(self, owner_id: str) -> list[SessionView]:
        return [r.view() for r in self._records.values() if r.owner_id == owner_id]

    def _owned(self, owner_id: str, session_id: str) -> _Record:
        record = self._records.get(session_id)
        if record is None or record.owner_id != owner_id:
            raise SessionNotFound()
        return record

    def peek(self, owner_id: str, session_id: str) -> BrowserContextHandle:
        """Sahiplik kontrollü, kilitsiz erişim. Yalnız tarayıcıya dokunmayan beklemeler (ör. seçim olayı)
        ve testler içindir; sayfa üzerinde iş yapan kod operation() kullanır."""
        return self._owned(owner_id, session_id).handle

    # ---- yaşam döngüsü --------------------------------------------------------

    async def open(self, owner_id: str) -> SessionView:
        if self._shutting_down:
            raise ServiceShuttingDown()
        # Rezervasyon await'ten önce yapılır: eşzamanlı open'lar limiti birlikte aşamaz.
        total = len(self._records) + sum(self._reserved.values())
        mine = sum(1 for r in self._records.values() if r.owner_id == owner_id) + self._reserved.get(
            owner_id, 0
        )
        if total >= self._limits.max_sessions or mine >= self._limits.max_per_user:
            raise SessionLimitReached()
        self._reserved[owner_id] = self._reserved.get(owner_id, 0) + 1
        try:
            handle = await self._factory.create_context(owner_id)
        finally:
            self._reserved[owner_id] -= 1
            if not self._reserved[owner_id]:
                del self._reserved[owner_id]
        if self._shutting_down:
            await self._safe_close(handle)
            raise ServiceShuttingDown()
        now = self._clock()
        record = _Record(secrets.token_urlsafe(16), owner_id, handle, now, now)
        self._records[record.session_id] = record
        logger.info("browser_session_opened owner=%s", owner_id)
        return record.view()

    async def close(self, owner_id: str, session_id: str) -> None:
        record = self._owned(owner_id, session_id)
        if record.busy_operation is not None:
            raise SessionBusy()
        del self._records[session_id]
        await self._safe_close(record.handle)
        logger.info("browser_session_closed owner=%s", owner_id)

    @asynccontextmanager
    async def operation(
        self, owner_id: str, session_id: str, name: str
    ) -> AsyncIterator[BrowserContextHandle]:
        """Oturumda tek işlem: ikinci eşzamanlı işlem beklemeden SessionBusy alır (kuyruğa girmez)."""
        if self._shutting_down:
            raise ServiceShuttingDown()
        record = self._owned(owner_id, session_id)
        if record.busy_operation is not None:
            raise SessionBusy()
        if record.handle.is_closed:
            self._records.pop(session_id, None)
            raise SessionNotFound("Tarayıcı oturumu kapanmış; yeni oturum açın.")
        record.busy_operation = name
        record.last_used_at = self._clock()
        try:
            yield record.handle
        finally:
            record.busy_operation = None
            record.last_used_at = self._clock()

    async def reap_idle(self) -> int:
        deadline = self._clock() - timedelta(seconds=self._limits.idle_seconds)
        expired = [
            r for r in self._records.values() if r.busy_operation is None and r.last_used_at <= deadline
        ]
        for record in expired:
            del self._records[record.session_id]
            await self._safe_close(record.handle)
        if expired:
            logger.info("browser_sessions_reaped count=%d", len(expired))
        return len(expired)

    async def shutdown(self) -> None:
        self._shutting_down = True
        records = list(self._records.values())
        self._records.clear()
        await asyncio.gather(*(self._safe_close(r.handle) for r in records))
        await self._factory.shutdown()
        logger.info("browser_sessions_shutdown closed=%d", len(records))

    @staticmethod
    async def _safe_close(handle: BrowserContextHandle) -> None:
        try:
            await handle.close()
        except Exception as exc:  # kapanışta tek hata diğer kaynakları sızdırmamalı
            logger.warning("browser_context_close_failed type=%s", type(exc).__name__)
