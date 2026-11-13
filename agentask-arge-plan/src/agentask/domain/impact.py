"""Anlamsal değişiklik ve etki analizi (docs/04 Değişiklik ekranı).

Yayımlanmış elemanlar (TargetSpec) yeni gözleme karşı çözülür; HTML id, sıra, zaman ve kayıt değerleri
karşılaştırılmaz.
Kapsam eksikse sonuç 'unknown'dır (kayboldu denmez). Yeniden adlandırma yalnız öneridir. Onarım yeni
taslak açar;
etkin yayın kendiliğinden değişmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from agentask.domain.catalog import OperationDraft, StepStatus
from agentask.domain.observation import Snapshot
from agentask.domain.screens import ScreenDef
from agentask.domain.targeting import Outcome, TargetSpec, normalize_name, resolve


class PublishedOperation(BaseModel):
    operation_id: str
    revision: int
    content_hash: str
    definition: dict[str, Any]


class ElementStatus(StrEnum):
    UNCHANGED = "unchanged"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    HIDDEN_OR_DISABLED = "hidden_or_disabled"
    UNKNOWN = "unknown"


@dataclass
class ElementCheck:
    operation_id: str
    element_id: str
    meaning: str
    target: dict[str, Any]
    status: ElementStatus
    reason: str
    suggestions: list[dict[str, Any]] = field(default_factory=list)


def classify_elements(op: PublishedOperation, snapshot: Snapshot) -> list[ElementCheck]:
    checks: list[ElementCheck] = []
    for element_id, element in op.definition["elements"].items():
        spec = TargetSpec.model_validate(element["target"])
        result = resolve(spec, snapshot)
        if result.outcome is Outcome.RESOLVED:
            status = ElementStatus.UNCHANGED
        elif result.outcome is Outcome.AMBIGUOUS:
            status = ElementStatus.AMBIGUOUS
        elif result.reason == "evidence_missing":
            status = ElementStatus.HIDDEN_OR_DISABLED
        elif result.reason == "coverage_incomplete":
            status = ElementStatus.UNKNOWN
        else:
            status = ElementStatus.NOT_FOUND
        suggestions: list[dict[str, Any]] = []
        if status is ElementStatus.NOT_FOUND:
            region = normalize_name(spec.region) if spec.region else None
            old = {w for label in spec.labels for w in normalize_name(label).split() if len(w) >= 3}
            scored = []
            for c in snapshot.controls:
                same_region = region is None or any(
                    x.name and normalize_name(x.name) == region for x in c.contexts
                )
                words = set(normalize_name(c.label or c.accessible_name or "").split())
                overlap = sum(1 for w in old if any(x.startswith(w[:4]) for x in words))
                if c.kind is spec.kind and same_region and overlap:
                    scored.append(
                        (
                            overlap,
                            {
                                "label": c.label or c.accessible_name,
                                "kind": c.kind.value,
                                "contexts": [x.name for x in c.contexts if x.name],
                            },
                        )
                    )
            suggestions = [s for _, s in sorted(scored, key=lambda x: -x[0])]
        checks.append(
            ElementCheck(
                op.operation_id,
                element_id,
                element["meaning"],
                element["target"],
                status,
                result.reason,
                suggestions[:5],
            )
        )
    return checks


@dataclass
class ImpactedOperation:
    operation_id: str
    revision: int
    reasons: list[str]
    regression_tests: list[str]


def _kind_of(op: PublishedOperation, element_id: str | None) -> str | None:
    element = op.definition["elements"].get(element_id or "")
    return element["target"]["kind"] if element else None


def impact_of(
    operations: list[PublishedOperation],
    *,
    elements: set[tuple[str, str]] | None = None,
    adapter_kinds: set[str] | None = None,
    action_ids: set[str] | None = None,
    screen_ids: set[str] | None = None,
) -> list[ImpactedOperation]:
    """Değişen elemanlar (op_id, element_id) aynı anlamsal hedefi kullanan bütün işlemlere yayılır. R4: aynı
    hedefi tetikleyici olarak kullanan geçişler ve paylaşılan ekranlar da etki nedenidir."""
    changed_targets = []
    for op_id, element_id in elements or set():
        op = next((o for o in operations if o.operation_id == op_id), None)
        if op and element_id in op.definition["elements"]:
            changed_targets.append(op.definition["elements"][element_id]["target"])
    impacted: list[ImpactedOperation] = []
    for op in operations:
        reasons: list[str] = []
        for element_id, element in op.definition["elements"].items():
            if element["target"] in changed_targets:
                reasons.append(f"element:{element_id}")
        for transition in op.definition.get("transitions", []):
            trigger = transition.get("trigger", {})
            if trigger.get("kind") == "control" and _same_target(trigger.get("target", {}), changed_targets):
                reasons.append(f"transition:{transition['transition_id']}")
        for screen_id in sorted(_screen_ids(op.definition) & (screen_ids or set())):
            reasons.append(f"screen:{screen_id}")
        for step in op.definition["steps"]:
            kind = _kind_of(op, step.get("element_id"))
            if adapter_kinds and kind in adapter_kinds:
                reasons.append(f"adapter:{kind}")
            if action_ids and step.get("action_id") in action_ids:
                reasons.append(f"action:{step['action_id']}")
        if reasons:
            impacted.append(
                ImpactedOperation(
                    op.operation_id,
                    op.revision,
                    sorted(set(reasons)),
                    [f"fresh_session_test:{op.operation_id}"],
                )
            )
    return impacted


def _screen_ids(definition: dict[str, Any]) -> set[str]:
    refs = [definition.get("screen_ref"), *definition.get("screens_ref", [])]
    return {r["screen_id"] for r in refs if isinstance(r, dict)}


def _same_target(target: dict[str, Any], changed: list[dict[str, Any]]) -> bool:
    if not target:
        return False
    norm = TargetSpec.model_validate(target).model_dump(mode="json")
    return any(TargetSpec.model_validate(c).model_dump(mode="json") == norm for c in changed)


def repair_draft(
    op: PublishedOperation,
    broken_elements: set[str],
    *,
    created_by: str,
    base_release_id: str,
    screen: ScreenDef | None = None,
    extra_screens: list[ScreenDef] | None = None,
) -> OperationDraft:
    """Yayımlanmış revizyondan onarım taslağı. Etkilenen adımlar hedef seçimine döner; diğerleri yeniden
    onay ister. Yayının ekran tanımı (varsa) taslağa taşınır; eski (ekransız) yayında taslağa ekran
    tanımı eklenmeden onay verilemez."""
    draft = OperationDraft.from_definition(
        op.definition, created_by=created_by, screen=screen, extra_screens=extra_screens
    )
    draft.description = (draft.description + f" [Onarım: {base_release_id} r{op.revision}]").strip()
    for step in draft.steps:
        step.confirmation, step.trial = None, None
        if step.element_id in broken_elements:
            step.status = StepStatus.INTENT_ENTERED
            step.element_id = None
        else:
            step.status = StepStatus.TARGET_SELECTED
    draft.elements = {k: v for k, v in draft.elements.items() if k not in broken_elements}
    return draft
