"""Gözlem veri modeli. Değerler (textbox içeriği, hassas alan metni) burada tutulmaz."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agentask.domain.frames import Lineage


class ControlKind(StrEnum):
    TEXTBOX = "textbox"
    BUTTON = "button"
    SELECT = "select"
    COMBOBOX = "combobox"
    TAB = "tab"
    TABLE = "table"


class ScanStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INACCESSIBLE = "inaccessible"
    TIMED_OUT = "timed_out"
    NOT_SCANNED = "not_scanned"


@dataclass(frozen=True, slots=True)
class ContextEntry:
    """Mantıksal bağlam: form, region, dialog, tabpanel, group veya table_row (key = satırın ilk hücresi)."""

    kind: str
    name: str | None
    key: str | None


@dataclass(frozen=True, slots=True)
class ObservedControl:
    candidate_id: str
    frame_ref: str
    kind: ControlKind
    role: str
    accessible_name: str | None
    label: str | None
    visible: bool
    enabled: bool
    sensitive: bool
    has_value: bool
    selected_text: str | None
    options: tuple[str, ...]
    contexts: tuple[ContextEntry, ...]
    frame_titles: tuple[str, ...]
    tag: str = ""


@dataclass(frozen=True, slots=True)
class FrameObservation:
    frame_ref: str
    parent_ref: str | None
    title: str | None
    origin: str | None
    path: str | None
    depth: int
    lineage: Lineage
    status: ScanStatus
    reason: str | None
    detail_scanned: bool
    control_count: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    revision: str
    created_at: datetime
    frames: tuple[FrameObservation, ...]
    controls: tuple[ObservedControl, ...]

    def frame(self, ref: str) -> FrameObservation | None:
        return next((f for f in self.frames if f.frame_ref == ref), None)

    def control(self, candidate_id: str) -> ObservedControl | None:
        return next((c for c in self.controls if c.candidate_id == candidate_id), None)


@dataclass(frozen=True, slots=True)
class LightFrame:
    """Hafif frame özeti: durum ve kontrol ad/etiket metinleri (bağlam ve değer yok)."""

    frame_ref: str
    title: str | None
    status: ScanStatus
    reason: str | None
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PickEvent:
    """Seçim modunda kullanıcının işaretlediği kontrol (veya desteklenmeyen öğe)."""

    candidate_id: str | None
    snapshot_revision: str | None
    reason: str
