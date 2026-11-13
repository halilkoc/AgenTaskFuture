"""Ekran tanımı (ScreenDef), mantıksal bölgeler ve ortak ekran doğrulama çekirdeği (R3, docs/02 Screen).

Tanım yalnız anlamsal kanıt taşır: tanıma işaretleri TargetSpec'tir (tür + etiket + bölüm/frame başlığı).
Selector, XPath, DOM id, frame sırası, URL veya koordinat yoktur (extra=forbid, TargetSpec kuralları).

Karar kuralları (model yok, güven puanı yok):
- Her zorunlu işaret güncel gözlemde TEKİL çözülmelidir (resolved). Birden fazla eşleşme → ekran belirsiz.
- Her yasak işaret (benzer yanlış ekranı ayıran kontrol) tam kapsamla "yok" kanıtlanmalıdır. Bulunursa
  ekran yanlıştır; kapsam eksikse "yok" denmez → kanıt eksik.
- Her mantıksal bölge en az bir zorunlu işaretle kanıtlanır; yani bölge, içindeki tekil işaret gözlenerek
  doğrulanır (yinelenen bölgede o işaret tekil olamaz).
- Ekran tanıma işlemin kendi hedefini bulmasına dayanamaz: işaretlerin en az biri adımların kullandığı
  elemanlardan farklı olmalıdır. Ekran tanınması da elemanın doğru olduğunu kanıtlamaz; eleman ayrıca
  çözülür (döngüsel doğrulama yok).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentask.domain.release import canonical_hash
from agentask.domain.targeting import Outcome, Resolution, TargetSpec, normalize_name

_SLUG = r"^[a-z][a-z0-9_]{0,60}$"


def spec_key(spec: TargetSpec) -> str:
    """TargetSpec için kararlı anahtar (liste alanı olduğundan hash'lenemez)."""
    return canonical_hash(spec.model_dump(mode="json"))


class RegionDef(BaseModel):
    """Mantıksal bölge: ekranda adıyla gözlenen bölüm (section/region/form/group/dialog/tabpanel adı)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    region_id: str = Field(pattern=_SLUG)
    name: str = Field(min_length=1, max_length=200)

    @property
    def key(self) -> str:
        return normalize_name(self.name)


class ScreenDef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    screen_id: str = Field(pattern=_SLUG)
    title: str = Field(min_length=1, max_length=200)
    regions: list[RegionDef] = Field(default_factory=list, max_length=20)
    markers: list[TargetSpec] = Field(min_length=1, max_length=10)
    absent_markers: list[TargetSpec] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        keys = [r.key for r in self.regions]
        if not all(keys):
            raise ValueError("bölge adı boş olamaz")
        if len(set(keys)) != len(keys) or len({r.region_id for r in self.regions}) != len(self.regions):
            raise ValueError("bölge kimlikleri ve adları tekil olmalı")
        required = [spec_key(m) for m in self.markers]
        if len(set(required)) != len(required):
            raise ValueError("aynı tanıma işareti iki kez eklenemez")
        if set(required) & {spec_key(m) for m in self.absent_markers}:
            raise ValueError("bir işaret hem zorunlu hem yasak olamaz")
        marker_regions = {normalize_name(m.region) for m in self.markers if m.region}
        for region in self.regions:
            if region.key not in marker_regions:
                raise ValueError(f"'{region.name}' bölgesi en az bir tanıma işaretiyle kanıtlanmalı")
        return self

    def region_for(self, name: str | None) -> RegionDef | None:
        if not name:
            return None
        key = normalize_name(name)
        return next((r for r in self.regions if r.key == key), None)

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def ref(self) -> dict[str, str]:
        return {"screen_id": self.screen_id, "content_hash": self.content_hash()}


class ScreenStatus(StrEnum):
    RECOGNIZED = "recognized"
    NOT_RECOGNIZED = "not_recognized"  # zorunlu işaret yok ya da yasak işaret var (yanlış/benzer ekran)
    AMBIGUOUS = "ambiguous"  # işaret tekil değil (ör. yinelenen bölge)
    INCOMPLETE = "incomplete"  # kapsam eksik; ekranın doğru/yanlış olduğu kanıtlanamadı


@dataclass(frozen=True, slots=True)
class MarkerResult:
    role: str  # "required" | "absent"
    target: dict[str, Any]
    outcome: str
    reason: str
    candidates: int


@dataclass(frozen=True, slots=True)
class ScreenVerdict:
    screen_id: str
    status: ScreenStatus
    explanation: str
    markers: tuple[MarkerResult, ...] = field(default_factory=tuple)

    @property
    def recognized(self) -> bool:
        return self.status is ScreenStatus.RECOGNIZED

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "status": self.status.value,
            "recognized": self.recognized,
            "explanation": self.explanation,
            "markers": [
                {
                    "role": m.role,
                    "target": m.target,
                    "outcome": m.outcome,
                    "reason": m.reason,
                    "candidates": m.candidates,
                }
                for m in self.markers
            ],
        }


def _describe(spec: TargetSpec) -> str:
    where = f" ({spec.region})" if spec.region else ""
    return f"'{spec.labels[0]}'{where}"


def judge(screen: ScreenDef, resolver: Callable[[TargetSpec], Resolution]) -> ScreenVerdict:
    """Ortak karar fonksiyonu: Designer, Assistant (yürütme) ve Changes aynı kuralları kullanır.

    resolver her çağrıda GÜNCEL gözlemden çözüm vermelidir; önceki snapshot/locator taşınmaz."""
    results: list[MarkerResult] = []
    ambiguous: list[str] = []
    missing: list[str] = []
    incomplete: list[str] = []
    blocked: list[str] = []
    present_forbidden: list[str] = []
    for spec in screen.markers:
        r = resolver(spec)
        results.append(_result("required", spec, r))
        if r.outcome is Outcome.AMBIGUOUS:
            ambiguous.append(_describe(spec))
        elif r.outcome is not Outcome.RESOLVED:
            bucket = {
                "coverage_incomplete": incomplete,
                "blocked": blocked,
                "multiple_active_dialogs": blocked,
            }
            bucket.get(r.reason, missing).append(_describe(spec))
    for spec in screen.absent_markers:
        r = resolver(spec)
        results.append(_result("absent", spec, r))
        if r.candidates:
            present_forbidden.append(_describe(spec))
        elif r.reason == "coverage_incomplete":
            incomplete.append(_describe(spec))
    if present_forbidden:
        status, text = (
            ScreenStatus.NOT_RECOGNIZED,
            f"Bu ekranda olmaması gereken kontrol görüldü: {', '.join(present_forbidden)}; "
            "benzer ama farklı bir ekran.",
        )
    elif ambiguous:
        status, text = (
            ScreenStatus.AMBIGUOUS,
            f"Tanıma işareti tekil değil: {', '.join(ambiguous)}; bölge yinelenmiş olabilir.",
        )
    elif blocked:
        status, text = (
            ScreenStatus.NOT_RECOGNIZED,
            f"Ekran kanıtı bir pencere veya katmanın arkasında kaldı: {', '.join(blocked)}; "
            "tanımlı olmayan pencere kapatılmadı, müdahale gerekiyor.",
        )
    elif missing:
        status, text = (
            ScreenStatus.NOT_RECOGNIZED,
            f"Beklenen ekran kanıtı bulunamadı: {', '.join(missing)}.",
        )
    elif incomplete:
        status, text = (
            ScreenStatus.INCOMPLETE,
            f"Ekranın bir kısmı taranamadı; şu kanıtlar doğrulanamadı: {', '.join(incomplete)}.",
        )
    else:
        status, text = ScreenStatus.RECOGNIZED, f"'{screen.title}' ekranı tanındı."
    return ScreenVerdict(screen.screen_id, status, text, tuple(results))


def _result(role: str, spec: TargetSpec, r: Resolution) -> MarkerResult:
    return MarkerResult(
        role,
        spec.model_dump(mode="json", exclude_none=True),
        r.outcome.value,
        r.reason,
        len(r.candidates),
    )


def static_issues(
    screen: ScreenDef | None, element_targets: dict[str, TargetSpec], used_element_ids: Iterable[str]
) -> list[str]:
    """Taslak/yayın öncesi statik kurallar (gözlem gerektirmez)."""
    if screen is None:
        return ["screen_missing"]
    issues: list[str] = []
    used = [element_targets[e] for e in used_element_ids if e in element_targets]
    if all(m in used for m in screen.markers):
        issues.append("screen_markers_only_targets")
    for element_id, spec in sorted(element_targets.items()):
        if spec.region and screen.region_for(spec.region) is None:
            issues.append(f"element_region_not_in_screen:{element_id}")
    return issues
