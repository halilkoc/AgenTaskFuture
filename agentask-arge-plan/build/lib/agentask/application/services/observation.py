"""Gözlem ve hedef çözümü use case'leri. Bütün sayfa işleri oturum kilidi (operation) altında yapılır.

Çözüm iki aşamalıdır: (1) bütün frame'lerin hafif özeti (ad/etiket metinleri), (2) yalnız tanımdaki adları
içeren frame'lerin ayrıntılı envanteri. Özeti tam olup adı içermeyen frame'ler kapsam dışı
kanıtlanmış sayılır;
özeti eksik/okunamayan frame'ler kapsam eksikliği olarak sonuçta kalır.
"""

from __future__ import annotations

from agentask.application.errors import CandidateStale
from agentask.application.ports.observation import PageObserverPort
from agentask.application.services.browser_sessions import BrowserSessionService
from agentask.domain.observation import ControlKind, ObservedControl, PickEvent, ScanStatus, Snapshot
from agentask.domain.targeting import Resolution, TargetSpec, normalize_name, resolve

KIND_LABELS = {
    ControlKind.TEXTBOX: "metin alanı",
    ControlKind.BUTTON: "düğme",
    ControlKind.SELECT: "açılır liste",
    ControlKind.COMBOBOX: "özel açılır liste",
    ControlKind.TAB: "sekme",
    ControlKind.TABLE: "tablo",
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


async def resolve_target(observer: PageObserverPort, spec: TargetSpec) -> Resolution:
    """İki aşamalı çözüm (hafif özet → ilgili frame ayrıntısı). Çağıran oturum kilidini tutmalıdır."""
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
    return resolve(spec, snapshot, summary_cleared=frozenset(cleared))


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
