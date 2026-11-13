"""HTTP katmanında korelasyon, tek hata kaydı, sorgu gizliliği ve çalışma geçmişi erişimi."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentask.application.errors import PlanInvalid
from agentask.application.observability import log_event
from agentask.config import load_settings
from agentask.domain.runtime import Run, RunStatus, StepState
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory

LOCAL = ("127.0.0.1", 50000)
OWNER = "dev.user"
Logs = Callable[[], list[dict[str, Any]]]
logger = logging.getLogger("agentask.test.http")


@pytest.fixture
def app(make_env_file: EnvFileFactory, tmp_path: Path) -> FastAPI:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", RUN_DIRECTORY=str(tmp_path / "runs")))
    application = create_app(settings)

    @application.get("/__probe/{n}")
    async def probe(n: int) -> dict[str, int]:
        await asyncio.sleep(0.005 * (10 - n % 10))
        log_event(logger, "probe", resource_id=str(n))
        return {"n": n}

    @application.get("/__boom")
    async def boom() -> None:
        raise RuntimeError("token=abc123secret müşteri 00456")

    @application.get("/__rejected")
    async def rejected() -> None:
        raise PlanInvalid(details={"reason": "schema"})

    return application


def by_event(lines: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [x for x in lines if x["event"] == event]


def seed(app: FastAPI, owner: str, **fields: Any) -> Run:
    run = Run.new(
        owner_id=owner,
        session_id="s",
        request_id=f"r-{owner}",
        payload_hash="h",
        commands=[{"op": "read", "target": {"kind": "textbox", "labels": ["A"]}}],
    )
    run.status = RunStatus.FAILED
    run.steps[0].state = StepState.KNOWN_FAILED
    run.steps[0].error_class = "TARGET_NOT_FOUND"
    for key, value in fields.items():
        setattr(run, key, value)
    app.state.container.runs._repo.save(run)
    return run


def test_response_and_log_share_correlation_and_actor(app: FastAPI, json_logs: Logs) -> None:
    with TestClient(app, client=LOCAL) as client:
        response = client.post("/api/runs", json={}, headers={"X-Correlation-Id": "abcd1234-log"})
    assert response.headers["X-Correlation-Id"] == "abcd1234-log"
    line = by_event(json_logs(), "http_request")[-1]
    assert line["correlation_id"] == "abcd1234-log" and line["actor"] == OWNER
    assert line["status_code"] == 422 and line["error_code"] == "invalid_request"
    assert line["error_kind"] == "business" and line["level"] == "INFO" and "duration_ms" in line


async def test_concurrent_requests_keep_separate_context(app: FastAPI, json_logs: Logs) -> None:
    transport = httpx.ASGITransport(app=app, client=LOCAL)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        await asyncio.gather(
            *(
                client.get(f"/__probe/{n}", headers={"X-Correlation-Id": f"corr-req-{n:04d}"})
                for n in range(30)
            )
        )
    probes = by_event(json_logs(), "probe")
    assert len(probes) == 30
    for line in probes:
        assert line["correlation_id"] == f"corr-req-{int(line['resource_id']):04d}"


def test_business_error_logged_once_and_not_as_error(app: FastAPI, json_logs: Logs) -> None:
    with TestClient(app, client=LOCAL) as client:
        assert client.get("/__rejected").status_code == 422
    lines = [x for x in json_logs() if x.get("error_code") == PlanInvalid.code]
    assert len(lines) == 1 and lines[0]["error_kind"] == "business" and lines[0]["level"] == "INFO"
    assert not [x for x in json_logs() if x["level"] == "ERROR"]


def test_software_error_logged_once_without_message(app: FastAPI, json_logs: Logs) -> None:
    with TestClient(app, client=LOCAL) as client:
        response = client.get("/__boom", headers={"X-Correlation-Id": "abcd1234-boom"})
    body = response.json()
    assert response.status_code == 500 and body["code"] == "internal_error"
    assert body["correlation_id"] == "abcd1234-boom" == response.headers["X-Correlation-Id"]
    assert "abc123secret" not in response.text
    errors = [x for x in json_logs() if x["level"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["error_kind"] == "software" and errors[0]["exc_type"] == "RuntimeError"
    assert any("boom" in frame for frame in errors[0]["stack"])
    text = json.dumps(json_logs(), ensure_ascii=False)
    assert "abc123secret" not in text and "00456" not in text


def test_query_string_is_not_logged(app: FastAPI, json_logs: Logs) -> None:
    with TestClient(app, client=LOCAL) as client:
        client.delete("/api/runs?token=abc123secret&musteri=00456")
    text = json.dumps(json_logs(), ensure_ascii=False)
    assert "abc123secret" not in text and "00456" not in text
    assert by_event(json_logs(), "http_request")[-1]["path"] == "/api/runs"


def test_successful_reads_are_debug_only(app: FastAPI, json_logs: Logs) -> None:
    with TestClient(app, client=LOCAL) as client:
        client.get("/health/live")
    assert by_event(json_logs(), "http_request")[-1]["level"] == "DEBUG"


def test_history_is_owner_only(app: FastAPI) -> None:
    mine = seed(app, OWNER, title="Benim işlemim", correlation_id="corr-mine")
    other = seed(app, "baskasi", title="Başkasının işlemi")
    with TestClient(app, client=LOCAL) as client:
        listed = client.get("/api/runs").json()
        assert [r["run_id"] for r in listed] == [mine.run_id]
        assert client.get(f"/api/runs/{other.run_id}").status_code == 404
        assert client.post(f"/api/runs/{other.run_id}/cancel").status_code == 404
        summary = client.get(f"/api/runs/{mine.run_id}").json()["summary"]
    assert summary["title"] == "Benim işlemim" and summary["correlation_id"] == "corr-mine"
    assert summary["reason"] and summary["next_step"] and "1. adım" in summary["failed_stage"]


def test_history_survives_restart_and_old_records_load(
    make_env_file: EnvFileFactory, tmp_path: Path, json_logs: Logs
) -> None:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", RUN_DIRECTORY=str(tmp_path / "runs")))
    first = create_app(settings)
    run = seed(first, OWNER, title="Yarım kalan", correlation_id="corr-restart")
    run.status = RunStatus.RUNNING
    run.steps[0].state = StepState.DISPATCHED
    run.steps[0].error_class = None
    first.state.container.runs._repo.save(run)
    # Eski kayıt: title ve correlation_id alanları hiç yok.
    old = seed(first, OWNER)
    path = tmp_path / "runs" / f"{old.run_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["title"], raw["correlation_id"]
    path.write_text(json.dumps(raw), encoding="utf-8")

    with TestClient(create_app(settings), client=LOCAL) as client:
        runs = {r["run_id"]: r for r in client.get("/api/runs").json()}
    assert runs[run.run_id]["status"] == "outcome_unknown"
    assert runs[run.run_id]["summary"]["correlation_id"] == "corr-restart"
    assert runs[old.run_id]["summary"]["correlation_id"] is None
    recovered = by_event(json_logs(), "run_recovered")
    assert len(recovered) == 1 and recovered[0]["outcome"] == "unknown"
    assert recovered[0]["correlation_id"] == "corr-restart" and recovered[0]["category"] == "audit"
