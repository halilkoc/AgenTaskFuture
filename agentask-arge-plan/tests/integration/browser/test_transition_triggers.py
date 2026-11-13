"""Bağlantı ve seçim tetikleyicileri: belirsizlik, yanlış ekran, zaten seçili, tek gönderim."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.domain.runtime import RunStatus
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env, build
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
TYPE = {"kind": "select", "labels": ["İşlem Türü"], "region": "Başlangıç"}
TARGET_FIELD = {"kind": "textbox", "labels": ["Hedef Alan"], "region": "Hedef"}
TARGET_SCREEN = {
    "screen_id": "hedef",
    "title": "Hedef",
    "regions": [],
    "markers": [{"kind": "textbox", "labels": ["Hedef Notu"]}],
}
START_SCREEN = {
    "screen_id": "basla",
    "title": "Başla",
    "regions": [],
    "markers": [{"kind": "textbox", "labels": ["Referans"]}],
}


def spec() -> dict[str, Any]:
    return {"transition_id": "git", "to_screen": TARGET_SCREEN, "timeout_ms": 1500}


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    lab.reset()
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="1500", ACTION_TIMEOUT_MS="3000")
    service, sessions = build(settings, PlaywrightContextFactory(settings), tmp_path / "runs")
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


async def test_link_trigger_reaches_target(env: Env) -> None:
    await env.goto("/pages/transitions")
    trigger = {"kind": "link", "labels": ["Detaya git"]}
    run = await env.run(
        [
            {"op": "assert_screen", "screen": START_SCREEN},
            {"op": "follow_transition", "trigger": trigger, **spec()},
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()


async def test_duplicate_link_is_not_clicked(env: Env) -> None:
    await env.goto("/pages/transitions")
    trigger = {"kind": "link", "labels": ["Aynı Bağlantı"]}
    run = await env.run([{"op": "follow_transition", "trigger": trigger, **spec()}])
    assert run.status is RunStatus.PAUSED_AMBIGUOUS
    assert "/pages/transitions" in env.page.url


async def choice(env: Env) -> Any:
    return await env.run(
        [
            {"op": "assert_screen", "screen": START_SCREEN},
            {
                "op": "ensure_choice",
                "target": TYPE,
                "choice": "Hedefe Git",
                "effect": "unknown",
                "transition": spec(),
            },
        ]
    )


async def test_choice_trigger_reaches_target_once(env: Env) -> None:
    await env.goto("/pages/transitions")
    run = await choice(env)
    assert run.status is RunStatus.COMPLETED and run.steps[1].result["transition_completed"], run.model_dump()


async def test_choice_that_does_not_navigate_times_out_without_reselecting(env: Env) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_outcome": "reject"})  # hedef aynı sayfa
    await env.goto("/pages/transitions")
    run = await choice(env)
    assert run.status is RunStatus.FAILED and run.steps[1].error_class in {
        "TRANSITION_TIMEOUT",
        "UNEXPECTED_SCREEN",
    }


async def test_already_selected_does_not_claim_transition(env: Env) -> None:
    await env.goto("/pages/transitions")
    await env.page.evaluate("""() => { const s = document.querySelector('select.xnavselect');
        s.value = "git"; }""")
    run = await choice(env)
    assert run.status is RunStatus.FAILED and "tetiklenmedi" in (run.steps[1].message or "")
