"""Beklenen yeni pencere ve isteğe bağlı pencere: gerçek Chromium + deney uygulaması."""

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
MAIN = {
    "screen_id": "ana",
    "title": "Ana",
    "regions": [],
    "markers": [{"kind": "textbox", "labels": ["Ana Not"]}],
}
CHILD = {
    "screen_id": "pencere",
    "title": "Pencere",
    "regions": [],
    "markers": [{"kind": "textbox", "labels": ["Pencere Notu"]}],
}
NOTE = {"kind": "textbox", "labels": ["Pencere Notu"]}
SECOND = {"kind": "textbox", "labels": ["İkinci Not"]}
BLOCKER = {
    "blocker_id": "optional.0",
    "dialog_name": "Bilgilendirme",
    "text": {"mode": "contains", "text": "Kaydınız işleniyor"},
    "button_label": "Tamam",
}


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


def open_window(button: str, **extra: Any) -> dict[str, Any]:
    return {
        "op": "follow_transition",
        "trigger": {"kind": "button", "labels": [button]},
        "transition_id": "ac",
        "to_screen": CHILD,
        "timeout_ms": 2500,
        "window": "new",
        **extra,
    }


def write(target: dict[str, Any] = NOTE, value: str = "yazıldı") -> dict[str, Any]:
    return {"op": "ensure_value", "target": target, "value": value}


def back(close: bool = True, timeout_ms: int = 2500) -> dict[str, Any]:
    return {
        "op": "return_window",
        "transition_id": "don",
        "to_screen": MAIN,
        "timeout_ms": timeout_ms,
        "close": close,
    }


START = {"op": "assert_screen", "screen": MAIN}


def handle(env: Env) -> Any:
    return env.sessions.peek(OWNER, env.sid)


async def echo(env: Env) -> str:
    return str(await handle(env).page.locator("#echo").text_content())


async def test_expected_window_is_used_and_main_screen_reverified(env: Env) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window("Pencere Aç"), write(), back(), START])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await echo(env) == "yazıldı"
    assert not handle(env).adopted
    assert handle(env).observer.new_windows == 0


@pytest.mark.parametrize("button", ["İki Pencere", "Pencere Açmaz"])
async def test_multiple_or_missing_window_stops(env: Env, button: str) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window(button), write()])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert run.steps[1].error_class == "NEW_WINDOW"
    assert await echo(env) == ""
    assert not handle(env).adopted


async def test_wrong_origin_is_not_adopted(env: Env, lab: LabServer) -> None:
    await env.goto("/pages/windows")
    await handle(env).page.evaluate("o => { window.__otherOrigin = o; }", lab.secondary)
    run = await env.run([START, open_window("Yabancı Pencere"), write()])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert not handle(env).adopted
    assert handle(env).observer.new_windows == 1  # kapatılmadı; insan karar verir


async def test_declared_other_origin_is_accepted(env: Env, lab: LabServer) -> None:
    await env.goto("/pages/windows")
    await handle(env).page.evaluate("o => { window.__otherOrigin = o; }", lab.secondary)
    plan = [START, open_window("Yabancı Pencere", window_origin=lab.secondary)]
    run = await env.run(plan)
    # İkinci adreste oturum yoksa hedef ekran tanınmaz; önemli olan pencerenin adres nedeniyle reddedilmemesi.
    assert run.steps[1].error_class != "NEW_WINDOW", run.model_dump()


async def test_wrong_screen_in_window_writes_nothing(env: Env) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window("Yanlış Ekran"), write()])
    assert run.status is not RunStatus.COMPLETED
    assert run.steps[2].state.value == "pending"
    assert not handle(env).adopted
    assert handle(env).observer.new_windows == 1


async def test_window_closing_early_is_unknown_not_success(env: Env) -> None:
    await env.goto("/pages/windows")
    wait = {"op": "assert_condition", "condition": {"type": "value_equals", "target": NOTE, "value": "olmaz"}}
    run = await env.run([START, open_window("Kapanan Pencere"), wait, write(SECOND)])
    assert run.status is RunStatus.OUTCOME_UNKNOWN, [s.model_dump() for s in run.steps]
    assert not handle(env).adopted
    assert run.steps[3].state.value == "pending"


async def test_application_closes_window_itself(env: Env) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window("Kapanan Pencere"), back(close=False), START])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]


async def test_window_not_closing_by_itself_stops(env: Env) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window("Pencere Aç"), back(close=False, timeout_ms=600)])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert not handle(env).adopted


async def test_extra_window_while_working_stops(env: Env) -> None:
    await env.goto("/pages/windows")
    run = await env.run([START, open_window("Çoğalan Pencere"), write(), write(SECOND, "ikinci")])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert "ikinci" not in await echo(env)


async def test_unexpected_window_still_stops_without_declaration(env: Env) -> None:
    await env.goto("/pages/windows")
    await handle(env).page.get_by_role("button", name="Pencere Aç", exact=True).click()
    await handle(env).page.wait_for_timeout(200)
    run = await env.run([START, write({"kind": "textbox", "labels": ["Ana Not"]})])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()


def modal_plan() -> list[dict[str, Any]]:
    first = {"kind": "textbox", "labels": ["Birinci"]}
    second = {"kind": "textbox", "labels": ["İkinci"]}
    return [
        {"op": "register_optional_dialogs", "dialogs": [BLOCKER]},
        write(first, "bir"),
        {"op": "assert_condition", "condition": {"type": "value_equals", "target": first, "value": "bir"}},
        write(second, "iki"),
    ]


async def modal_counts(env: Env) -> tuple[str, str, str]:
    page = handle(env).page
    counter = page.locator("#clicks")
    return (
        await counter.get_attribute("data-ok"),
        await counter.get_attribute("data-cancel"),
        await page.get_by_label("İkinci").input_value(),
    )


async def test_optional_dialog_appears_and_defined_button_is_used(env: Env) -> None:
    await env.goto("/pages/optional-modal?mode=info")
    run = await env.run(modal_plan())
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await modal_counts(env) == ("1", "0", "iki")


async def test_optional_dialog_absent_causes_no_wait_or_failure(env: Env) -> None:
    await env.goto("/pages/optional-modal")
    run = await env.run(modal_plan())
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await modal_counts(env) == ("0", "0", "iki")


@pytest.mark.parametrize("mode", ["other", "two"])
async def test_different_text_or_two_dialogs_stop(env: Env, mode: str) -> None:
    await env.goto(f"/pages/optional-modal?mode={mode}")
    run = await env.run(modal_plan())
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert await modal_counts(env) == ("0", "0", "")


async def test_undeclared_dialog_stops(env: Env) -> None:
    await env.goto("/pages/optional-modal?mode=info")
    run = await env.run(modal_plan()[1:])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert await modal_counts(env) == ("0", "0", "")
