"""Saf çözümleyici: tekil/çoklu/yok ayrımı, bağlamla daraltma, kapsam kuralları (T02, T04)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agentask.domain.observation import (
    ContextEntry,
    ControlKind,
    FrameObservation,
    ObservedControl,
    ScanStatus,
    Snapshot,
)
from agentask.domain.targeting import Outcome, TargetSpec, normalize_name, resolve


def frame(
    ref: str,
    *,
    title: str | None = None,
    parent: str | None = None,
    status: ScanStatus = ScanStatus.COMPLETE,
    detail: bool = True,
) -> FrameObservation:
    return FrameObservation(
        frame_ref=ref,
        parent_ref=parent,
        title=title,
        origin="http://127.0.0.1:8100",
        path="/p",
        depth=0 if parent is None else 1,
        lineage=((ref, 0),),
        status=status,
        reason=None,
        detail_scanned=detail,
        control_count=0,
    )


def control(
    n: int,
    *,
    frame_ref: str = "f1",
    kind: ControlKind = ControlKind.TEXTBOX,
    label: str = "Müşteri No",
    contexts: tuple[ContextEntry, ...] = (),
    visible: bool = True,
    enabled: bool = True,
    frame_titles: tuple[str, ...] = (),
) -> ObservedControl:
    return ObservedControl(
        candidate_id=f"c-s1-{n}",
        frame_ref=frame_ref,
        kind=kind,
        role=kind.value,
        accessible_name=label,
        label=label,
        visible=visible,
        enabled=enabled,
        sensitive=False,
        has_value=False,
        selected_text=None,
        options=(),
        contexts=contexts,
        frame_titles=frame_titles,
    )


def snap(controls: list[ObservedControl], frames: list[FrameObservation] | None = None) -> Snapshot:
    return Snapshot(
        revision="s1",
        created_at=datetime(2026, 11, 5, tzinfo=UTC),
        frames=tuple(frames or [frame("f1")]),
        controls=tuple(controls),
    )


APPLICANT = (ContextEntry("region", "Başvuran", None),)
GUARANTOR = (ContextEntry("region", "Kefil", None),)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Müşteri No", "musteri no"),
        ("MÜŞTERİ NO:", "musteri no"),
        ("  Şube * ", "sube"),
        ("IĞDIR", "igdir"),
        ("Çalışma   Şubesi", "calisma subesi"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_label_match_is_exact_after_normalization() -> None:
    s = snap([control(0, label="Mevcut notlar"), control(1, label="Not")])
    result = resolve(TargetSpec(kind="textbox", labels=["not"]), s)
    assert result.outcome is Outcome.RESOLVED and result.candidate_id == "c-s1-1"


def test_two_same_named_controls_are_ambiguous_without_context() -> None:
    s = snap([control(0, contexts=APPLICANT), control(1, contexts=GUARANTOR)])
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), s)
    assert result.outcome is Outcome.AMBIGUOUS
    assert result.reason == "multiple_candidates"
    assert result.candidate_id is None
    assert {c.candidate_id for c in result.candidates} == {"c-s1-0", "c-s1-1"}
    assert result.snapshot_revision == "s1"


def test_region_context_disambiguates() -> None:
    s = snap([control(0, contexts=APPLICANT), control(1, contexts=GUARANTOR)])
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"], region="kefil"), s)
    assert result.outcome is Outcome.RESOLVED and result.candidate_id == "c-s1-1"
    assert result.reason == "unique_match"


def test_kind_must_match() -> None:
    s = snap([control(0, kind=ControlKind.BUTTON, label="Kaydet")])
    assert resolve(TargetSpec(kind="textbox", labels=["Kaydet"]), s).outcome is Outcome.UNRESOLVED


def test_row_key_matches_exact_text_keeping_leading_zeros() -> None:
    rows = [
        control(
            i, kind=ControlKind.BUTTON, label="Aç", contexts=(ContextEntry("table_row", "Başvurular", key),)
        )
        for i, key in enumerate(["007", "7"])
    ]
    s = snap(rows)
    result = resolve(TargetSpec(kind="button", labels=["Aç"], row_key="007"), s)
    assert result.outcome is Outcome.RESOLVED and result.candidate_id == "c-s1-0"


def test_frame_title_narrows_scope() -> None:
    frames = [frame("f1"), frame("f2", title="Müşteri Kaydı (dış sistem)", parent="f1")]
    controls = [
        control(0, frame_ref="f1"),
        control(1, frame_ref="f2", frame_titles=("Müşteri Kaydı (dış sistem)",)),
    ]
    result = resolve(
        TargetSpec(kind="textbox", labels=["Müşteri No"], frame_title="müşteri kaydı (dış sistem)"),
        snap(controls, frames),
    )
    assert result.outcome is Outcome.RESOLVED and result.candidate_id == "c-s1-1"


def test_not_found_only_when_scope_complete() -> None:
    result = resolve(TargetSpec(kind="textbox", labels=["Yok"]), snap([control(0)]))
    assert result.outcome is Outcome.UNRESOLVED and result.reason == "not_found"
    assert result.coverage.overall is ScanStatus.COMPLETE


@pytest.mark.parametrize(
    "status", [ScanStatus.PARTIAL, ScanStatus.TIMED_OUT, ScanStatus.INACCESSIBLE, ScanStatus.NOT_SCANNED]
)
def test_incomplete_scope_never_reports_not_found(status: ScanStatus) -> None:
    frames = [frame("f1"), frame("f2", parent="f1", status=status)]
    result = resolve(TargetSpec(kind="textbox", labels=["Yok"]), snap([control(0)], frames))
    assert result.outcome is Outcome.UNRESOLVED and result.reason == "coverage_incomplete"
    assert result.coverage.overall is not ScanStatus.COMPLETE
    assert [f.frame_ref for f in result.coverage.incomplete] == ["f2"]


def test_single_match_with_incomplete_scope_is_unresolved() -> None:
    frames = [frame("f1"), frame("f2", parent="f1", status=ScanStatus.PARTIAL)]
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), snap([control(0)], frames))
    assert result.outcome is Outcome.UNRESOLVED and result.reason == "coverage_incomplete"
    assert [c.candidate_id for c in result.candidates] == ["c-s1-0"]
    assert result.candidate_id is None


def test_frames_scanned_only_lightly_count_as_incomplete_scope() -> None:
    frames = [frame("f1"), frame("f2", parent="f1", detail=False)]
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), snap([control(0)], frames))
    assert result.outcome is Outcome.UNRESOLVED and result.reason == "coverage_incomplete"


def test_incomplete_frame_outside_frame_title_scope_does_not_block() -> None:
    frames = [frame("f1", status=ScanStatus.PARTIAL), frame("f2", title="Adres Bilgileri", parent="f1")]
    controls = [control(0, frame_ref="f2", label="Adres", frame_titles=("Adres Bilgileri",))]
    result = resolve(
        TargetSpec(kind="textbox", labels=["Adres"], frame_title="Adres Bilgileri"), snap(controls, frames)
    )
    assert result.outcome is Outcome.RESOLVED


def test_invisible_or_disabled_single_match_is_evidence_missing() -> None:
    hidden = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), snap([control(0, visible=False)]))
    assert hidden.outcome is Outcome.UNRESOLVED and hidden.reason == "evidence_missing"
    disabled = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), snap([control(0, enabled=False)]))
    assert disabled.reason == "evidence_missing"
    allowed = resolve(
        TargetSpec(kind="textbox", labels=["Müşteri No"], require_enabled=False),
        snap([control(0, enabled=False)]),
    )
    assert allowed.outcome is Outcome.RESOLVED


def test_ambiguous_even_if_one_candidate_hidden_is_not_first_match() -> None:
    s = snap([control(0), control(1)])
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), s)
    assert result.outcome is Outcome.AMBIGUOUS


def test_target_spec_rejects_selectors_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TargetSpec.model_validate({"kind": "textbox", "labels": ["A"], "css": "#x"})
    with pytest.raises(ValidationError):
        TargetSpec.model_validate({"kind": "video", "labels": ["A"]})
    with pytest.raises(ValidationError):
        TargetSpec.model_validate({"kind": "textbox", "labels": []})


def test_resolution_has_explanation_and_no_confidence() -> None:
    result = resolve(TargetSpec(kind="textbox", labels=["Müşteri No"]), snap([control(0)]))
    dumped = result.to_dict()
    assert "confidence" not in str(dumped).lower()
    assert result.explanation


def test_summary_cleared_frames_count_as_complete_scope() -> None:
    frames = [frame("f1"), frame("f2", parent="f1", detail=False)]
    result = resolve(
        TargetSpec(kind="textbox", labels=["Müşteri No"]),
        snap([control(0)], frames),
        summary_cleared=frozenset({"f2"}),
    )
    assert result.outcome is Outcome.RESOLVED


def test_summary_cleared_cannot_hide_incomplete_scan() -> None:
    frames = [frame("f1"), frame("f2", parent="f1", status=ScanStatus.PARTIAL, detail=False)]
    result = resolve(
        TargetSpec(kind="textbox", labels=["Müşteri No"]),
        snap([control(0)], frames),
        summary_cleared=frozenset({"f2"}),
    )
    assert result.outcome is Outcome.UNRESOLVED and result.reason == "coverage_incomplete"


@pytest.mark.parametrize("labels", [[""], ["   "], ["*:"], ["Müşteri No", ""]])
def test_blank_labels_are_rejected(labels: list[str]) -> None:
    with pytest.raises(ValidationError):
        TargetSpec.model_validate({"kind": "textbox", "labels": labels})


# ---- etkileşim bağlamı (ADR 0014) --------------------------------------------

DIALOG = (ContextEntry("dialog", "Not ekle", None),)


def _with(c: ObservedControl, interaction: str) -> ObservedControl:
    from dataclasses import replace

    return replace(c, interaction=interaction)


def test_copy_inside_closed_dialog_is_not_a_candidate() -> None:
    page = control(1)
    hidden = _with(control(2, visible=False, contexts=DIALOG), "inactive_dialog")
    r = resolve(TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"]), snap([page, hidden]))
    assert r.outcome is Outcome.RESOLVED and r.candidate_id == page.candidate_id
    assert [c.candidate_id for c in r.candidates] == [page.candidate_id]


def test_hidden_copy_outside_dialogs_still_makes_it_ambiguous() -> None:
    r = resolve(
        TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"]),
        snap([control(1), control(2, visible=False)]),
    )
    assert r.outcome is Outcome.AMBIGUOUS  # gizli kopya ihtimali gizlenmez (eski kural korunur)


def test_active_dialog_target_wins_over_same_named_field_behind_it() -> None:
    inside = control(1, contexts=DIALOG)
    behind = _with(control(2, contexts=APPLICANT), "behind_dialog")
    spec = TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"])
    r = resolve(spec, snap([inside, behind]))
    assert r.outcome is Outcome.RESOLVED and r.candidate_id == inside.candidate_id
    assert len(r.candidates) == 2  # engellenen aday görünür ama kullanılmaz


@pytest.mark.parametrize("interaction", ["behind_dialog", "overlay", "inert"])
def test_only_blocked_candidate_is_never_resolved(interaction: str) -> None:
    behind = _with(control(1, contexts=APPLICANT), interaction)
    r = resolve(
        TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"], region="Başvuran"), snap([behind])
    )
    assert r.outcome is Outcome.UNRESOLVED and r.reason == "blocked" and r.candidate_id is None
    # Ekran işareti olarak varlığı kanıtlanır (pencere politikası yürütücüdedir).
    presence = resolve(
        TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"], region="Başvuran"),
        snap([behind]),
        presence=True,
    )
    assert presence.outcome is Outcome.RESOLVED


def test_multiple_active_dialogs_stop_resolution() -> None:
    a = _with(control(1, contexts=(ContextEntry("dialog", "Birinci", None),)), "dialog_ambiguous")
    r = resolve(TargetSpec(kind=ControlKind.TEXTBOX, labels=["Müşteri No"]), snap([a]))
    assert r.outcome is Outcome.UNRESOLVED and r.reason == "multiple_active_dialogs"


def test_driver_never_bypasses_playwright_actionability() -> None:
    # Engeller force veya betikle tıklama/olay gönderme ile aşılmaz (statik koruma).
    from pathlib import Path

    import agentask.infrastructure.browser.driver as driver_module

    source = Path(driver_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("force=True", "dispatch_event(", '.click()"', "el.click()", "e.click()"):
        assert forbidden not in source, forbidden
