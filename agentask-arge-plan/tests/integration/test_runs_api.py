from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

LOCAL = ("127.0.0.1", 50000)
AYSE = {"X-Dev-User": "ayse", "X-Dev-Roles": "designer"}
MEHMET = {"X-Dev-User": "mehmet", "X-Dev-Roles": "designer"}


@pytest.fixture(autouse=True)
def _reset(lab: LabServer) -> None:
    lab.reset()


def wait_terminal(c: TestClient, run_id: str, headers: dict[str, str]) -> dict:  # type: ignore[type-arg]
    for _ in range(200):
        run = c.get(f"/api/runs/{run_id}", headers=headers).json()
        if run["status"] not in {"created", "running", "cancel_requested"}:
            return run
        time.sleep(0.1)
    raise AssertionError("run bitmedi")


@pytest.mark.browser
def test_runs_api_flow(make_env_file: EnvFileFactory, lab: LabServer, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = lab_settings(make_env_file, lab, RUN_DIRECTORY=str(tmp_path / "runs"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        actions = c.get("/api/actions", headers=AYSE).json()
        assert {a["action_id"] for a in actions["actions"]} == {
            "lab.add_case_note",
            "lab.save_guarantor",
            "lab.submit_application",  # R4 çok ekranlı deney akışı
        }
        assert "ensure_value" in actions["commands"]

        sid = c.post("/api/sessions", headers=AYSE).json()["session_id"]
        c.post(
            f"/api/sessions/{sid}/navigate",
            headers=AYSE,
            json={"url": f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/note-form"},
        )
        steps = [
            {"op": "ensure_value", "target": {"kind": "textbox", "labels": ["Not"]}, "value": "API notu"},
            {
                "op": "invoke_approved_action",
                "action_id": "lab.add_case_note",
                "params": {"text": "API notu"},
            },
        ]
        created = c.post(
            "/api/runs", headers=AYSE, json={"session_id": sid, "request_id": "api-1", "steps": steps}
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run_id"]
        busy = c.post(f"/api/sessions/{sid}/observe", headers=AYSE)
        assert busy.status_code in {200, 409}
        assert c.get(f"/api/runs/{run_id}", headers=MEHMET).status_code == 404
        assert c.post(f"/api/runs/{run_id}/cancel", headers=MEHMET).status_code == 404
        done = wait_terminal(c, run_id, AYSE)
        assert done["status"] == "completed" and done["outcome_label"] == "Başarılı"
        assert [s["state"] for s in done["steps"]] == ["succeeded", "succeeded"]
        assert [x["text"] for x in lab.control("GET", "/__lab/state").json()["commits"]] == ["API notu"]

        again = c.post(
            "/api/runs", headers=AYSE, json={"session_id": sid, "request_id": "api-1", "steps": steps}
        )
        assert again.status_code == 202 and again.json()["run_id"] == run_id
        conflict = c.post(
            "/api/runs", headers=AYSE, json={"session_id": sid, "request_id": "api-1", "steps": steps[:1]}
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"

        bad = c.post(
            "/api/runs",
            headers=AYSE,
            json={
                "session_id": sid,
                "request_id": "api-2",
                "steps": [{"op": "invoke_approved_action", "action_id": "lab.drop_tables", "params": {}}],
            },
        )
        assert bad.status_code == 422 and bad.json()["details"]["reason"] == "unknown_action"
        selector = c.post(
            "/api/runs",
            headers=AYSE,
            json={"session_id": sid, "request_id": "api-3", "steps": [{"op": "read", "selector": "#x"}]},
        )
        assert selector.status_code == 422

        c.post(
            f"/api/sessions/{sid}/navigate",
            headers=AYSE,
            json={"url": f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/duplicates"},
        )
        amb = c.post(
            "/api/runs",
            headers=AYSE,
            json={
                "session_id": sid,
                "request_id": "api-4",
                "steps": [
                    {
                        "op": "ensure_value",
                        "target": {"kind": "textbox", "labels": ["Müşteri No"]},
                        "value": "1",
                    }
                ],
            },
        )
        amb_run = wait_terminal(c, amb.json()["run_id"], AYSE)
        assert amb_run["status"] == "paused_ambiguous" and amb_run["outcome_label"] == "Duraklatıldı"
        cancelled = c.post(f"/api/runs/{amb_run['run_id']}/cancel", headers=AYSE).json()
        assert cancelled["status"] == "cancelled"
        assert (
            c.post(
                f"/api/runs/{amb_run['run_id']}/resume", headers=AYSE, json={"session_id": sid}
            ).status_code
            == 409
        )
        listed = c.get("/api/runs", headers=AYSE).json()
        assert {r["run_id"] for r in listed} >= {run_id, amb_run["run_id"]}
        assert c.get("/api/runs", headers=MEHMET).json() == []


def test_runs_require_capability(make_env_file: EnvFileFactory, lab: LabServer, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = lab_settings(make_env_file, lab, RUN_DIRECTORY=str(tmp_path / "runs"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        r = c.post(
            "/api/runs",
            headers={"X-Dev-User": "p", "X-Dev-Roles": "publisher"},
            json={"session_id": "x", "request_id": "r", "steps": []},
        )
    assert r.status_code == 403


def test_startup_recovers_interrupted_runs(make_env_file: EnvFileFactory, lab: LabServer, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from agentask.domain.runtime import Run, RunStatus, StepState
    from agentask.infrastructure.runs.local_file import LocalFileRunRepository

    repo = LocalFileRunRepository(tmp_path / "runs")
    run = Run.new(
        owner_id="ayse",
        session_id="old",
        request_id="r",
        payload_hash="h",
        commands=[{"op": "read", "target": {"kind": "textbox", "labels": ["A"]}}],
    )
    run.set_status(RunStatus.RUNNING)
    run.steps[0].to(StepState.PREPARED)
    run.steps[0].to(StepState.DISPATCHED)
    repo.save(run)
    settings = lab_settings(make_env_file, lab, RUN_DIRECTORY=str(tmp_path / "runs"))
    with TestClient(create_app(settings), client=LOCAL) as c:
        got = c.get(f"/api/runs/{run.run_id}", headers=AYSE).json()
    assert got["status"] == "outcome_unknown" and got["outcome_label"] == "Belirsiz"
