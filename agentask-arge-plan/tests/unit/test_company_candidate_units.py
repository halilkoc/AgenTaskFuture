"""Şirket testi adayı küçük sözleşmeleri: iptal kaynağı, aksiyon dosyası, ön kontrol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentask.bootstrap import build_container
from agentask.config import ConfigurationError, load_settings
from agentask.diagnostics import FAIL, OK, _python, run_doctor
from agentask.domain.run_summary import summarize
from agentask.domain.runtime import Run, RunStatus
from agentask.infrastructure.approved_actions.file import load_action_set
from tests.conftest import EnvFileFactory

ACTION = {
    "action_id": "kurum.kaydet",
    "title": "Kaydet",
    "application_id": "lab",
    "target": {"kind": "button", "labels": ["Kaydet"]},
    "effect": "non_mutating",
    "retry_safe": False,
    "outcome": {
        "evidence": {"kind": "status_text"},
        "success": {"mode": "contains", "text": "Kaydedildi"},
    },
}


def cancelled(by: str | None, reason: str = "cancel_requested") -> Run:
    run = Run.new(owner_id="a", session_id="s", request_id="r", payload_hash="h", commands=[])
    run.status, run.status_reason, run.cancelled_by = RunStatus.CANCELLED, reason, by
    return run


def test_cancel_source_is_not_confused() -> None:
    assert "kullanıcı" in (summarize(cancelled("user")).reason or "")
    assert "sistem" in (summarize(cancelled("system_timeout")).reason or "")
    old = summarize(cancelled(None)).reason or ""
    assert "kullanıcı tarafından" not in old and "tutulmamış" in old


def test_action_file_loads_and_rejects_bad_content(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"actions": {"kurum.kaydet": ACTION}}), encoding="utf-8")
    assert load_action_set(path).actions["kurum.kaydet"].title == "Kaydet"
    path.write_text(json.dumps({"actions": {"baska.ad": ACTION}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="action_id"):
        load_action_set(path)
    path.write_text(json.dumps({"actions": {"kurum.kaydet": {**ACTION, "selector": "#x"}}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="geçersiz"):
        load_action_set(path)
    with pytest.raises(ConfigurationError, match="okunamadı"):
        load_action_set(tmp_path / "yok.json")


def test_action_file_is_used_by_container(make_env_file: EnvFileFactory, tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"actions": {"kurum.kaydet": ACTION}}), encoding="utf-8")
    settings = load_settings(
        make_env_file(CATALOG_BACKEND="disabled", APPROVED_ACTION_SET="file", APPROVED_ACTIONS_FILE=str(path))
    )
    assert set(build_container(settings).runs.actions.actions) == {"kurum.kaydet"}
    with pytest.raises(ConfigurationError, match="APPROVED_ACTIONS_FILE"):
        load_settings(make_env_file(APPROVED_ACTION_SET="file"))


def test_doctor_reports_without_secrets(
    make_env_file: EnvFileFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = load_settings(
        make_env_file(
            CATALOG_BACKEND="disabled",
            BROWSER_ENGINE="chromium",
            BROWSER_EXECUTABLE_PATH=str(tmp_path / "yok.exe"),
            RUN_DIRECTORY=str(tmp_path / "r"),
            DRAFT_DIRECTORY=str(tmp_path / "d"),
            ARTIFACT_DIRECTORY=str(tmp_path / "a"),
            MONGO_URI="mongodb://kullanici:cok-gizli@127.0.0.1:1/x",
        )
    )
    lines: list[str] = []
    code = run_doctor(settings, lines.append)
    text = "\n".join(lines)
    assert code == 1 and f"[{FAIL}] Tarayıcı" in text and "cok-gizli" not in text
    assert f"[{OK}] Taslak dizini" in text and "SONUÇ: BAŞARISIZ" in text
    assert _python().status == OK
