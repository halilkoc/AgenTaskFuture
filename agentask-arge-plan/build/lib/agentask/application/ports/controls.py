"""Kontrol sürücüsü portu: adapterlerin kullandığı fiziksel etkileşim ilkelleri.

Hepsi P2 aday kimliğiyle çalışır; selector almaz. Uygulama (Playwright) eleman bayatsa StaleTarget fırlatır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentask.domain.actions import EvidenceSpec


@dataclass(frozen=True, slots=True)
class ControlState:
    value: str | None = None
    selected_text: str | None = None
    expanded: bool | None = None
    selected: bool | None = None
    panel_visible: bool | None = None
    visible: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class OpenDialog:
    frame_ref: str | None
    native: bool
    name: str | None
    text: str


class ControlDriver(Protocol):
    async def state(self, cid: str) -> ControlState: ...

    async def fill(self, cid: str, value: str) -> None: ...

    async def select_option(self, cid: str, label: str) -> None: ...

    async def click(self, cid: str) -> None: ...

    async def click_trial(self, cid: str) -> None:
        """Tıklamadan yalnız actionability kontrolü (görünür, sabit, etkin, olayı alabilir)."""
        ...

    async def listbox_options(self, cid: str) -> list[str]:
        """Açılmış combobox listesinin seçenekleri; liste koşullu ve süre sınırlı beklenir."""
        ...

    async def click_option(self, cid: str, label: str) -> None: ...

    async def table_keys(self, cid: str) -> list[str]: ...

    async def table_next_page(self, cid: str, labels: list[str]) -> bool:
        """Tablonun frame'inde adı tam eşleşen tek etkin 'sonraki' kontrolüne basar; yoksa False."""
        ...

    async def table_load_more(self, cid: str) -> bool:
        """Kaydırmalı listeyi sona kaydırır ve değişimi bekler; değişim olmadıysa False."""
        ...

    async def text_visible(self, cid: str, text: str) -> bool: ...


class PageDriver(ControlDriver, Protocol):
    """Executor'ın sayfa düzeyi ilkelleri (kanıt okuma, engelleyiciler, oturum)."""

    async def evidence(self, spec: EvidenceSpec, anchor_cid: str | None) -> list[str]: ...

    async def wait_for_change(self, timeout_ms: int) -> bool: ...

    async def reload(self) -> None: ...

    async def current_path(self) -> str: ...

    async def open_dialogs(self) -> list[OpenDialog]: ...

    async def click_dialog_button(self, dialog_name: str, button_label: str) -> bool: ...
