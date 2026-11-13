"""Gözlem portu: frame takibi, bütçeli envanter, aday doğrulama, vurgulama ve seçim modu."""

from __future__ import annotations

from typing import Protocol

from agentask.domain.observation import LightFrame, PickEvent, Snapshot


class PageObserverPort(Protocol):
    @property
    def current_snapshot(self) -> Snapshot | None: ...

    @property
    def native_dialog(self) -> tuple[str, str] | None:
        """Açık native dialog (tür, kısaltılmış metin); kapatılmaz."""
        ...

    async def light_scan(self) -> list[LightFrame]: ...

    async def observe(
        self, detail_refs: set[str] | None = None, light: list[LightFrame] | None = None
    ) -> Snapshot: ...

    async def check_candidate(self, candidate_id: str) -> str | None:
        """None → geçerli; aksi halde stale nedeni."""
        ...

    async def highlight(self, candidate_id: str, caption: str) -> None:
        """Sayfaya olay göndermeden hedefi görsel olarak işaretler."""
        ...

    async def clear_highlight(self) -> None: ...

    async def start_picker(self) -> None: ...

    async def stop_picker(self) -> None: ...

    @property
    def picker_active(self) -> bool: ...

    async def wait_raw_pick(self, timeout_s: float) -> bool:
        """Seçim olayı geldiyse True (tarayıcıya dokunmaz)."""
        ...

    async def map_pick(self) -> PickEvent:
        """Son seçimi güncel snapshot adayına çevirir; gerekirse yeniden gözlemler."""
        ...
