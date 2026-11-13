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
    max_per_user: int  # etkileşimli oturumlar
    idle_seconds: int
    max_verification_per_user: int = 1  # geçici doğrulama oturumları (toplam max_sessions içinde)


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    owner_id: str
    created_at: datetime
    last_used_at: datetime
    busy_operation: str | None
    purpose: str = "interactive"
    current_url: str | None = None
    alive: bool = True


@dataclass(slots=True)
class _Record:
    session_id: str
    owner_id: str
    handle: BrowserContextHandle
    created_at: datetime
    last_used_at: datetime
    busy_operation: str | None = None
    purpose: str = "interactive"

    def view(self) -> SessionView:
        return SessionView(
            self.session_id,
            self.owner_id,
            self.created_at,
            self.last_used_at,
            self.busy_operation,
            self.purpose,
            self.handle.current_url,
            not self.handle.is_closed,
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
        self._reserved: dict[tuple[str, str], int] = {}
        self._shutting_down = False

    # ---- sorgular -------------------------------------------------------------

    def list(self, owner_id: str) -> list[SessionView]:
        return [r.view() for r in self._records.values() if r.owner_id == owner_id]

    def _owned(self, owner_id: str, session_id: str, allow_verification: bool = False) -> _Record:
        """Sahibi olmayan ve (iç kullanım dışında) doğrulama oturumu 'bulunamadı' döner: amaç alanıyla
        etkileşimli kota atlatılamaz, geçici oturum normal oturum yerine kullanılamaz."""
        record = self._records.get(session_id)
        if record is None or record.owner_id != owner_id:
            raise SessionNotFound()
        if record.purpose == "verification" and not allow_verification:
            raise SessionNotFound()
        return record

    def status(self, owner_id: str, session_id: str) -> SessionView:
        return self._owned(owner_id, session_id).view()

    def overview(self, owner_id: str) -> dict[str, object]:
        mine = [r for r in self._records.values() if r.owner_id == owner_id]
        interactive = [r for r in mine if r.purpose == "interactive"]
        return {
            "sessions": [r.view() for r in interactive],
            "quota": {
                "interactive_limit": self._limits.max_per_user,
                "interactive_used": len(interactive),
                "total_capacity": self._limits.max_sessions,
                "total_used": len(self._records),
                "verification_in_use": len(mine) - len(interactive),
            },
        }

    def peek(self, owner_id: str, session_id: str, allow_verification: bool = False) -> BrowserContextHandle:
        """Sahiplik kontrollü, kilitsiz erişim. Yalnız tarayıcıya dokunmayan beklemeler (ör. seçim olayı)
        ve testler içindir; sayfa üzerinde iş yapan kod operation() kullanır."""
        return self._owned(owner_id, session_id, allow_verification).handle

    # ---- yaşam döngüsü --------------------------------------------------------

    async def open(self, owner_id: str, purpose: str = "interactive") -> SessionView:
        """purpose: 'interactive' (kullanıcı ekranı, kullanıcı başına max_per_user) veya 'verification'
        (geçici doğrulama, kullanıcı başına max_verification_per_user). İkisi de toplam max_sessions
        içindedir;
        kapasite doluysa başka hiçbir oturum kapatılmaz, SessionLimitReached döner."""
        if self._shutting_down:
            raise ServiceShuttingDown()
        if purpose not in {"interactive", "verification"}:
            raise ValueError("geçersiz oturum amacı")
        quota = (
            self._limits.max_per_user if purpose == "interactive" else self._limits.max_verification_per_user
        )
        # Rezervasyon await'ten önce yapılır: eşzamanlı open'lar limiti birlikte aşamaz.
        key = (owner_id, purpose)
        total = len(self._records) + sum(self._reserved.values())
        mine = sum(1 for r in self._records.values() if r.owner_id == owner_id and r.purpose == purpose)
        mine += self._reserved.get(key, 0)
        if total >= self._limits.max_sessions or mine >= quota:
            details: dict[str, object] = (
                {f"{purpose}_limit": quota, f"{purpose}_used": mine}
                if mine >= quota
                else {"total_capacity": self._limits.max_sessions}
            )
            raise SessionLimitReached(details=details)
        self._reserved[key] = self._reserved.get(key, 0) + 1
        try:
            handle = await self._factory.create_context(owner_id)
        finally:
            self._reserved[key] -= 1
            if not self._reserved[key]:
                del self._reserved[key]
        if self._shutting_down:
            await self._safe_close(handle)
            raise ServiceShuttingDown()
        now = self._clock()
        record = _Record(secrets.token_urlsafe(16), owner_id, handle, now, now, purpose=purpose)
        self._records[record.session_id] = record
        logger.info("browser_session_opened owner=%s purpose=%s", owner_id, purpose)
        return record.view()

    async def close(self, owner_id: str, session_id: str) -> None:
        record = self._owned(owner_id, session_id)
        if record.busy_operation is not None:
            raise SessionBusy()
        del self._records[session_id]
        await self._safe_close(record.handle)
        logger.info("browser_session_closed owner=%s", owner_id)

    async def close_verification(self, owner_id: str, session_id: str) -> None:
        """Elle giriş beklemesinde açılan doğrulama oturumunu kapatır (yalnız sahibinin kendi oturumu)."""
        record = self._records.get(session_id)
        if record is None or record.owner_id != owner_id or record.purpose != "verification":
            return
        del self._records[session_id]
        await self._safe_close(record.handle)

    def is_open(self, owner_id: str, session_id: str) -> bool:
        record = self._records.get(session_id)
        return record is not None and record.owner_id == owner_id and not record.handle.is_closed

    @asynccontextmanager
    async def verification_session(self, owner_id: str) -> AsyncIterator[SessionView]:
        """Geçici doğrulama oturumu: blok bittiğinde (hata/iptal dahil) kapanır. İçinde işlem sürüyor
        olsa bile
        context kapatılır; bu yalnız sahibinin kendi geçici oturumuna uygulanır, başka oturuma dokunulmaz."""
        view = await self.open(owner_id, purpose="verification")
        try:
            yield view
        finally:
            record = self._records.pop(view.session_id, None)
            if record is not None:
                await self._safe_close(record.handle)
                logger.info(
                    "browser_verification_session_closed owner=%s busy=%s",
                    owner_id,
                    record.busy_operation is not None,
                )

    @asynccontextmanager
    async def operation(
        self, owner_id: str, session_id: str, name: str, allow_verification: bool = False
    ) -> AsyncIterator[BrowserContextHandle]:
        """Oturumda tek işlem: ikinci eşzamanlı işlem beklemeden SessionBusy alır (kuyruğa girmez).
        allow_verification yalnız iç doğrulama akışı (yeni oturum testi) içindir; public uçlar kullanmaz."""
        if self._shutting_down:
            raise ServiceShuttingDown()
        record = self._owned(owner_id, session_id, allow_verification)
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
        # Doğrulama oturumunun ömrünü sahibi yönetir (elle giriş beklemesinin kendi süresi var).
        expired = [
            r
            for r in self._records.values()
            if r.busy_operation is None and r.last_used_at <= deadline and r.purpose != "verification"
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
