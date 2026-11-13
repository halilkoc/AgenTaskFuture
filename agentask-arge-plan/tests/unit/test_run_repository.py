"""Yerel dosya checkpoint deposu ve süreç yeniden başlatma kurtarması."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.services.runs import recover_interrupted
from agentask.domain.runtime import Run, RunStatus, StepState
from agentask.infrastructure.runs.local_file import LocalFileRunRepository

CMD = {"op": "read", "target": {"kind": "textbox", "labels": ["A"]}}


def new_run(owner: str = "ayse", request_id: str = "r1") -> Run:
    return Run.new(
        owner_id=owner, session_id="s1", request_id=request_id, payload_hash="h", commands=[CMD, CMD]
    )


def test_save_and_reload_from_new_instance(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    repo.save(run)
    assert run.revision == 1
    again = LocalFileRunRepository(tmp_path).get(run.run_id)
    assert again == run
    assert [r.run_id for r in LocalFileRunRepository(tmp_path).list_for("ayse")] == [run.run_id]
    assert LocalFileRunRepository(tmp_path).list_for("mehmet") == []


def test_find_by_request_is_owner_scoped(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    repo.save(run)
    assert repo.find_by_request("ayse", "r1") == run
    assert repo.find_by_request("mehmet", "r1") is None


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    for _ in range(3):
        repo.save(run)
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{run.run_id}.json"]


def test_corrupt_file_is_skipped_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "run-bad.json").write_text("{not json", encoding="utf-8")
    repo = LocalFileRunRepository(tmp_path)
    assert repo.list_all() == []
    assert "run_checkpoint_unreadable" in caplog.text


def test_run_id_cannot_escape_directory(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    assert repo.get("../../etc/passwd") is None


def test_recovery_marks_dispatched_step_outcome_unknown(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    run.set_status(RunStatus.RUNNING)
    run.steps[0].to(StepState.PREPARED)
    run.steps[0].to(StepState.DISPATCHED)
    repo.save(run)
    recovered = recover_interrupted(LocalFileRunRepository(tmp_path))
    loaded = LocalFileRunRepository(tmp_path).get(run.run_id)
    assert [r.run_id for r in recovered] == [run.run_id]
    assert loaded is not None
    assert loaded.status is RunStatus.OUTCOME_UNKNOWN and loaded.status_reason == "process_restart"
    assert loaded.steps[0].state is StepState.OUTCOME_UNKNOWN
    assert loaded.steps[0].error_class == "WRITE_RESULT_UNKNOWN"
    assert loaded.steps[1].state is StepState.PENDING


def test_recovery_pauses_run_without_dispatch(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    run.set_status(RunStatus.RUNNING)
    run.steps[0].to(StepState.PREPARED)
    repo.save(run)
    recover_interrupted(repo)
    loaded = repo.get(run.run_id)
    assert loaded is not None
    assert loaded.status is RunStatus.PAUSED_SESSION and loaded.status_reason == "process_restart"
    assert loaded.steps[0].state is StepState.PENDING


def test_recovery_completes_cancel_request_without_dispatch(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    run = new_run()
    run.set_status(RunStatus.RUNNING)
    run.set_status(RunStatus.CANCEL_REQUESTED)
    repo.save(run)
    recover_interrupted(repo)
    loaded = repo.get(run.run_id)
    assert loaded is not None and loaded.status is RunStatus.CANCELLED
    assert {s.state for s in loaded.steps} == {StepState.SKIPPED}


def test_recovery_leaves_terminal_and_paused_runs(tmp_path: Path) -> None:
    repo = LocalFileRunRepository(tmp_path)
    done, paused = new_run(request_id="a"), new_run(request_id="b")
    done.set_status(RunStatus.RUNNING)
    done.set_status(RunStatus.COMPLETED)
    paused.set_status(RunStatus.RUNNING)
    paused.set_status(RunStatus.PAUSED_BLOCKED, "UNKNOWN_DIALOG")
    repo.save(done)
    repo.save(paused)
    assert recover_interrupted(repo) == []
