"""Çalışma geçmişi özeti: anlaşılır neden, sonraki adım, başarıda hata yok, değer sızıntısı yok."""

from __future__ import annotations

from typing import Any

import pytest

from agentask.domain.actions import ErrorClass
from agentask.domain.run_summary import ERROR_TEXT, failed_step, outcome_of, summarize
from agentask.domain.runtime import Run, RunStatus, StepState

SECRET_VALUE = "00456-GIZLI"
TARGET = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}


def run(status: RunStatus, *steps: dict[str, Any], **fields: Any) -> Run:
    item = Run.new(
        owner_id="ayse",
        session_id="s",
        request_id="r",
        payload_hash="h",
        commands=[{"op": "ensure_value", "target": TARGET, "value": SECRET_VALUE} for _ in steps],
    )
    for record, change in zip(item.steps, steps, strict=True):
        for key, value in change.items():
            setattr(record, key, value)
    item.status = status
    for key, value in fields.items():
        setattr(item, key, value)
    return item


def test_every_error_class_has_plain_reason_and_next_step() -> None:
    assert {e.value for e in ErrorClass} <= set(ERROR_TEXT)
    assert all(reason and next_step for reason, next_step in ERROR_TEXT.values())


def test_failure_names_stage_reason_next_step_without_values() -> None:
    failed = run(
        RunStatus.FAILED,
        {"state": StepState.SUCCEEDED},
        {"state": StepState.KNOWN_FAILED, "error_class": "TARGET_NOT_FOUND", "message": "x"},
        title="Kefil numarası gir",
        correlation_id="corr-1",
    )
    summary = summarize(failed)
    assert summary.title == "Kefil numarası gir" and summary.correlation_id == "corr-1"
    assert summary.failed_stage == "2. adım · Alana değer yazma · “Kefil › Müşteri No”"
    assert summary.reason == ERROR_TEXT["TARGET_NOT_FOUND"][0]
    assert summary.next_step == ERROR_TEXT["TARGET_NOT_FOUND"][1]
    assert SECRET_VALUE not in str(summary)


def test_success_carries_no_old_error_text() -> None:
    done = run(RunStatus.COMPLETED, {"state": StepState.SUCCEEDED, "message": "eski hata"})
    summary = summarize(done)
    assert summary.reason is None and summary.next_step is None and summary.failed_stage is None


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (RunStatus.COMPLETED, "success"),
        (RunStatus.FAILED, "failed"),
        (RunStatus.OUTCOME_UNKNOWN, "unknown"),
        (RunStatus.CANCELLED, "cancelled"),
        (RunStatus.PAUSED_BLOCKED, "paused"),
        (RunStatus.RUNNING, "in_progress"),
    ],
)
def test_outcome_mapping_never_reports_success_early(status: RunStatus, outcome: str) -> None:
    assert outcome_of(status) == outcome


def test_restart_and_old_records_have_understandable_text() -> None:
    old = run(RunStatus.PAUSED_SESSION, {"state": StepState.PENDING}, status_reason="process_restart")
    summary = summarize(old)
    assert "yeniden başladı" in (summary.reason or "") and summary.correlation_id is None
    assert summary.title == "Elle başlatılan deneme"
    assert failed_step(old) is None


def test_unknown_outcome_warns_against_repeating() -> None:
    unknown = run(
        RunStatus.OUTCOME_UNKNOWN,
        {"state": StepState.OUTCOME_UNKNOWN, "error_class": "WRITE_RESULT_UNKNOWN"},
    )
    assert "tekrarlamayın" in (summarize(unknown).next_step or "")
