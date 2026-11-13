"""Kayıt bul ve bulunan satır: doğru satır, sıra değişimi, yinelenen ve bulunamayan kayıt (lab)."""

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
TABLE = {"kind": "table", "labels": ["Kayıtlar"]}
NOTE = {"kind": "textbox", "labels": ["Satır Notu"]}


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


def plan(key: str) -> list[dict[str, Any]]:
    return [
        {"op": "find_record", "table": TABLE, "key": key, "navigation": "none"},
        {"op": "ensure_value", "target": NOTE, "value": "yazıldı", "in_found_row": True},
    ]


async def row_note(env: Env, key: str) -> str:
    row = env.page.locator("tr", has_text=key)
    return str(await row.get_by_label("Satır Notu").input_value())


async def test_only_found_row_is_written(env: Env) -> None:
    await env.goto("/pages/records")
    run = await env.run(plan("R-1002"))
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await row_note(env, "R-1002") == "yazıldı" and await row_note(env, "R-1001") == ""


async def test_row_order_change_does_not_change_target(env: Env) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_catalog": "changed"})
    await env.goto("/pages/records")
    run = await env.run(plan("R-1008"))
    assert run.status is RunStatus.COMPLETED and await row_note(env, "R-1008") == "yazıldı"


async def test_missing_record_writes_nothing(env: Env) -> None:
    await env.goto("/pages/records")
    run = await env.run(plan("R-9999"))
    assert run.status is RunStatus.FAILED and run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert run.steps[1].state.value == "pending"


async def test_paged_search_with_custom_next_label(env: Env) -> None:
    await env.goto("/pages/records")
    run = await env.run(
        [
            {
                "op": "find_record",
                "table": TABLE,
                "key": "R-1007",
                "navigation": "paged",
                "next_labels": ["Sonraki"],
            },
            {"op": "ensure_value", "target": NOTE, "value": "sayfa", "in_found_row": True},
        ]
    )
    assert run.status is RunStatus.COMPLETED and run.steps[0].result["pages_visited"] == 3


async def test_duplicate_key_pauses(env: Env) -> None:
    env.lab.control("PUT", "/__lab/scenario", json={"selection_redraw": True})
    await env.goto("/pages/records?page=2")
    run = await env.run(plan("R-1004"))
    assert run.status is RunStatus.PAUSED_AMBIGUOUS and run.steps[1].state.value == "pending"


async def test_row_step_without_found_record_is_refused(env: Env) -> None:
    await env.goto("/pages/records")
    run = await env.run([plan("R-1002")[1]])
    assert run.status is RunStatus.FAILED and run.steps[0].error_class == "RECORD_NOT_LOADED"
    assert await row_note(env, "R-1002") == ""
