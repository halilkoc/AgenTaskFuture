"""PageObserver: FrameTracker + bütçeli anlamsal envanter (Playwright).

- Frame ağacı Playwright Frame nesneleri ve olaylarıyla tutulur; frame sırası/HTML id kullanılmaz.
- Cross-origin frame'ler Playwright'ın frame API'siyle ayrı ayrı incelenir; ana sayfa JS'ine güvenilmez.
- Her frame için süre, toplam gözlem süresi, derinlik, frame sayısı, eleman ve eşzamanlılık sınırı uygulanır;
  sınır aşımı ve okunamayan bölgeler durum + neden olarak raporlanır.
- Snapshot revision geçicidir; yeni gözlem eski adayları geçersiz kılar. Element handle'ları yalnız
  bellekte tutulur.
- Değer, ham HTML veya etiket metni loglanmaz; log yalnız sayılar ve durumlardır.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Dialog, Frame, JSHandle, Page
from playwright.async_api import Error as PlaywrightError

from agentask.config.settings import Settings
from agentask.domain.frames import FrameRegistry, Lineage
from agentask.domain.observation import (
    ContextEntry,
    ControlKind,
    FrameObservation,
    LightFrame,
    ObservedControl,
    PickEvent,
    ScanStatus,
    Snapshot,
)
from agentask.domain.origins import origin_of
from agentask.infrastructure.browser.inventory_js import DETAIL_SCAN, FINGERPRINT_AT, INDEX_OF, LIGHT_SCAN
from agentask.infrastructure.browser.picker_js import (
    CLEAR_HIGHLIGHT,
    ELEMENT_AT,
    HIGHLIGHT,
    PICKER_INSTALL,
    PICKER_UNINSTALL,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _FrameScan:
    frame: Frame
    ref: str
    parent_ref: str | None
    depth: int
    lineage: Lineage
    title: str | None
    titles: tuple[str, ...]
    status: ScanStatus = ScanStatus.NOT_SCANNED
    reason: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)
    els: JSHandle | None = None
    names: tuple[str, ...] = ()
    detail: bool = False


@dataclass(slots=True)
class _Runtime:
    snapshot: Snapshot
    handles: dict[str, JSHandle]  # frame_ref -> element dizisi
    index: dict[str, tuple[str, int, str]]  # candidate_id -> (frame_ref, index, fingerprint)


def _origin_path(url: str) -> tuple[str | None, str | None]:
    parts = urlsplit(url)
    if parts.scheme in {"http", "https"}:
        return f"{parts.scheme}://{parts.netloc}", parts.path or "/"
    return None, None


class PageObserver:
    def __init__(
        self,
        page: Page,
        settings: Settings,
        shared_windows: list[tuple[str, Page]] | None = None,
    ) -> None:
        self._page = page
        self._settings = settings
        self._registry = FrameRegistry()
        self._counter = 0
        self._runtime: _Runtime | None = None
        self._picker_token: str | None = None
        self._pick_ready = asyncio.Event()
        self._last_pick: tuple[Frame, int, str | None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.native_dialog: tuple[str, str] | None = None
        self._dialog: Dialog | None = None
        self._dialog_id: str | None = None
        # (kesinti kimliği, sayfa); ana sayfa asla burada değil. Benimsenen pencerenin gözlemcisi aynı listeyi
        # paylaşır: orada çalışırken açılan üçüncü pencere de kesinti sayılır.
        self._new_pages: list[tuple[str, Page]] = [] if shared_windows is None else shared_windows
        # Kullanıcı kararlarını sıralar; sayfa betiklerine dokunmaz (oturum kilidinden bağımsız, kilitlenmez).
        self._decision_lock = asyncio.Lock()
        self._registry.attach(page.main_frame, None)
        if shared_windows is not None:  # açılmış pencere: mevcut çerçeveler de izlenir
            for frame in page.frames:
                if frame is not page.main_frame:
                    self._registry.attach(frame, frame.parent_frame)
        # Native dialog'lar otomatik kapatılmaz: kayıt altına alınır, yürütme durur, insan karar verir.
        page.on("dialog", self._on_dialog)
        # Yeni pencere/sekme: otomatik geçilmez ve kapatılmaz; kayıt altına alınır, yürütme durur.
        if shared_windows is None:
            with contextlib.suppress(AttributeError):  # test ikamelerinde context olmayabilir
                page.context.on("page", self._on_new_page)
        page.on("frameattached", self._on_attached)
        page.on("framenavigated", self._on_navigated)
        page.on("framedetached", self._on_detached)

    # ---- FrameTracker ---------------------------------------------------------

    def _on_attached(self, frame: Frame) -> None:
        self._registry.attach(frame, frame.parent_frame)

    def _on_navigated(self, frame: Frame) -> None:
        if self._registry.ref_for(frame) is None:
            self._registry.attach(frame, frame.parent_frame)
        self._registry.navigated(frame)
        if self._picker_token is not None:
            task = asyncio.ensure_future(self._install_after_load(frame, self._picker_token))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _on_detached(self, frame: Frame) -> None:
        self._registry.detached(frame)

    def _on_dialog(self, dialog: Dialog) -> None:
        self._dialog = dialog
        self._dialog_id = secrets.token_hex(8)
        self.native_dialog = (dialog.type, dialog.message[:300])
        logger.warning("native_dialog_open type=%s", dialog.type)

    def _on_new_page(self, page: Page) -> None:
        if page is self._page:
            return
        self._new_pages.append((secrets.token_hex(8), page))
        page.on("close", self._forget_page)
        logger.warning("new_window_open count=%d", len(self._new_pages))

    def _forget_page(self, page: Page) -> None:
        self._new_pages[:] = [(i, p) for i, p in self._new_pages if p is not page]

    @property
    def window_list(self) -> list[tuple[str, Page]]:
        """Bekleyen pencereler listesinin kendisi (yalnız oturum tutamacı benimseme için kullanır)."""
        return self._new_pages

    @property
    def new_windows(self) -> int:
        """Bu oturumda açık kalan yeni pencere/sekme sayısı (ana sayfa hariç)."""
        return len(self._new_pages)

    def interruption_state(self) -> dict[str, Any]:
        """Görünen kesintiler ve kimlikleri. Karar bu kimliklere bağlanır; adres yalnız origin olarak."""
        dialog = None
        if self.native_dialog is not None and self._dialog_id is not None:
            dialog = {"id": self._dialog_id, "type": self.native_dialog[0], "message": self.native_dialog[1]}
        windows = [{"id": i, "origin": origin_of(p.url) or "boş sayfa"} for i, p in self._new_pages]
        return {"browser_dialog": dialog, "new_windows": windows}

    async def dismiss_native_dialog(self, dialog_id: str) -> bool:
        """Yalnız kullanıcının açık kararıyla ve yalnız GÖRÜLEN dialog için: iptal ederek kapatır. Kimlik
        güncel dialog'a ait değilse (kapanmış/başkası açılmış) hiçbir şey yapılmaz ve False döner."""
        async with self._decision_lock:
            if self._dialog is None or self._dialog_id != dialog_id:
                return False
            dialog, self._dialog, self._dialog_id = self._dialog, None, None
            self.native_dialog = None
            with contextlib.suppress(PlaywrightError):
                await dialog.dismiss()
            return True

    async def close_new_windows(self, window_ids: list[str]) -> list[str] | None:
        """Yalnız kullanıcının açık kararıyla ve yalnız GÖRÜLEN pencereler için. İstenen kimliklerin hepsi
        hâlâ açık değilse hiçbir pencere kapatılmaz (None): eski karar sonradan açılan başka pencereye
        uygulanmaz. Ana çalışma sayfası hiçbir durumda kapatılmaz."""
        async with self._decision_lock:
            wanted = set(window_ids)
            current = {i: p for i, p in self._new_pages if p is not self._page}
            if not wanted or not wanted <= set(current):
                return None
            closed: list[str] = []
            for window_id in window_ids:
                page = current[window_id]
                self._forget_page(page)
                with contextlib.suppress(PlaywrightError):
                    await page.close()
                closed.append(window_id)
            return closed

    @property
    def tree_revision(self) -> int:
        return self._registry.tree_revision

    @property
    def page(self) -> Page:
        return self._page

    @property
    def registry(self) -> FrameRegistry:
        return self._registry

    @property
    def current_snapshot(self) -> Snapshot | None:
        return self._runtime.snapshot if self._runtime else None

    def _sync_tree(self) -> None:
        def walk(frame: Frame) -> None:
            if frame.is_detached():
                return
            self._registry.attach(frame, frame.parent_frame)
            for child in frame.child_frames:
                walk(child)

        walk(self._page.main_frame)

    async def _frame_title(self, frame: Frame) -> str | None:
        if frame.parent_frame is None:
            return None
        try:
            element = await asyncio.wait_for(
                frame.frame_element(), self._settings.frame_scan_timeout_ms / 1000
            )
            title = await element.evaluate(
                "el => el.getAttribute('title') || el.getAttribute('aria-label') || el.getAttribute('name')"
            )
            return str(title).strip() or None if title else None
        except (TimeoutError, PlaywrightError):
            return None

    async def _plan_frames(self) -> list[_FrameScan]:
        """Ağacı genişlik öncelikli dolaşır; derinlik ve frame sayısı sınırını işaretler."""
        self._sync_tree()
        plans: list[_FrameScan] = []
        queue: list[tuple[Frame, tuple[str, ...]]] = [(self._page.main_frame, ())]
        while queue:
            frame, parent_titles = queue.pop(0)
            ref = self._registry.ref_for(frame)
            if ref is None or frame.is_detached():
                continue
            title = await self._frame_title(frame)
            titles = (*parent_titles, title) if title else parent_titles
            info = self._registry.info(ref)
            plan = _FrameScan(
                frame=frame,
                ref=ref,
                parent_ref=info.parent_ref if info else None,
                depth=self._registry.depth(ref),
                lineage=self._registry.lineage(ref),
                title=title,
                titles=titles,
            )
            if plan.depth > self._settings.frame_scan_max_depth:
                plan.reason = "depth_limit"
            elif len([p for p in plans if p.reason is None]) >= self._settings.observe_max_frames:
                plan.reason = "frame_limit"
            plans.append(plan)
            queue += [(child, titles) for child in frame.child_frames]
        return plans

    # ---- tarama ---------------------------------------------------------------

    async def _scan_frames(self, plans: Iterable[_FrameScan], *, light: bool) -> None:
        settings = self._settings
        deadline = time.monotonic() + settings.observe_timeout_ms / 1000
        semaphore = asyncio.Semaphore(settings.frame_scan_concurrency)
        opts = {"maxElements": settings.frame_scan_max_elements}

        async def scan(plan: _FrameScan) -> None:
            if plan.reason is not None:
                return
            url = plan.frame.url
            if url.startswith("chrome-error://") or plan.frame.is_detached():
                plan.status, plan.reason = ScanStatus.INACCESSIBLE, "error_page_or_blocked"
                return
            async with semaphore:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    plan.status, plan.reason = ScanStatus.NOT_SCANNED, "observe_timeout"
                    return
                timeout = min(settings.frame_scan_timeout_ms / 1000, remaining)
                try:
                    if light:
                        result = await asyncio.wait_for(plan.frame.evaluate(LIGHT_SCAN, opts), timeout)
                        plan.names = tuple(result["names"])
                        total = int(result["total"])
                    else:
                        handle = await asyncio.wait_for(
                            plan.frame.evaluate_handle(DETAIL_SCAN, opts), timeout
                        )
                        plan.items = await handle.evaluate("o => o.items")
                        plan.els = await handle.get_property("els")
                        total = int(await handle.evaluate("o => o.total"))
                        await handle.dispose()
                        plan.detail = True
                except TimeoutError:
                    timed_out = remaining <= settings.frame_scan_timeout_ms / 1000
                    plan.status = ScanStatus.TIMED_OUT
                    plan.reason = "observe_timeout" if timed_out else "frame_timeout"
                    return
                except PlaywrightError:
                    plan.status, plan.reason = ScanStatus.INACCESSIBLE, "evaluation_failed"
                    return
            if total > settings.frame_scan_max_elements:
                plan.status, plan.reason = ScanStatus.PARTIAL, "element_limit"
            else:
                plan.status, plan.reason = ScanStatus.COMPLETE, None

        await asyncio.gather(*(scan(p) for p in plans))

    async def light_scan(self) -> list[LightFrame]:
        plans = await self._plan_frames()
        await self._scan_frames(plans, light=True)
        return [LightFrame(p.ref, p.title, p.status, p.reason, p.names) for p in plans]

    async def observe(
        self, detail_refs: set[str] | None = None, light: list[LightFrame] | None = None
    ) -> Snapshot:
        """Ayrıntılı envanter. detail_refs verilirse yalnız o frame'ler ayrıntılı taranır; diğerleri hafif
        tarama durumuyla (detail_scanned=False) snapshot'ta kalır."""
        plans = await self._plan_frames()
        light_by_ref = {lf.frame_ref: lf for lf in light or []}
        selected = [p for p in plans if detail_refs is None or p.ref in detail_refs]
        for plan in plans:
            if plan not in selected and plan.reason is None:
                lf = light_by_ref.get(plan.ref)
                plan.status = lf.status if lf else ScanStatus.NOT_SCANNED
                plan.reason = (lf.reason if lf else "not_selected") or None
        await self._scan_frames(selected, light=False)
        return await self._commit(plans)

    async def _commit(self, plans: list[_FrameScan]) -> Snapshot:
        self._counter += 1
        revision = f"s{self._counter}{secrets.token_hex(2)}"
        controls: list[ObservedControl] = []
        index: dict[str, tuple[str, int, str]] = {}
        handles: dict[str, JSHandle] = {}
        frames: list[FrameObservation] = []
        for plan in plans:
            if plan.els is not None:
                handles[plan.ref] = plan.els
            for i, item in enumerate(plan.items):
                cid = f"c-{revision}-{len(controls)}"
                controls.append(_control(cid, plan, item))
                index[cid] = (plan.ref, i, str(item["fp"]))
            origin, path = _origin_path(plan.frame.url)
            frames.append(
                FrameObservation(
                    frame_ref=plan.ref,
                    parent_ref=plan.parent_ref,
                    title=plan.title,
                    origin=origin,
                    path=path,
                    depth=plan.depth,
                    lineage=plan.lineage,
                    status=plan.status,
                    reason=plan.reason,
                    detail_scanned=plan.detail,
                    control_count=len(plan.items),
                )
            )
        previous, self._runtime = self._runtime, None
        snapshot = Snapshot(revision, datetime.now(UTC), tuple(frames), tuple(controls))
        self._runtime = _Runtime(snapshot, handles, index)
        if previous is not None:
            for old in previous.handles.values():
                with contextlib.suppress(PlaywrightError):
                    await old.dispose()
        logger.info(
            "observation_completed frames=%d controls=%d incomplete=%d",
            len(frames),
            len(controls),
            sum(1 for f in frames if f.status is not ScanStatus.COMPLETE),
        )
        return snapshot

    # ---- aday doğrulama --------------------------------------------------------

    async def check_candidate(self, candidate_id: str) -> str | None:
        """None: aday geçerli. Aksi halde neden: snapshot_superseded | unknown_candidate | frame_changed |
        element_detached | element_changed."""
        runtime = self._runtime
        if runtime is None or not candidate_id.startswith(f"c-{runtime.snapshot.revision}-"):
            return "snapshot_superseded"
        entry = runtime.index.get(candidate_id)
        if entry is None:
            return "unknown_candidate"
        frame_ref, idx, fingerprint = entry
        frame_obs = runtime.snapshot.frame(frame_ref)
        if frame_obs is None or not self._registry.is_current(frame_obs.lineage):
            return "frame_changed"
        try:
            current = await runtime.handles[frame_ref].evaluate(FINGERPRINT_AT, idx)
        except PlaywrightError:
            return "frame_changed"
        if current is None:
            return "element_detached"
        if current != fingerprint:
            return "element_changed"
        return None

    async def element_for(self, candidate_id: str) -> tuple[JSHandle, int]:
        assert self._runtime is not None
        frame_ref, idx, _ = self._runtime.index[candidate_id]
        return self._runtime.handles[frame_ref], idx

    async def candidate_for_element(self, frame: Frame, element: JSHandle) -> str | None:
        runtime = self._runtime
        ref = self._registry.ref_for(frame)
        if runtime is None or ref is None or ref not in runtime.handles:
            return None
        try:
            idx = int(await runtime.handles[ref].evaluate(INDEX_OF, element))
        except PlaywrightError:
            return None
        if idx < 0:
            return None
        return next((cid for cid, (r, i, _) in runtime.index.items() if r == ref and i == idx), None)

    # ---- vurgulama ve seçim modu (sayfaya olay göndermez) -----------------------

    async def highlight(self, candidate_id: str, caption: str) -> None:
        await self.clear_highlight()
        array, index = await self.element_for(candidate_id)
        await array.evaluate(HIGHLIGHT, [index, caption])

    async def clear_highlight(self) -> None:
        for frame in self._page.frames:
            with contextlib.suppress(PlaywrightError):
                await frame.evaluate(CLEAR_HIGHLIGHT)

    @property
    def picker_active(self) -> bool:
        return self._picker_token is not None

    async def _install(self, frame: Frame, token: str) -> None:
        if frame.is_detached() or frame.url.startswith("chrome-error://"):
            return
        with contextlib.suppress(PlaywrightError):
            await frame.evaluate(PICKER_INSTALL, token)

    async def _install_after_load(self, frame: Frame, token: str) -> None:
        with contextlib.suppress(PlaywrightError):
            await frame.wait_for_load_state("domcontentloaded", timeout=self._settings.navigation_timeout_ms)
        if self._picker_token == token:
            await self._install(frame, token)

    async def start_picker(self) -> None:
        token = secrets.token_hex(16)
        self._picker_token = token
        self._last_pick = None
        self._pick_ready.clear()
        await asyncio.gather(*(self._install(f, token) for f in self._page.frames))

    async def stop_picker(self) -> None:
        self._picker_token = None
        for frame in self._page.frames:
            with contextlib.suppress(PlaywrightError):
                await frame.evaluate(PICKER_UNINSTALL)
        self._last_pick = None
        # Bekleyen seçim isteklerini uyandır; _last_pick boş olduğu için "seçim yok" dönerler.
        self._pick_ready.set()
        self._pick_ready = asyncio.Event()

    async def on_binding(self, source: dict[str, Any], payload: Any) -> None:
        """Seçim katmanından gelen çağrı. Token eşleşmezse (ör. sayfa betiği taklidi) yok sayılır."""
        token = self._picker_token
        if token is None or not isinstance(payload, dict) or payload.get("token") != token:
            logger.warning("picker_binding_rejected")
            return
        index = payload.get("index")
        fingerprint = payload.get("fp")
        if not isinstance(index, int):
            return
        self._last_pick = (source["frame"], index, fingerprint if isinstance(fingerprint, str) else None)
        self._pick_ready.set()

    async def wait_raw_pick(self, timeout_s: float) -> bool:
        ready = self._pick_ready
        if not ready.is_set():
            try:
                await asyncio.wait_for(ready.wait(), timeout_s)
            except TimeoutError:
                return False
        return self._last_pick is not None

    async def map_pick(self) -> PickEvent:
        pick, self._last_pick = self._last_pick, None
        self._pick_ready.clear()
        if pick is None:
            return PickEvent(
                None, self.current_snapshot.revision if self.current_snapshot else None, "no_pick"
            )
        frame, index, fingerprint = pick
        snapshot = self.current_snapshot
        if index < 0 or fingerprint is None:
            return PickEvent(None, snapshot.revision if snapshot else None, "unsupported_element")
        try:
            element = await frame.evaluate_handle(ELEMENT_AT, [index, fingerprint])
            present = await element.evaluate("e => e instanceof Element")
        except PlaywrightError:
            return PickEvent(None, snapshot.revision if snapshot else None, "frame_changed")
        if not present:
            return PickEvent(None, snapshot.revision if snapshot else None, "element_changed")
        candidate = await self.candidate_for_element(frame, element)
        if candidate is None:
            # Seçilen kontrol güncel snapshot'ta yoksa (yeni frame/yeniden çizim) bütçeli yeniden gözlem.
            await self.observe()
            candidate = await self.candidate_for_element(frame, element)
        snapshot = self.current_snapshot
        revision = snapshot.revision if snapshot else None
        if candidate is None:
            return PickEvent(None, revision, "not_in_inventory")
        return PickEvent(candidate, revision, "picked")


def _control(cid: str, plan: _FrameScan, item: dict[str, Any]) -> ObservedControl:
    return ObservedControl(
        candidate_id=cid,
        frame_ref=plan.ref,
        kind=ControlKind(item["kind"]),
        role=str(item["role"]),
        accessible_name=item["name"],
        label=item["label"],
        visible=bool(item["visible"]),
        enabled=bool(item["enabled"]),
        sensitive=bool(item["sensitive"]),
        has_value=bool(item["hasValue"]),
        selected_text=item["selectedText"],
        options=tuple(item["options"]),
        contexts=tuple(ContextEntry(c["kind"], c["name"], c["key"]) for c in item["contexts"]),
        frame_titles=plan.titles,
        tag=str(item.get("tag", "")),
        interaction=str(item.get("interaction", "open")),
        multiple=bool(item.get("multiple", False)),
    )
