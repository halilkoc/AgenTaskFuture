"""Tarayıcı portu. Uygulama katmanı Playwright'ı tanımaz; yalnızca bu sözleşmeyi kullanır."""

from __future__ import annotations

from typing import Protocol

from agentask.application.ports.observation import PageObserverPort


class BrowserContextHandle(Protocol):
    """Tek kullanıcıya ait izole tarayıcı bağlamı (cookie/storage paylaşılmaz)."""

    @property
    def current_url(self) -> str: ...

    @property
    def observer(self) -> PageObserverPort: ...

    @property
    def is_closed(self) -> bool: ...

    async def navigate(self, url: str) -> None:
        """İzinli origin değilse NavigationNotAllowed fırlatır."""
        ...

    async def close(self) -> None: ...


class BrowserContextFactory(Protocol):
    async def create_context(self, owner_id: str) -> BrowserContextHandle: ...

    async def shutdown(self) -> None:
        """Bütün tarayıcı kaynaklarını (browser süreci dahil) serbest bırakır."""
        ...
