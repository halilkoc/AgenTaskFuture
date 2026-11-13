"""Çalışma olayları (Chromium + lab): korelasyon, tek sonuç kaydı, erken başarı ve değer sızıntısı yok."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from agentask.application.observability import log_context
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env, build
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
Logs = Callable[[], list[dict[str, Any]]]
TARGET = {"kind": "select", "labels": ["Öncelik"], "region": "Kayıt Etkili"}
CHOOSE = {"op": "ensure_choice", "target": TARGET, "choice": "Yüksek", "effect": "unknown"}
STATUS_OK = {
    "op": "assert_condition",
    "condition": {
        "type": "text_present",
        "evidence": {"kind": "status_text"},
        "match": {"mode": "contains", "text": "Öncelik güncellendi"},
        "anchor": TARGET,
    },
}


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        READINESS_TIMEOUT_MS="2000",
        OUTCOME_TIMEOUT_MS="2000",
        RECONCILE_TIMEOUT_MS="1500",
        ACTION_TIMEOUT_MS="3000",
    )
    factory = PlaywrightContextFactory(settings)
    service, sessions = build(settings, factory, tmp_path / "runs")
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


def events(lines: list[dict[str, Any]], name: str, run_id: str) -> list[dict[str, Any]]:
    return [x for x in lines if x["event"] == name and x.get("run_id") == run_id]


async def test_request_correlation_reaches_run_events(env: Env, json_logs: Logs) -> None:
    await env.goto("/pages/selections")
    with log_context(correlation_id="corr-run-0001"):
        run = await env.run([CHOOSE, STATUS_OK])
    assert run.status is RunStatus.COMPLETED and run.correlation_id == "corr-run-0001"
    lines = json_logs()
    started, finished = events(lines, "run_started", run.run_id), events(lines, "run_finished", run.run_id)
    assert len(started) == len(finished) == 1
    assert started[0]["correlation_id"] == finished[0]["correlation_id"] == "corr-run-0001"
    assert started[0]["actor"] == OWNER and started[0]["category"] == "audit"
    assert finished[0]["outcome"] == "success" and "duration_ms" in finished[0]
    steps = events(lines, "step_done", run.run_id)
    assert [s["step_id"] for s in steps] == [0, 1]
    assert all(s["correlation_id"] == "corr-run-0001" and "duration_ms" in s for s in steps)
    assert lines.index(finished[0]) > max(lines.index(s) for s in steps)
    assert "Yüksek" not in json.dumps(lines, ensure_ascii=False)  # seçilen değer loglanmaz


async def test_failure_is_logged_once_and_no_success_event(env: Env, json_logs: Logs) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_outcome": "reject"})
    await env.goto("/pages/selections")
    run = await env.run([CHOOSE, STATUS_OK])
    assert run.status is RunStatus.FAILED
    lines = json_logs()
    coded = [x for x in lines if x.get("run_id") == run.run_id and x.get("error_code")]
    assert len(coded) == 1 and coded[0]["event"] == "run_finished"
    assert coded[0]["outcome"] == "failed" and coded[0]["error_code"] == "VERIFICATION_FAILED"
    assert (
        coded[0]["error_kind"] == "business" and coded[0]["step_id"] == 1 and coded[0]["level"] == "WARNING"
    )
    assert not [x for x in events(lines, "run_finished", run.run_id) if x["outcome"] == "success"]


async def test_unknown_outcome_event(env: Env, json_logs: Logs) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_outcome": "revert"})
    await env.goto("/pages/selections")
    run = await env.run([CHOOSE])
    assert run.status is RunStatus.OUTCOME_UNKNOWN
    finished = events(json_logs(), "run_finished", run.run_id)
    assert len(finished) == 1 and finished[0]["outcome"] == "unknown"
    assert finished[0]["error_code"] == "WRITE_RESULT_UNKNOWN"
    assert not events(json_logs(), "step_done", run.run_id)  # doğrulanmayan adım başarı yazmaz


async def test_stop_and_intervention_events(env: Env, json_logs: Logs) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_modal": True})
    await env.goto("/pages/selections")
    target = {"kind": "select", "labels": ["Para Birimi"], "region": "Ödeme"}
    run = await env.run([{"op": "ensure_choice", "target": target, "choice": "Dolar"}])
    assert run.status is RunStatus.PAUSED_BLOCKED
    assert events(json_logs(), "run_finished", run.run_id)[0]["outcome"] == "paused"
    await env.service.cancel(OWNER, run.run_id)
    finished = events(json_logs(), "run_finished", run.run_id)
    assert finished[-1]["outcome"] == "cancelled" and finished[-1]["actor"] == OWNER
    assert env.service.get(OWNER, run.run_id).cancelled_by == "user"


async def test_software_crash_logged_once_as_software(
    env: Env, json_logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    await env.goto("/pages/selections")

    async def explode(*_: Any) -> None:
        raise RuntimeError("password=hunter2")

    monkeypatch.setattr(env.service._executor, "execute", explode)
    run = await env.run([CHOOSE])
    assert run.status is RunStatus.FAILED
    finished = events(json_logs(), "run_finished", run.run_id)
    assert len(finished) == 1 and finished[0]["level"] == "ERROR"
    assert finished[0]["error_kind"] == "software" and finished[0]["exc_type"] == "RuntimeError"
    assert "hunter2" not in json.dumps(json_logs())
