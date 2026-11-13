"""Gözlem ve hedef çözümü use case'leri. Bütün sayfa işleri oturum kilidi (operation) altında yapılır.

Çözüm iki aşamalıdır: (1) bütün frame'lerin hafif özeti (ad/etiket metinleri), (2) yalnız tanımdaki adları
içeren frame'lerin ayrıntılı envanteri. Özeti tam olup adı içermeyen frame'ler kapsam dışı
kanıtlanmış sayılır;
özeti eksik/okunamayan frame'ler kapsam eksikliği olarak sonuçta kalır.
"""

from __future__ import annotations

import logging
from typing import Any

from agentask.application.controls import AdapterError, AdapterRegistry, ControlUnsupported
from agentask.application.errors import CandidateStale, InterruptionChanged
from agentask.application.observability import log_event
from agentask.application.ports.observation import PageObserverPort
from agentask.application.services.browser_sessions import BrowserSessionService
from agentask.domain.choices import describe_options
from agentask.domain.observation import ControlKind, ObservedControl, PickEvent, ScanStatus, Snapshot
from agentask.domain.screens import ScreenDef, ScreenVerdict, judge, spec_key
from agentask.domain.targeting import Outcome, Resolution, TargetSpec, normalize_name, resolve

KIND_LABELS = {
    ControlKind.TEXTBOX: "metin alanı",
    ControlKind.BUTTON: "düğme",
    ControlKind.SELECT: "açılır liste",
    ControlKind.COMBOBOX: "özel açılır liste",
    ControlKind.TAB: "sekme",
    ControlKind.TABLE: "tablo",
    ControlKind.LINK: "bağlantı",
    ControlKind.CHECKBOX: "onay kutusu",
    ControlKind.RADIO_GROUP: "seçenek grubu",
    ControlKind.FILE: "dosya alanı",
}


logger = logging.getLogger(__name__)
UNSUPPORTED_CHOICE_TEXT = {
    "input_combobox_not_supported": (
        "Bu alan yazarak arama yapan bir kutu. Yazarak arama henüz desteklenmiyor; bu alan için seçim adımı "
        "kurulamaz."
    ),
    "multi_select_not_supported": "Bu alan birden fazla seçime izin veriyor; çoklu seçim desteklenmiyor.",
    "sensitive_target_requires_secret_ref": "Bu hassas bir alan; seçenekleri okunmaz, adım kurulamaz.",
    "listbox_not_accessible": (
        "Liste açıldı ama seçenekleri ekrandan güvenilir biçimde okunamadı. Bu bileşen desteklenmiyor; "
        "rastgele tıklama yapılmadı."
    ),
    "not_a_choice_control": "Bu bir seçim alanı değil. Açılır liste veya seçim kutusu seçin.",
    "not_multi_select": "Bu alan birden fazla seçime izin vermiyor; “Seçim yap” bileşenini kullanın.",
    "autocomplete_requires_input": "Yazınca öneri açan alan yalnız metin girişinde desteklenir.",
}


def caption_for(control: ObservedControl) -> str:
    name = control.label or control.accessible_name or "(adsız)"
    context = " › ".join(
        [
            *control.frame_titles,
            *(f"{c.name} [{c.key}]" if c.key else (c.name or c.kind) for c in reversed(control.contexts)),
        ]
    )
    return " · ".join(part for part in (name, KIND_LABELS[control.kind], context) if part)


async def resolve_target(observer: PageObserverPort, spec: TargetSpec, presence: bool = False) -> Resolution:
    """İki aşamalı çözüm (hafif özet → ilgili frame ayrıntısı). Çağıran oturum kilidini tutmalıdır.
    presence=True yalnız ekran işaretleri içindir (varlık kanıtı; bkz. domain/targeting)."""
    light = await observer.light_scan()
    wanted = spec.normalized_labels()
    title = normalize_name(spec.frame_title) if spec.frame_title else None
    relevant: set[str] = set()
    cleared: set[str] = set()
    for frame in light:
        if title is not None and (frame.title is None or normalize_name(frame.title) != title):
            continue
        if any(normalize_name(n) in wanted for n in frame.names):
            relevant.add(frame.frame_ref)
        elif frame.status is ScanStatus.COMPLETE:
            cleared.add(frame.frame_ref)
    snapshot = await observer.observe(detail_refs=relevant, light=light)
    return resolve(spec, snapshot, summary_cleared=frozenset(cleared), presence=presence)


async def assess_screen(observer: PageObserverPort, screen: ScreenDef) -> ScreenVerdict:
    """Ortak ekran doğrulaması (Designer/Assistant yürütmesi). Her işaret GÜNCEL gözlemle çözülür; önceki
    snapshot veya aday kimliği kullanılmaz. Çağıran oturum kilidini tutmalıdır."""
    resolved: dict[str, Resolution] = {}
    for spec in (*screen.markers, *screen.absent_markers):
        resolved[spec_key(spec)] = await resolve_target(observer, spec, presence=True)
    return judge(screen, lambda spec: resolved[spec_key(spec)])


def assess_screen_on(snapshot: Snapshot, screen: ScreenDef) -> ScreenVerdict:
    """Aynı karar kuralları, tek bir tam snapshot üzerinde (Changes ekranı)."""
    return judge(screen, lambda spec: resolve(spec, snapshot, presence=True))


class ObservationService:
    def __init__(self, sessions: BrowserSessionService, picker_wait_max_ms: int) -> None:
        self.sessions = sessions
        self._picker_wait_max_ms = picker_wait_max_ms

    def current_snapshot(self, owner_id: str, session_id: str) -> Snapshot | None:
        return self.sessions.peek(owner_id, session_id).observer.current_snapshot

    async def navigate(self, owner_id: str, session_id: str, url: str) -> str:
        async with self.sessions.operation(owner_id, session_id, "navigate") as handle:
            await handle.navigate(url)
            return handle.current_url

    async def observe(self, owner_id: str, session_id: str) -> Snapshot:
        async with self.sessions.operation(owner_id, session_id, "observe") as handle:
            return await handle.observer.observe()

    async def resolve(self, owner_id: str, session_id: str, spec: TargetSpec) -> Resolution:
        async with self.sessions.operation(owner_id, session_id, "resolve") as handle:
            return await resolve_target(handle.observer, spec)

    async def choice_options(
        self,
        owner_id: str,
        session_id: str,
        spec: TargetSpec,
        open_list: bool,
        search: str | None = None,
        multi: bool = False,
    ) -> dict[str, Any]:
        """Seçim alanının güncel seçenekleri. Hedef tanımdan yeniden çözülür (eski aday kullanılmaz). Seçim
        yapmaz; özel liste yalnız open_list=True (açık kullanıcı eylemi) ile açılıp yine kapatılır."""
        async with self.sessions.operation(owner_id, session_id, "choice_options") as handle:
            observer = handle.observer
            resolution = await resolve_target(observer, spec)
            snapshot = observer.current_snapshot
            control = (
                snapshot.control(resolution.candidate_id) if snapshot and resolution.candidate_id else None
            )
            if resolution.outcome is not Outcome.RESOLVED or control is None:
                return {
                    "status": "unresolved",
                    "reason": resolution.reason,
                    "message": resolution.explanation,
                    "options": [],
                }
            registry = AdapterRegistry.default()
            try:
                if multi:
                    registry_multi = registry.for_multi(control)
                    inspection = await registry_multi.inspect_options(handle.driver, control, False)
                    adapter_name = registry_multi.name
                elif search:
                    inspection = await registry.for_autocomplete(control).preview(
                        handle.driver, control, search
                    )
                    adapter_name = "autocomplete"
                else:
                    adapter = registry.for_control(control)
                    inspection = await adapter.inspect_options(handle.driver, control, open_list)
                    adapter_name = adapter.name
            except ControlUnsupported as exc:
                return {
                    "status": "unsupported",
                    "reason": exc.message,
                    "message": UNSUPPORTED_CHOICE_TEXT.get(
                        exc.message, "Bu kontrol türü desteklenmiyor; seçim adımı kurulamaz."
                    ),
                    "options": [],
                }
            except AdapterError as exc:
                return {
                    "status": "failed",
                    "reason": exc.error_class.value,
                    "message": exc.message,
                    "options": [],
                }
            return {
                "status": inspection.status,
                "control": adapter_name,
                "reason": None,
                "message": (
                    "Seçenekleri görmek için listenin açılması gerekiyor."
                    if inspection.status == "needs_open"
                    else None
                ),
                "current": inspection.current,
                "options": describe_options(inspection.options),
            }

    async def highlight(self, owner_id: str, session_id: str, candidate_id: str) -> ObservedControl:
        async with self.sessions.operation(owner_id, session_id, "highlight") as handle:
            observer = handle.observer
            reason = await observer.check_candidate(candidate_id)
            snapshot = observer.current_snapshot
            control = snapshot.control(candidate_id) if snapshot else None
            if reason is not None or control is None:
                raise CandidateStale(details={"reason": reason or "unknown_candidate"})
            await observer.highlight(candidate_id, caption_for(control))
            return control

    async def clear_highlight(self, owner_id: str, session_id: str) -> None:
        async with self.sessions.operation(owner_id, session_id, "highlight") as handle:
            await handle.observer.clear_highlight()

    async def start_picker(self, owner_id: str, session_id: str) -> None:
        async with self.sessions.operation(owner_id, session_id, "picker") as handle:
            await handle.observer.start_picker()

    async def stop_picker(self, owner_id: str, session_id: str) -> None:
        async with self.sessions.operation(owner_id, session_id, "picker") as handle:
            await handle.observer.stop_picker()

    def interruptions(self, owner_id: str, session_id: str) -> dict[str, Any]:
        """Oturumdaki görünen kesintiler ve kimlikleri (kilitsiz, tarayıcıya dokunmaz). Hiçbiri otomatik
        kapatılmaz."""
        handle = self.sessions.peek(owner_id, session_id)
        return {
            **handle.observer.interruption_state(),
            "focused_window": getattr(handle, "focused_origin", None),
        }

    async def resolve_interruption(
        self, owner_id: str, session_id: str, action: str, ids: list[str]
    ) -> dict[str, Any]:
        """Yalnız kullanıcının açık kararıyla ve yalnız kararın verildiği (görülen) kesinti kimlikleri
        için. Sahiplik her çağrıda denetlenir (kapanmış oturum "bulunamadı"). Oturum kilidi ALINMAZ: native
        dialog açıkken sayfa betikleri durur ve süren bir işlem kilidi tutarak asılı kalabilir.
        Eşzamanlı/tekrarlanan kararlar gözlemcinin karar kilidiyle sıralanır; kimlik eskiyse hiçbir şey
        kapatılmaz."""
        observer = self.sessions.peek(owner_id, session_id).observer
        if action in {"design_new_window", "design_main_window"}:  # sayfa değişir: oturum kilidiyle
            async with self.sessions.operation(owner_id, session_id, "designer") as handle:
                if action == "design_main_window":
                    handle.release_windows()
                    done = True
                else:
                    done = len(ids) == 1 and await handle.focus_window(ids[0])
        elif action == "dismiss_browser_dialog":
            done = len(ids) == 1 and await observer.dismiss_native_dialog(ids[0])
        else:
            done = await observer.close_new_windows(ids) is not None
        if not done:
            raise InterruptionChanged()
        log_event(
            logger,
            "interruption_resolved",
            audit=True,
            outcome="applied",
            actor=owner_id,
            action=action,
            count=len(ids),
            session_id=session_id,
        )
        return self.interruptions(owner_id, session_id)

    async def wait_pick(self, owner_id: str, session_id: str, wait_ms: int) -> PickEvent | None:
        """Seçim olayını bekler (kilitsiz), sonra kilit altında adaya çevirir. Olay yoksa None."""
        wait_ms = max(0, min(wait_ms, self._picker_wait_max_ms))
        observer = self.sessions.peek(owner_id, session_id).observer
        if not await observer.wait_raw_pick(wait_ms / 1000):
            return None
        async with self.sessions.operation(owner_id, session_id, "picker") as handle:
            event = await handle.observer.map_pick()
            snapshot = handle.observer.current_snapshot
            control = snapshot.control(event.candidate_id) if snapshot and event.candidate_id else None
            if control is not None:
                await handle.observer.highlight(control.candidate_id, caption_for(control))
            return event
