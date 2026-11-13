"""Bağımlılık etkisi, eleman durum sınıflandırması, onarım taslağı ve run metrikleri (P7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentask.domain.catalog import OperationDraft, StepStatus
from agentask.domain.impact import (
    ElementStatus,
    PublishedOperation,
    classify_elements,
    impact_of,
    repair_draft,
)
from agentask.domain.metrics import run_metrics
from agentask.domain.observation import (
    ContextEntry,
    ControlKind,
    FrameObservation,
    ObservedControl,
    ScanStatus,
    Snapshot,
)
from agentask.domain.runtime import Run, RunStatus, StepState
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET


def op_def(op_id: str, elements: dict[str, dict], steps: list[dict]) -> PublishedOperation:
    return PublishedOperation(
        operation_id=op_id,
        revision=1,
        content_hash="h" * 64,
        definition={
            "application_id": "lab",
            "operation_id": op_id,
            "title": op_id,
            "description": "",
            "intent_phrases": [],
            "parameters": [
                {
                    "name": "v",
                    "title": "V",
                    "max_length": 10,
                    "required": True,
                    "source": "user_input",
                    "constant": None,
                    "secret_ref": None,
                    "prior_step": None,
                }
            ],
            "elements": {k: {"element_id": k, "meaning": k, "target": v} for k, v in elements.items()},
            "steps": steps,
        },
    )


KEFIL = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}
URUN = {"kind": "combobox", "labels": ["Ürün Tipi"]}
OPS = [
    op_def(
        "kefil_no", {"kefil": KEFIL}, [{"op": "ensure_value", "element_id": "kefil", "value_template": "{v}"}]
    ),
    op_def(
        "kefil_ve_not",
        {"kefil": KEFIL},
        [
            {"op": "ensure_value", "element_id": "kefil", "value_template": "{v}"},
            {
                "op": "invoke_approved_action",
                "action_id": "lab.add_case_note",
                "action_params": {"text": "{v}"},
            },
        ],
    ),
    op_def("kart", {"urun": URUN}, [{"op": "ensure_choice", "element_id": "urun", "choice_template": "{v}"}]),
]


def control(
    n: int, label: str, region: str | None, kind: ControlKind = ControlKind.TEXTBOX
) -> ObservedControl:
    ctx = (ContextEntry("region", region, None),) if region else ()
    return ObservedControl(
        candidate_id=f"c-s1-{n}",
        frame_ref="f1",
        kind=kind,
        role=kind.value,
        accessible_name=label,
        label=label,
        visible=True,
        enabled=True,
        sensitive=False,
        has_value=False,
        selected_text=None,
        options=(),
        contexts=ctx,
        frame_titles=(),
        tag="input",
    )


def snap(controls: list[ObservedControl], status: ScanStatus = ScanStatus.COMPLETE) -> Snapshot:
    frame = FrameObservation("f1", None, None, None, "/", 0, (("f1", 0),), status, None, True, len(controls))
    return Snapshot("s1", datetime.now(UTC), (frame,), tuple(controls))


def test_shared_dependency_impact() -> None:
    by_element = impact_of(OPS, elements={("kefil_no", "kefil")})
    assert {i.operation_id for i in by_element} == {"kefil_no", "kefil_ve_not"}  # aynı anlamsal hedef
    by_kind = impact_of(OPS, adapter_kinds={"combobox"})
    assert [i.operation_id for i in by_kind] == ["kart"]
    by_action = impact_of(OPS, action_ids={"lab.add_case_note"})
    assert [i.operation_id for i in by_action] == ["kefil_ve_not"]
    assert all(i.regression_tests == [f"fresh_session_test:{i.operation_id}"] for i in by_element)


def test_label_change_detected_with_rename_suggestion() -> None:
    result = classify_elements(
        OPS[0], snap([control(0, "Müşteri Numarası", "Kefil"), control(1, "Müşteri No", "Başvuran")])
    )
    [kefil] = result
    assert kefil.status is ElementStatus.NOT_FOUND
    assert [s["label"] for s in kefil.suggestions] == ["Müşteri Numarası"]


def test_dynamic_ids_ignored_and_unchanged() -> None:
    [kefil] = classify_elements(OPS[0], snap([control(7, "Müşteri No", "Kefil")]))
    assert kefil.status is ElementStatus.UNCHANGED


def test_incomplete_coverage_is_unknown_not_missing() -> None:
    [kefil] = classify_elements(OPS[0], snap([], ScanStatus.PARTIAL))
    assert kefil.status is ElementStatus.UNKNOWN


def test_ambiguity_reported() -> None:
    [kefil] = classify_elements(
        OPS[0], snap([control(0, "Müşteri No", "Kefil"), control(1, "Müşteri No", "Kefil")])
    )
    assert kefil.status is ElementStatus.AMBIGUOUS


def test_repair_draft_resets_only_affected_steps() -> None:
    draft = repair_draft(OPS[1], {"kefil"}, created_by="ayse", base_release_id="rel-1")
    assert isinstance(draft, OperationDraft) and draft.operation_id == "kefil_ve_not"
    assert [s.status for s in draft.steps] == [StepStatus.INTENT_ENTERED, StepStatus.TARGET_SELECTED]
    assert "rel-1" in draft.description and draft.fresh_test is None and draft.approval is None
    assert draft.validation_issues(LAB_ACTION_SET)  # yayımlanamaz; yeniden doğrulama gerekir


def make_run(
    status: RunStatus,
    recoveries: list[str],
    seconds: int,
    binding_op: str | None = None,
    error: str | None = None,
) -> Run:
    run = Run.new(
        owner_id="ayse",
        session_id="s",
        request_id=f"r{seconds}{status}",
        payload_hash="h",
        commands=[{"op": "read"}],
    )
    run.status = status
    run.steps[0].recoveries = recoveries
    run.steps[0].error_class = error
    run.steps[0].state = StepState.SUCCEEDED if status is RunStatus.COMPLETED else StepState.KNOWN_FAILED
    run.updated_at = run.created_at + timedelta(seconds=seconds)
    run.binding = {"operation_id": binding_op} if binding_op else None
    return run


def test_metrics_separate_recoveries() -> None:
    runs = [
        make_run(RunStatus.COMPLETED, ["FRAME_CHANGED"], 2, "kefil_no"),
        make_run(RunStatus.COMPLETED, [], 4, "kefil_no"),
        make_run(RunStatus.FAILED, [], 6, None, "TARGET_AMBIGUOUS"),
        make_run(RunStatus.OUTCOME_UNKNOWN, ["WRITE_RESULT_UNKNOWN"], 8),
    ]
    m = run_metrics(runs)
    assert m["total"] == 4 and m["by_status"]["completed"] == 2
    assert m["business_success_rate"] == 0.5
    assert m["completed_with_technical_recovery"] == 1
    assert m["recoveries"] == {"FRAME_CHANGED": 1, "WRITE_RESULT_UNKNOWN": 1}
    assert m["error_classes"] == {"TARGET_AMBIGUOUS": 1}
    assert m["duration_seconds"]["p50"] in {4.0, 6.0} and m["duration_seconds"]["p95"] == 8.0
    assert m["by_operation"]["kefil_no"]["completed"] == 2
