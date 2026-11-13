"""Çalışma anı: değişen aksiyon gönderilmez; uzlaştırmasız belirsizlik ve silinen aksiyon hata üretmez."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.runs import RunService
from agentask.domain.actions import ActionSet
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
NOTE = {"kind": "textbox", "labels": ["Not"]}
ACTION: dict[str, Any] = {
    "action_id": "kurum.not",
    "title": "Not",
    "application_id": "lab",
    "target": {"kind": "button", "labels": ["Kaydet"]},
    "effect": "non_mutating",
    "retry_safe": False,
    "params": [],
    "outcome": {"evidence": {"kind": "status_text"}, "success": {"mode": "equals", "text": "Hiç gelmeyecek"}},
}
ACTIONS = ActionSet.model_validate({"actions": {"kurum.not": ACTION}})


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        READINESS_TIMEOUT_MS="1500",
        OUTCOME_TIMEOUT_MS="800",
        RECONCILE_TIMEOUT_MS="800",
        ACTION_TIMEOUT_MS="3000",
    )
    factory = PlaywrightContextFactory(settings)
    sessions = BrowserSessionService(factory, SessionLimits(max_sessions=4, max_per_user=2, idle_seconds=600))
    repo = LocalFileRunRepository(tmp_path / "runs")
    executor = Executor(repo, ACTIONS, AdapterRegistry.default(), ExecutorConfig.from_settings(settings))
    service = RunService(repo, sessions, executor, ACTIONS, max_steps=20)
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


def invoke() -> dict[str, Any]:
    return {
        "op": "invoke_approved_action",
        "action_id": "kurum.not",
        "action_hash": ACTIONS.fingerprint("kurum.not"),
        "application_id": "lab",
    }


async def test_definition_changed_after_planning_is_not_dispatched(env: Env) -> None:
    await env.goto("/pages/note-form")
    changed = ActionSet.model_validate({"actions": {"kurum.not": {**ACTION, "retry_safe": True}}})
    env.service._executor._actions = changed
    run = await env.run([{"op": "ensure_value", "target": NOTE, "value": "n"}, invoke()])
    assert run.status is RunStatus.FAILED and run.steps[1].error_class == "POLICY_DENIED"
    assert "değişti" in (run.steps[1].message or "") and env.commits() == []


async def test_unknown_outcome_without_reconcile_is_safe_and_not_a_crash(env: Env) -> None:
    await env.goto("/pages/note-form")
    run = await env.run([{"op": "ensure_value", "target": NOTE, "value": "n"}, invoke()])
    assert run.status is RunStatus.OUTCOME_UNKNOWN and run.status_reason == "WRITE_RESULT_UNKNOWN"
    assert run.steps[1].error_class == "WRITE_RESULT_UNKNOWN" and len(env.commits()) == 1
    # Aksiyon sonradan kaldırılırsa devam yazılım hatası üretmez, yeniden göndermez.
    env.service._executor._actions = ActionSet()
    resumed = await env.service.resume(OWNER, run.run_id, env.sid)
    resumed = await env.service.wait(resumed.run_id, 10)
    assert (
        resumed.status is RunStatus.OUTCOME_UNKNOWN and resumed.status_reason == "action_definition_changed"
    )
    assert len(env.commits()) == 1


async def test_session_lost_text_pauses_before_action(env: Env) -> None:
    await env.goto("/pages/note-form")
    env.service._executor._actions = ActionSet.model_validate(
        {
            "actions": {"kurum.not": ACTION},
            "profile": {"session_lost_texts": [{"mode": "contains", "text": "Oturum kapandı"}]},
        }
    )
    await env.page.evaluate("document.querySelector('.note-status').textContent = 'Oturum kapandı'")
    run = await env.run([{"op": "ensure_value", "target": NOTE, "value": "n"}])
    assert run.status is RunStatus.PAUSED_SESSION and run.steps[0].error_class == "SESSION_EXPIRED"
