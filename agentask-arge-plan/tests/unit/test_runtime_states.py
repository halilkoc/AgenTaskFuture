"""Run ve step durum makineleri (docs/03 Run durumları)."""

from __future__ import annotations

import pytest

from agentask.domain.runtime import IllegalTransition, Run, RunStatus, StepRecord, StepState


def make_run(steps: int = 2) -> Run:
    return Run.new(
        owner_id="ayse",
        session_id="s1",
        request_id="r1",
        payload_hash="h",
        commands=[{"op": "read", "target": {"kind": "textbox", "labels": ["A"]}}] * steps,
    )


def test_new_run_is_created_with_pending_steps() -> None:
    run = make_run()
    assert run.status is RunStatus.CREATED
    assert [s.state for s in run.steps] == [StepState.PENDING, StepState.PENDING]
    assert run.run_id and run.revision == 0


@pytest.mark.parametrize(
    "path",
    [
        [StepState.PREPARED, StepState.DISPATCHED, StepState.VERIFYING, StepState.SUCCEEDED],
        [StepState.PREPARED, StepState.SUCCEEDED],  # zaten istenen durumda
        [
            StepState.PREPARED,
            StepState.DISPATCHED,
            StepState.VERIFYING,
            StepState.OUTCOME_UNKNOWN,
            StepState.SUCCEEDED,
        ],  # uzlaştırıldı
        [StepState.PREPARED, StepState.DISPATCHED, StepState.VERIFYING, StepState.KNOWN_FAILED],
        [StepState.PREPARED, StepState.DISPATCHED, StepState.VERIFYING, StepState.PREPARED],  # güvenli tekrar
        [StepState.SKIPPED],
        [StepState.KNOWN_FAILED, StepState.PENDING],  # uygulanmadığı bilinen hata sonrası devam
    ],
)
def test_legal_step_paths(path: list[StepState]) -> None:
    step = make_run().steps[0]
    for state in path:
        step.to(state)
    assert step.state is path[-1]


@pytest.mark.parametrize(
    ("path", "illegal"),
    [
        (
            [StepState.PREPARED, StepState.DISPATCHED, StepState.VERIFYING, StepState.SUCCEEDED],
            StepState.DISPATCHED,
        ),
        ([], StepState.DISPATCHED),  # hazırlanmadan gönderim yok
        (
            [StepState.PREPARED, StepState.DISPATCHED],
            StepState.PREPARED,
        ),  # gönderilmiş adım sessizce tekrar edilmez
        (
            [StepState.PREPARED, StepState.DISPATCHED, StepState.VERIFYING, StepState.OUTCOME_UNKNOWN],
            StepState.PREPARED,
        ),
        ([StepState.SKIPPED], StepState.PREPARED),
    ],
)
def test_illegal_step_transitions(path: list[StepState], illegal: StepState) -> None:
    step = make_run().steps[0]
    for state in path:
        step.to(state)
    with pytest.raises(IllegalTransition):
        step.to(illegal)


def test_run_status_transitions() -> None:
    run = make_run()
    run.set_status(RunStatus.RUNNING)
    run.set_status(RunStatus.PAUSED_SESSION, "session_expired")
    assert run.status_reason == "session_expired"
    run.set_status(RunStatus.RUNNING)
    run.set_status(RunStatus.CANCEL_REQUESTED)
    run.set_status(RunStatus.CANCELLED)
    with pytest.raises(IllegalTransition):
        run.set_status(RunStatus.RUNNING)


@pytest.mark.parametrize("terminal", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED])
def test_terminal_runs_cannot_resume(terminal: RunStatus) -> None:
    run = make_run()
    run.set_status(RunStatus.RUNNING)
    run.set_status(terminal)
    with pytest.raises(IllegalTransition):
        run.set_status(RunStatus.RUNNING)


def test_outcome_unknown_run_may_resume_for_reconciliation_only() -> None:
    run = make_run()
    run.set_status(RunStatus.RUNNING)
    run.set_status(RunStatus.OUTCOME_UNKNOWN, "write_result_unknown")
    run.set_status(RunStatus.RUNNING)
    assert run.status is RunStatus.RUNNING


def test_run_roundtrips_as_json() -> None:
    run = make_run()
    run.steps[0].to(StepState.PREPARED)
    run.steps[0].intent = {"action_id": "lab.add_case_note", "baseline": 0}
    again = Run.model_validate_json(run.model_dump_json())
    assert again == run
    assert isinstance(again.steps[0], StepRecord)


def test_cancel_after_last_step_may_complete() -> None:
    run = make_run()
    run.set_status(RunStatus.RUNNING)
    run.set_status(RunStatus.CANCEL_REQUESTED)
    run.set_status(RunStatus.COMPLETED, "cancel_arrived_after_last_step")
    assert run.status is RunStatus.COMPLETED
