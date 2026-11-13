"""Kural tabanlı hazırlama yardımı (modelsiz). Öneriler rule_generated provenance taşır; hiçbiri otomatik
onaylanmaz. Adaylar puanla sıralanır ama eşit puanlılar birlikte gösterilir; ilk aday seçilmez."""

from __future__ import annotations

from dataclasses import dataclass

from agentask.domain.observation import ControlKind, ObservedControl
from agentask.domain.targeting import TargetSpec, normalize_name

_VERBS: list[tuple[str, tuple[str, ...]]] = [
    ("activate_tab", ("sekme", "sekmesine", "sekmesini", "sekmesi")),
    ("find_record", ("bul", "ara", "getir")),
    ("ensure_choice", ("sec", "secin", "seciniz", "belirle")),
    ("ensure_value", ("yaz", "yazin", "gir", "girin", "doldur", "guncelle")),
    ("invoke_approved_action", ("kaydet", "gonder", "onayla", "tamamla")),
    ("read", ("oku", "goster", "kontrol")),
]
_KINDS: dict[str, set[ControlKind]] = {
    "ensure_value": {ControlKind.TEXTBOX},
    "ensure_choice": {ControlKind.SELECT, ControlKind.COMBOBOX},
    "activate_tab": {ControlKind.TAB},
    "find_record": {ControlKind.TABLE},
    "invoke_approved_action": {ControlKind.BUTTON},
    "read": set(ControlKind),
}
_STOP = {
    "alan",
    "alani",
    "alanina",
    "alanini",
    "degeri",
    "degerini",
    "olarak",
    "ile",
    "ve",
    "bir",
    "icin",
    "no",
}


def _tokens(text: str) -> set[str]:
    words = normalize_name(text).replace("'", " ").replace(".", " ").replace(",", " ").split()
    return {w for w in words if len(w) >= 2}


def propose_op(intent: str) -> str | None:
    words = _tokens(intent)
    for op, verbs in _VERBS:
        if any(w in verbs or any(w.startswith(v) and len(v) >= 4 for v in verbs) for w in words):
            return op
    return None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    control: ObservedControl
    score: int
    matched: tuple[str, ...]


def rank_candidates(
    intent: str, controls: list[ObservedControl] | tuple[ObservedControl, ...], op: str | None
) -> list[RankedCandidate]:
    words = _tokens(intent)
    allowed = _KINDS.get(op or "read", set(ControlKind))
    ranked: list[RankedCandidate] = []
    for control in controls:
        if control.kind not in allowed:
            continue
        name_tokens = _tokens(control.label or control.accessible_name or "")
        context_tokens = (
            set().union(
                *(_tokens(c.name or "") for c in control.contexts),
                *(_tokens(t) for t in control.frame_titles),
            )
            if (control.contexts or control.frame_titles)
            else set()
        )
        hit_name = {t for t in name_tokens if any(w.startswith(t) or t.startswith(w) for w in words)}
        hit_ctx = {
            t for t in context_tokens if any(w.startswith(t) or t.startswith(w) for w in words)
        } - _STOP
        score = 2 * len(hit_name) + len(hit_ctx)
        if hit_name:
            ranked.append(RankedCandidate(control, score, tuple(sorted(hit_name | hit_ctx))))
    return sorted(ranked, key=lambda r: -r.score)


def spec_from_control(control: ObservedControl) -> TargetSpec:
    region = next((c.name for c in control.contexts if c.kind != "table_row" and c.name), None)
    return TargetSpec(
        kind=control.kind,
        labels=[control.label or control.accessible_name or ""],
        region=region,
        frame_title=control.frame_titles[-1] if control.frame_titles else None,
    )


_TEMPLATES = {
    "ensure_value": "'{m}' alanına {v} değerini yaz",
    "ensure_choice": "'{m}' listesinde {v} seçeneğini seç",
    "activate_tab": "'{m}' sekmesini etkinleştir",
    "find_record": "'{m}' tablosunda {v} anahtarlı kaydı bul",
    "read": "'{m}' değerini oku",
    "invoke_approved_action": "Onaylı aksiyonu çalıştır: {m}",
}


def standard_text(op: str, meaning: str, value: str | None = None) -> str:
    return _TEMPLATES[op].format(m=meaning, v=value or "")
