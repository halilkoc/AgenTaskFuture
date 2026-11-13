"""Playwright kontrol sürücüsü. Yalnız P2 adaylarıyla çalışır; her işlemden önce aday yeniden doğrulanır
(check_candidate). Tıklama/yazma Playwright eylemleriyle (actionability beklemesi, force yok) yapılır.

Hata eşlemesi: bayat aday / frame değişimi → StaleTarget; Playwright zaman aşımı → TargetNotReady.
Değer veya metin loglanmaz.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import ElementHandle, Frame, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from agentask.application.controls import AdapterError, ChoiceNotAvailable, StaleTarget, TargetNotReady
from agentask.application.ports.controls import ControlState, OpenDialog
from agentask.config.settings import Settings
from agentask.domain.actions import ErrorClass, EvidenceSpec
from agentask.infrastructure.browser import driver_js as js
from agentask.infrastructure.browser.observer import PageObserver

logger = logging.getLogger(__name__)
_STALE_MARKERS = (
    "detached",
    "Execution context was destroyed",
    "Target closed",
    "has been closed",
    "not attached",
    "Frame was detached",
)


class AmbiguousControl(AdapterError):
    error_class = ErrorClass.TARGET_AMBIGUOUS


@contextlib.asynccontextmanager
async def _mapped() -> AsyncIterator[None]:
    try:
        yield
    except PlaywrightTimeout as exc:
        raise TargetNotReady("Hedef süre içinde işleme hazır olmadı.") from exc
    except PlaywrightError as exc:
        if any(m in exc.message for m in _STALE_MARKERS):
            raise StaleTarget("frame_changed") from exc
        raise


class PlaywrightDriver:
    def __init__(self, observer: PageObserver, page: Page, settings: Settings) -> None:
        self._observer = observer
        self._page = page
        self._settings = settings

    @property
    def _timeout(self) -> int:
        return self._settings.action_timeout_ms

    async def _element(self, cid: str) -> tuple[ElementHandle, Frame]:
        reason = await self._observer.check_candidate(cid)
        if reason is not None:
            raise StaleTarget(reason)
        array, index = await self._observer.element_for(cid)
        async with _mapped():
            handle = await array.evaluate_handle("(a, i) => a[i]", index)
            element = handle.as_element()
            frame = await element.owner_frame() if element else None
        if element is None or frame is None:
            raise StaleTarget("element_detached")
        return element, frame

    # ---- kontrol ilkelleri ----------------------------------------------------

    async def state(self, cid: str) -> ControlState:
        element, _ = await self._element(cid)
        async with _mapped():
            raw: dict[str, Any] = await element.evaluate(js.STATE)
        return ControlState(
            value=raw["value"],
            selected_text=raw["selectedText"],
            expanded=raw["expanded"],
            selected=raw["selected"],
            panel_visible=raw["panelVisible"],
            visible=raw["visible"],
            enabled=raw["enabled"],
        )

    async def fill(self, cid: str, value: str) -> None:
        element, _ = await self._element(cid)
        async with _mapped():
            await element.fill(value, timeout=self._timeout)

    async def select_option(self, cid: str, label: str) -> None:
        element, _ = await self._element(cid)
        async with _mapped():
            await element.select_option(label=label, timeout=self._timeout)

    async def click(self, cid: str) -> None:
        element, _ = await self._element(cid)
        async with _mapped():
            await element.click(timeout=self._timeout)

    async def click_trial(self, cid: str) -> None:
        element, _ = await self._element(cid)
        async with _mapped():
            await element.click(trial=True, timeout=self._timeout)

    async def listbox_options(self, cid: str) -> list[str]:
        element, frame = await self._element(cid)
        async with _mapped():
            await frame.wait_for_function(js.LISTBOX_READY, arg=element, timeout=self._timeout)
            options: list[str] = await element.evaluate(js.LISTBOX_OPTIONS)
        return options

    async def click_option(self, cid: str, label: str) -> None:
        element, _ = await self._element(cid)
        async with _mapped():
            option = (await element.evaluate_handle(js.FIND_OPTION, label)).as_element()
            if option is None:
                raise ChoiceNotAvailable("Seçenek listede tekil değil.")
            await option.click(timeout=self._timeout)

    async def table_keys(self, cid: str) -> list[str]:
        element, _ = await self._element(cid)
        async with _mapped():
            keys: list[str] = await element.evaluate(js.TABLE_KEYS, self._settings.table_max_rows)
        return keys

    async def table_next_page(self, cid: str, labels: list[str]) -> bool:
        element, frame = await self._element(cid)
        async with _mapped():
            before = await element.evaluate(js.TABLE_KEYS, self._settings.table_max_rows)
            controls = await frame.evaluate_handle(js.NEXT_CONTROLS, labels)
            count = int(await controls.evaluate("a => a.length"))
            if count == 0:
                return False
            if count > 1:
                raise AmbiguousControl("Birden fazla 'sonraki' kontrolü var.")
            target = (await controls.evaluate_handle("a => a[0]")).as_element()
            assert target is not None
            await target.click(timeout=self._timeout)
        deadline = time.monotonic() + self._settings.readiness_timeout_ms / 1000
        while time.monotonic() < deadline:
            try:
                connected = await element.evaluate("e => e.isConnected")
                if (
                    connected
                    and await element.evaluate(js.TABLE_KEYS, self._settings.table_max_rows) != before
                ):
                    return True
                if not connected:
                    break
            except PlaywrightError:
                break  # sayfa yönlendi; eski tablo bağlamı yok
            await self.wait_for_change(int((deadline - time.monotonic()) * 1000))
        else:
            raise TargetNotReady("Sonraki sayfa süre içinde yüklenmedi.")
        async with _mapped():
            await self._page.wait_for_load_state(
                "domcontentloaded", timeout=self._settings.navigation_timeout_ms
            )
        return True

    async def table_load_more(self, cid: str) -> bool:
        element, _ = await self._element(cid)
        async with _mapped():
            before = len(await element.evaluate(js.TABLE_KEYS, self._settings.table_max_rows))
            if not await element.evaluate(js.SCROLL_TO_END):
                return False
        deadline = time.monotonic() + self._settings.action_timeout_ms / 1000
        while time.monotonic() < deadline:
            async with _mapped():
                if len(await element.evaluate(js.TABLE_KEYS, self._settings.table_max_rows)) > before:
                    return True
            await self.wait_for_change(int((deadline - time.monotonic()) * 1000))
        return False

    async def text_visible(self, cid: str, text: str) -> bool:
        _, frame = await self._element(cid)
        async with _mapped():
            return bool(await frame.evaluate(js.TEXT_VISIBLE, text))

    # ---- sayfa ilkelleri ---------------------------------------------------------

    async def evidence(self, spec: EvidenceSpec, anchor_cid: str | None) -> list[str]:
        if anchor_cid is not None:
            element, frame = await self._element(anchor_cid)
        else:
            element, frame = None, self._page.main_frame
        async with _mapped():
            if spec.kind == "status_text":
                if element is None:
                    texts: list[str] = await frame.evaluate(
                        js.EVIDENCE_STATUS.replace("(el) =>", "(el = null) =>")
                    )
                else:
                    texts = await element.evaluate(js.EVIDENCE_STATUS)
                return texts
            result = await frame.evaluate(js.EVIDENCE_LIST, spec.name)
        if result["error"] == "ambiguous":
            raise AmbiguousControl("Kanıt listesi tekil değil.")
        items: list[str] = result["items"]
        return items

    async def wait_for_change(self, timeout_ms: int) -> bool:
        """Herhangi bir frame'de DOM değişimi veya frame ağacı değişimi olana kadar (süre sınırlı) bekler."""
        if timeout_ms <= 0 or self._observer.native_dialog is not None:
            return False
        revision = self._observer.tree_revision
        tasks = [asyncio.ensure_future(f.evaluate(js.MUTATION_WAIT, timeout_ms)) for f in self._page.frames]
        deadline = time.monotonic() + timeout_ms / 1000 + 0.5
        try:
            pending = set(tasks)
            while pending and time.monotonic() < deadline:
                done, pending = await asyncio.wait(pending, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                if self._observer.tree_revision != revision:
                    return True
                for task in done:
                    if not task.cancelled() and task.exception() is None and task.result():
                        return True
                    if not task.cancelled() and task.exception() is not None:
                        return True  # frame yönlendi/ayrıldı: değişim
            return False
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def reload(self) -> None:
        async with _mapped():
            await self._page.reload(
                wait_until="domcontentloaded", timeout=self._settings.navigation_timeout_ms
            )

    async def current_path(self) -> str:
        return urlsplit(self._page.url).path or "/"

    async def open_dialogs(self) -> list[OpenDialog]:
        native = self._observer.native_dialog
        if native is not None:
            # Native dialog açıkken sayfada betik çalışmaz; yalnız kaydı dön, dialog'u kapatma.
            return [OpenDialog(frame_ref=None, native=True, name=native[0], text=native[1])]
        dialogs: list[OpenDialog] = []
        for frame in self._page.frames:
            if frame.is_detached() or frame.url.startswith("chrome-error://"):
                continue
            try:
                found = await asyncio.wait_for(
                    frame.evaluate(js.OPEN_DIALOGS), self._settings.frame_scan_timeout_ms / 1000
                )
            except (TimeoutError, PlaywrightError):
                continue
            ref = self._observer.registry.ref_for(frame)
            dialogs += [
                OpenDialog(frame_ref=ref, native=False, name=d["name"], text=d["text"]) for d in found
            ]
        return dialogs

    async def click_dialog_button(self, dialog_name: str, button_label: str) -> bool:
        matches: list[ElementHandle] = []
        for frame in self._page.frames:
            if frame.is_detached():
                continue
            with contextlib.suppress(PlaywrightError):
                array = await frame.evaluate_handle(js.DIALOG_BUTTONS, [dialog_name, button_label])
                count = int(await array.evaluate("a => a.length"))
                for i in range(count):
                    element = (await array.evaluate_handle("(a, i) => a[i]", i)).as_element()
                    if element is not None:
                        matches.append(element)
        if len(matches) != 1:
            return False
        async with _mapped():
            await matches[0].click(timeout=self._timeout)
        return True
