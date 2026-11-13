"""Hedef çözümleyici: yapılandırılmış anlamsal tanım + güncel snapshot → resolved / ambiguous / unresolved.

Kurallar (docs/03 Hedef çözümü):
- Tekil eşleşme ve bağlam hard gate'tir; birden fazla eşleşme ilk/n'inci seçilerek çözülmez.
- Kapsam eksikse (partial/timed_out/inaccessible/not_scanned ya da yalnız hafif taranmış frame) "yok"
  denmez ve
  tekil görünen eşleşme de tekilliği kanıtlanmadığı için resolved sayılmaz.
- Model güven puanı yoktur; sonuç yalnızca gözlenen kanıta dayanır.
- Görünmeyen/devre dışı adaylar da aday sayılır (gizli kopya ihtimali); bu yüzden belirsizlik gizlenmez.
- Etkileşim bağlamı (ADR 0014): kapalı/gizli bir pencerenin içindeki aday aktif hedef olamaz. Açık modalın
  arkasındaki, sayfayı kaplayan katmanın altındaki veya inert aday kullanılamaz; tek etkileşime açık aday
  varsa o seçilir, hiç yoksa "engellendi" sonucu verilir. Aynı belgede birden fazla bağımsız aktif pencere
  varsa hangisinin etkin olduğu belirsizdir; çözüm yapılmaz.
- Varlık kanıtı (presence=True, ekran işaretleri): ekranın kimliği, üstünde pencere açık olsa da kanıtlanır;
  engellenmiş aday kullanılabilir sayılır. Pencere politikası yürütücünün engelleyici kontrolündedir. İşlem
  hedefleri her zaman katı kuralla (presence=False) çözülür.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentask.domain.observation import ControlKind, FrameObservation, ObservedControl, ScanStatus, Snapshot

_SPACES = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).replace("İ", "i").replace("I", "ı")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).replace("ı", "i").casefold()
    return _SPACES.sub(" ", text).strip().rstrip(":*").strip()


class TargetSpec(BaseModel):
    """Anlamsal alan tanımı. Selector, id, frame sırası veya koordinat alanı yoktur (extra=forbid)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ControlKind
    labels: list[str] = Field(min_length=1, max_length=10)
    region: str | None = Field(default=None, min_length=1, max_length=200)
    frame_title: str | None = Field(default=None, min_length=1, max_length=200)
    row_key: str | None = Field(default=None, min_length=1, max_length=200)
    require_visible: bool = True
    require_enabled: bool = True

    @field_validator("labels")
    @classmethod
    def _labels_not_blank(cls, value: list[str]) -> list[str]:
        if any(len(label) > 200 or not normalize_name(label) for label in value):
            raise ValueError("etiketler boş olamaz ve en fazla 200 karakter olmalı")
        return value

    def normalized_labels(self) -> frozenset[str]:
        return frozenset(n for n in (normalize_name(label) for label in self.labels) if n)


class Outcome(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    candidate_id: str
    kind: str
    label: str | None
    accessible_name: str | None
    contexts: tuple[dict[str, str | None], ...]
    frame_titles: tuple[str, ...]
    visible: bool
    enabled: bool
    interaction: str = "open"

    @classmethod
    def of(cls, control: ObservedControl) -> CandidateSummary:
        return cls(
            candidate_id=control.candidate_id,
            kind=control.kind.value,
            label=control.label,
            accessible_name=control.accessible_name,
            contexts=tuple({"kind": c.kind, "name": c.name, "key": c.key} for c in control.contexts),
            frame_titles=control.frame_titles,
            visible=control.visible,
            enabled=control.enabled,
            interaction=control.interaction,
        )


@dataclass(frozen=True, slots=True)
class Coverage:
    overall: ScanStatus
    scope_frame_refs: tuple[str, ...]
    incomplete: tuple[FrameObservation, ...]


@dataclass(frozen=True, slots=True)
class Resolution:
    outcome: Outcome
    reason: str
    snapshot_revision: str
    candidate_id: str | None
    candidates: tuple[CandidateSummary, ...]
    coverage: Coverage
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "snapshot_revision": self.snapshot_revision,
            "candidate_id": self.candidate_id,
            "candidates": [asdict(c) for c in self.candidates],
            "coverage": {
                "overall": self.coverage.overall.value,
                "scope_frame_refs": list(self.coverage.scope_frame_refs),
                "incomplete": [
                    {
                        "frame_ref": f.frame_ref,
                        "title": f.title,
                        "status": f.status.value,
                        "reason": f.reason or ("only_summary_scanned" if not f.detail_scanned else None),
                    }
                    for f in self.coverage.incomplete
                ],
            },
            "explanation": self.explanation,
        }


def _is_complete(frame: FrameObservation, summary_cleared: frozenset[str]) -> bool:
    # Hafif özeti tam olup tanımdaki adların hiçbirini içermeyen frame'de eşleşme olamaz.
    if frame.status is not ScanStatus.COMPLETE:
        return False
    return frame.detail_scanned or frame.frame_ref in summary_cleared


def _overall(incomplete: tuple[FrameObservation, ...]) -> ScanStatus:
    statuses = {f.status for f in incomplete}
    for status in (ScanStatus.TIMED_OUT, ScanStatus.INACCESSIBLE, ScanStatus.NOT_SCANNED, ScanStatus.PARTIAL):
        if status in statuses:
            return status
    return ScanStatus.PARTIAL if incomplete else ScanStatus.COMPLETE


def scope_frames(spec: TargetSpec, snapshot: Snapshot) -> tuple[FrameObservation, ...]:
    if spec.frame_title is None:
        return snapshot.frames
    wanted = normalize_name(spec.frame_title)
    return tuple(f for f in snapshot.frames if f.title is not None and normalize_name(f.title) == wanted)


def matches(spec: TargetSpec, control: ObservedControl) -> bool:
    if control.kind is not spec.kind:
        return False
    names = {normalize_name(n) for n in (control.label, control.accessible_name) if n}
    if not names & spec.normalized_labels():
        return False
    if spec.region is not None:
        region = normalize_name(spec.region)
        if not any(
            c.kind != "table_row" and c.name and normalize_name(c.name) == region for c in control.contexts
        ):
            return False
    if spec.row_key is not None:
        key = spec.row_key.strip()
        if not any(
            c.kind == "table_row" and c.key is not None and c.key.strip() == key for c in control.contexts
        ):
            return False
    return True


INACTIVE_INTERACTION = frozenset({"inactive_dialog"})
BLOCKED_INTERACTION = frozenset({"behind_dialog", "overlay", "inert"})
_BLOCKED_TEXT = {
    "behind_dialog": "açık bir pencerenin arkasında",
    "overlay": "sayfayı kaplayan bir katmanın altında",
    "inert": "etkileşime kapalı bir bölümde",
}


def resolve(
    spec: TargetSpec,
    snapshot: Snapshot,
    summary_cleared: frozenset[str] = frozenset(),
    presence: bool = False,
) -> Resolution:
    """summary_cleared: hafif özeti tam olan ve tanımdaki adları içermeyen frame ref'leri."""
    scope = scope_frames(spec, snapshot)
    scope_refs = tuple(f.frame_ref for f in scope)
    incomplete = tuple(f for f in scope if not _is_complete(f, summary_cleared))
    if spec.frame_title is not None and not scope:
        # Başlıklı frame görülmedi; başka frame eksik tarandıysa orada olabilir.
        incomplete = tuple(f for f in snapshot.frames if not _is_complete(f, summary_cleared))
    coverage = Coverage(_overall(incomplete), scope_refs, incomplete)
    matched = tuple(c for c in snapshot.controls if c.frame_ref in scope_refs and matches(spec, c))
    # Kapalı penceredeki kopyalar aday değildir; engellenmiş adaylar aday listesinde görünür ama kullanılamaz.
    found = tuple(c for c in matched if c.interaction not in INACTIVE_INTERACTION)
    usable: tuple[ObservedControl, ...]
    blocked: tuple[ObservedControl, ...]
    if presence:
        usable, blocked = found, ()
    else:
        usable = tuple(c for c in found if c.interaction not in BLOCKED_INTERACTION)
        blocked = tuple(c for c in found if c.interaction in BLOCKED_INTERACTION)
    candidates = tuple(CandidateSummary.of(c) for c in found)

    def result(
        outcome: Outcome, reason: str, explanation: str, candidate_id: str | None = None
    ) -> Resolution:
        return Resolution(outcome, reason, snapshot.revision, candidate_id, candidates, coverage, explanation)

    if not presence and any(c.interaction == "dialog_ambiguous" for c in found):
        return result(
            Outcome.UNRESOLVED,
            "multiple_active_dialogs",
            "Aynı anda birden fazla etkin pencere açık; hangisinde işlem yapılacağı belirsiz. "
            "Müdahale gerekiyor.",
        )
    if len(usable) > 1:
        return result(
            Outcome.AMBIGUOUS,
            "multiple_candidates",
            f"Tanıma uyan {len(usable)} kontrol var; bölüm, frame veya satır bağlamıyla daraltın.",
        )
    if incomplete:
        detail = "tekil olduğu kanıtlanamadı" if found else "hedefin olmadığı kesin değil"
        return result(
            Outcome.UNRESOLVED,
            "coverage_incomplete",
            f"Taranamayan veya eksik taranan {len(incomplete)} bölge var; {detail}.",
        )
    if not usable and blocked:
        where = _BLOCKED_TEXT.get(blocked[0].interaction, "etkileşime kapalı")
        return result(
            Outcome.UNRESOLVED,
            "blocked",
            f"Tanıma uyan kontrol {where}; üzerinde işlem yapılmadı. Müdahale gerekiyor.",
        )
    if not usable:
        return result(
            Outcome.UNRESOLVED, "not_found", "İncelenen kapsamın tamamında tanıma uyan kontrol yok."
        )
    target = usable[0]
    missing = []
    if spec.require_visible and not target.visible:
        missing.append("görünür değil")
    if spec.require_enabled and not target.enabled:
        missing.append("etkin değil")
    if missing:
        return result(Outcome.UNRESOLVED, "evidence_missing", f"Tek aday bulundu ancak {', '.join(missing)}.")
    return result(Outcome.RESOLVED, "unique_match", "Tanıma uyan tek kontrol bulundu.", target.candidate_id)
