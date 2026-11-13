"""Dinamik ekran ve pencere bağlamı (ADR 0014) — gerçek Chromium + lab /pages/popups.

Kapsam: kapalı penceredeki aynı isimli alan, aktif modal ve arkasındaki alan, beklenen (ekran tanımlı)
pencere, iki etkin pencere, kaplayan katman (kalıcı/geçici), ilgisiz DOM değişikliği, yeniden çizilen alan,
yeni pencere, tarayıcı onay penceresi ve modal içinde seçim. Pop-up'lar otomatik kapatılmaz.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentask.application.services.observation import resolve_target
from agentask.domain.observation import ControlKind
from agentask.domain.runtime import RunStatus
from agentask.domain.targeting import Outcome, TargetSpec
from tests.integration.browser import test_executor as base
from tests.integration.browser.test_executor import OWNER, Env

pytestmark = pytest.mark.browser
env = base.env  # gerçek Chromium + lab yürütme ortamı (fikstür)

CUSTOMER = {"kind": "textbox", "labels": ["Müşteri No"]}
NOTE = {"kind": "textbox", "labels": ["Not"]}
NOTE_SCREEN = {
    "op": "assert_screen",
    "screen": {
        "screen_id": "not_penceresi",
        "title": "Not penceresi",
        "regions": [{"region_id": "not_ekle", "name": "Not ekle"}],
        "markers": [{**NOTE, "region": "Not ekle"}],
    },
}


async def _resolve(env: Env, spec: dict[str, Any]) -> Any:
    async with env.sessions.operation(OWNER, env.sid, "resolve") as handle:
        return await resolve_target(handle.observer, TargetSpec.model_validate(spec))


def _section(env: Env, name: str) -> Any:
    return env.page.get_by_role("region", name=name)


async def test_hidden_dialog_copy_is_not_an_active_target(env: Env) -> None:
    await env.goto("/pages/popups")
    r = await _resolve(env, CUSTOMER)
    assert r.outcome is Outcome.RESOLVED, r.to_dict()
    assert [c.interaction for c in r.candidates] == ["open"]  # kapalı penceredeki kopya aday değil
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}])
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == "00456"
    assert await env.page.locator(".hidden-dialog input").input_value() == ""


async def test_active_modal_wins_and_field_behind_it_is_never_used(env: Env) -> None:
    await env.goto("/pages/popups?modal=open")
    inside = await _resolve(env, NOTE)
    assert inside.outcome is Outcome.RESOLVED
    chosen = next(c for c in inside.candidates if c.candidate_id == inside.candidate_id)
    assert any(ctx["kind"] == "dialog" and ctx["name"] == "Not ekle" for ctx in chosen.contexts)
    behind = await _resolve(env, {**NOTE, "region": "Başvuru"})
    assert behind.outcome is Outcome.UNRESOLVED and behind.reason == "blocked"
    # Pencere ekran tanımında yoksa beklenmeyen pencere: kapatılmaz, hiçbir alana yazılmaz.
    run = await env.run([{"op": "ensure_value", "target": NOTE, "value": "yazılmamalı"}])
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "UNKNOWN_DIALOG"
    assert await env.page.locator(".note-dialog").evaluate("d => d.open")
    assert await env.page.locator(".note-dialog input").input_value() == ""
    assert await _section(env, "Başvuru").get_by_label("Not").input_value() == ""


async def test_expected_dialog_defined_in_screen_allows_work_inside_it(env: Env) -> None:
    await env.goto("/pages/popups?modal=open")
    run = await env.run(
        [NOTE_SCREEN, {"op": "ensure_value", "target": {**NOTE, "region": "Not ekle"}, "value": "Arandı"}]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await env.page.locator(".note-dialog input").input_value() == "Arandı"
    assert await _section(env, "Başvuru").get_by_label("Not").input_value() == ""


async def test_two_independent_active_dialogs_stop(env: Env) -> None:
    await env.goto("/pages/popups?two=1")
    r = await _resolve(env, {"kind": "textbox", "labels": ["Ad"]})
    assert r.outcome is Outcome.UNRESOLVED and r.reason == "multiple_active_dialogs"
    run = await env.run(
        [{"op": "ensure_value", "target": {"kind": "textbox", "labels": ["Ad"]}, "value": "x"}]
    )
    assert run.status is RunStatus.PAUSED_BLOCKED
    assert [await i.input_value() for i in await env.page.locator("[role=dialog] input").all()] == ["", ""]


async def test_blocking_overlay_is_not_clicked_through(env: Env) -> None:
    await env.goto("/pages/popups?overlay=0")
    r = await _resolve(env, CUSTOMER)
    assert r.outcome is Outcome.UNRESOLVED and r.reason == "blocked"
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}])
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "TARGET_BLOCKED"
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == ""


async def test_transient_overlay_is_waited_on_condition_then_written(env: Env) -> None:
    await env.goto("/pages/popups?overlay=800")
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}])
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert "TARGET_NOT_READY" in run.steps[0].recoveries
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == "00456"


async def test_unrelated_dom_changes_do_not_block_resolution(env: Env) -> None:
    await env.goto("/pages/popups?ticker=1")
    run = await env.run(
        [
            {"op": "ensure_value", "target": CUSTOMER, "value": "00789"},
            {
                "op": "assert_condition",
                "condition": {"type": "value_equals", "target": CUSTOMER, "value": "00789"},
            },
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert int((await env.page.locator(".ticker").inner_text()).split()[-1]) > 0  # sayfa değişmeye devam etti


class RedrawBeforeFillDriver:
    """Test aracı: ilk yazmadan hemen önce alanı yeni bir DOM düğümüyle yeniden çizer (bayat element)."""

    def __init__(self, real: Any, page: Any) -> None:
        self._real, self._page, self.redrawn = real, page, False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def fill(self, cid: str, value: str) -> None:
        if not self.redrawn:
            self.redrawn = True
            await self._page.evaluate(
                "document.querySelector('.redraw').dispatchEvent(new MouseEvent('click'))"
            )
        await self._real.fill(cid, value)


async def test_recreated_element_is_re_resolved_not_reused(env: Env) -> None:
    from agentask.application.controls import AdapterRegistry
    from agentask.application.services.executor import Executor, ExecutorConfig
    from agentask.domain.runtime import Run
    from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
    from agentask.infrastructure.runs.local_file import LocalFileRunRepository

    await env.goto("/pages/popups")
    handle = env.sessions.peek(OWNER, env.sid)
    driver = RedrawBeforeFillDriver(handle.driver, env.page)  # type: ignore[attr-defined]

    class Wrapped:
        observer = handle.observer

    Wrapped.driver = driver  # type: ignore[attr-defined]
    executor = Executor(
        LocalFileRunRepository(env.run_dir),
        LAB_ACTION_SET,
        AdapterRegistry.default(),
        ExecutorConfig.from_settings(env.settings),
    )
    run = Run.new(
        owner_id=OWNER,
        session_id=env.sid,
        request_id="redraw-1",
        payload_hash="h",
        commands=[{"op": "ensure_value", "target": CUSTOMER, "value": "00321"}],
    )
    async with env.sessions.operation(OWNER, env.sid, "run"):
        run = await executor.execute(run, Wrapped())  # type: ignore[arg-type]
    assert driver.redrawn
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.steps[0].recoveries  # eski element kullanılmadı; hedef yeniden çözüldü
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == "00321"


async def _wait(predicate: Any, tries: int = 100) -> None:
    for _ in range(tries):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("koşul gerçekleşmedi")


async def test_new_window_pauses_and_is_not_switched_or_closed(env: Env) -> None:
    await env.goto("/pages/popups")
    observer = env.sessions.peek(OWNER, env.sid).observer
    await env.page.evaluate("document.querySelector('.open-window').click()")
    await _wait(lambda: observer.new_windows == 1)
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}], request_id="nw-1")
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "NEW_WINDOW"
    assert observer.new_windows == 1  # otomatik kapatılmadı
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == ""
    # Kullanıcının açık kararıyla (görülen pencere kimliğiyle) kapatılınca yeni çalıştırma ana sayfada sürer.
    seen = [w["id"] for w in observer.interruption_state()["new_windows"]]
    assert await observer.close_new_windows(seen) == seen
    assert not env.page.is_closed()  # ana çalışma sayfası kapatılmadı
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}], request_id="nw-2")
    assert run.status is RunStatus.COMPLETED, run.model_dump()


async def test_browser_confirm_pauses_and_is_dismissed_only_on_request(env: Env) -> None:
    await env.goto("/pages/popups")
    observer = env.sessions.peek(OWNER, env.sid).observer
    task = asyncio.ensure_future(env.page.evaluate("document.querySelector('.ask-confirm').click()"))
    await _wait(lambda: observer.native_dialog is not None)
    assert observer.native_dialog[0] == "confirm"
    run = await env.run(
        [{"op": "ensure_value", "target": CUSTOMER, "value": "x"}], request_id="nd-1", timeout=40
    )
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "UNKNOWN_DIALOG"
    assert observer.native_dialog is not None  # kendiliğinden kapatılmadı
    seen = observer.interruption_state()["browser_dialog"]["id"]
    # Aynı karar eşzamanlı iki kez gelirse yalnız biri uygulanır.
    results = await asyncio.gather(observer.dismiss_native_dialog(seen), observer.dismiss_native_dialog(seen))
    assert sorted(results) == [False, True]
    await task
    assert await env.page.locator(".ticker").get_attribute("data-confirm") == "false"  # iptal: onay verilmedi


async def test_picker_inside_modal_selects_without_typing(env: Env) -> None:
    await env.goto("/pages/popups?modal=open")
    observer = env.sessions.peek(OWNER, env.sid).observer
    async with env.sessions.operation(OWNER, env.sid, "picker"):
        await observer.observe()
        await observer.start_picker()
    box = await env.page.locator(".note-dialog input").bounding_box()
    assert box is not None
    await env.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await env.page.keyboard.type("yazılmamalı")
    assert await observer.wait_raw_pick(5)
    async with env.sessions.operation(OWNER, env.sid, "picker"):
        event = await observer.map_pick()
        await observer.stop_picker()
    assert event.reason == "picked" and event.candidate_id
    control = observer.current_snapshot.control(event.candidate_id)
    assert control.kind is ControlKind.TEXTBOX and control.label == "Not"
    assert any(c.kind == "dialog" and c.name == "Not ekle" for c in control.contexts)
    assert await env.page.locator(".note-dialog input").input_value() == ""
    assert await env.page.locator("[data-agentask-ui]").count() == 0  # seçim katmanı temizlendi


async def test_small_cover_over_target_blocks_regardless_of_size(env: Env) -> None:
    await env.goto("/pages/popups?cover=1")
    r = await _resolve(env, CUSTOMER)
    assert r.outcome is Outcome.UNRESOLVED and r.reason == "blocked"
    run = await env.run([{"op": "ensure_value", "target": CUSTOMER, "value": "00456"}])
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "TARGET_BLOCKED"
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == ""


class CoverBeforeFillDriver:
    """Test aracı: hedef çözüldükten sonra, yazmadan hemen önce alanın ortasına küçük bir katman koyar."""

    def __init__(self, real: Any, page: Any) -> None:
        self._real, self._page, self.covered = real, page, False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def fill(self, cid: str, value: str) -> None:
        if not self.covered:
            self.covered = True
            await self._page.evaluate("window.labAddCover()")
        await self._real.fill(cid, value)


async def test_cover_appearing_at_action_time_prevents_write_and_re_resolves(env: Env) -> None:
    from agentask.application.controls import AdapterRegistry
    from agentask.application.services.executor import Executor, ExecutorConfig
    from agentask.domain.runtime import Run
    from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
    from agentask.infrastructure.runs.local_file import LocalFileRunRepository

    await env.goto("/pages/popups")
    handle = env.sessions.peek(OWNER, env.sid)
    driver = CoverBeforeFillDriver(handle.driver, env.page)  # type: ignore[attr-defined]

    class Wrapped:
        observer = handle.observer

    Wrapped.driver = driver  # type: ignore[attr-defined]
    executor = Executor(
        LocalFileRunRepository(env.run_dir),
        LAB_ACTION_SET,
        AdapterRegistry.default(),
        ExecutorConfig.from_settings(env.settings),
    )
    run = Run.new(
        owner_id=OWNER,
        session_id=env.sid,
        request_id="cover-1",
        payload_hash="h",
        commands=[{"op": "ensure_value", "target": CUSTOMER, "value": "00654"}],
    )
    async with env.sessions.operation(OWNER, env.sid, "run"):
        run = await executor.execute(run, Wrapped())  # type: ignore[arg-type]
    assert driver.covered
    assert "TARGET_BLOCKED" in run.steps[0].recoveries  # eylem anında engel görüldü, hedef yeniden çözüldü
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "TARGET_BLOCKED"
    assert await _section(env, "Başvuru").get_by_label("Müşteri No").input_value() == ""


async def test_same_named_decoy_dialog_is_not_accepted_as_expected(env: Env) -> None:
    # Ekran "Not ekle" bölgesini tanımlıyor, aynı adlı bir pencere de açık; ancak bölgenin işareti pencerenin
    # içinde değil (arkadaki aynı adlı sayfa bölümünde). Bölge adı tek başına "beklenen pencere" sayılmaz.
    await env.goto("/pages/popups?modal=decoy")
    run = await env.run(
        [
            NOTE_SCREEN,
            {"op": "ensure_value", "target": {**NOTE, "region": "Not ekle"}, "value": "yazılmamalı"},
        ]
    )
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert run.steps[0].error_class == "UNKNOWN_DIALOG"
    assert await env.page.locator(".decoy-section input").input_value() == ""
    assert await env.page.locator(".decoy-dialog").evaluate("d => d.open")  # kapatılmadı


async def test_stale_window_decision_is_not_applied_to_a_later_window(env: Env) -> None:
    await env.goto("/pages/popups")
    observer = env.sessions.peek(OWNER, env.sid).observer
    await env.page.evaluate("document.querySelector('.open-window').click()")
    await _wait(lambda: observer.new_windows == 1)
    first = observer.interruption_state()["new_windows"][0]["id"]
    # İlk pencere kendiliğinden kapanır, ardından başka bir pencere açılır; kullanıcının ekranındaki eski
    # karar yalnız ilk pencereye aittir.
    await observer._new_pages[0][1].close()
    await _wait(lambda: observer.new_windows == 0)
    await env.page.evaluate("document.querySelector('.open-window').click()")
    await _wait(lambda: observer.new_windows == 1)
    assert await observer.close_new_windows([first]) is None
    assert observer.new_windows == 1  # sonradan açılan pencere kapatılmadı
    second = observer.interruption_state()["new_windows"][0]["id"]
    assert second != first
    # Görülen ve görülmeyen kimlik birlikte istenirse de hiçbiri kapatılmaz (kısmi uygulama yok).
    assert await observer.close_new_windows([second, first]) is None
    assert observer.new_windows == 1
    assert await observer.close_new_windows([second]) == [second]
    assert observer.new_windows == 0 and not env.page.is_closed()


async def test_stale_dialog_decision_does_not_dismiss_a_new_dialog(env: Env) -> None:
    await env.goto("/pages/popups")
    observer = env.sessions.peek(OWNER, env.sid).observer
    task = asyncio.ensure_future(env.page.evaluate("document.querySelector('.ask-confirm').click()"))
    await _wait(lambda: observer.native_dialog is not None)
    first = observer.interruption_state()["browser_dialog"]["id"]
    assert await observer.dismiss_native_dialog(first) is True
    await task
    task = asyncio.ensure_future(env.page.evaluate("document.querySelector('.ask-confirm').click()"))
    await _wait(lambda: observer.native_dialog is not None)
    assert await observer.dismiss_native_dialog(first) is False  # eski karar yeni pencereye uygulanmaz
    assert observer.native_dialog is not None
    second = observer.interruption_state()["browser_dialog"]["id"]
    assert await observer.dismiss_native_dialog(second) is True
    await task


async def test_decision_after_session_closed_is_refused(env: Env) -> None:
    from agentask.application.errors import SessionNotFound
    from agentask.application.services.observation import ObservationService

    await env.goto("/pages/popups")
    observer = env.sessions.peek(OWNER, env.sid).observer
    await env.page.evaluate("document.querySelector('.open-window').click()")
    await _wait(lambda: observer.new_windows == 1)
    seen = [w["id"] for w in observer.interruption_state()["new_windows"]]
    service = ObservationService(env.sessions, 1000)
    await env.sessions.close(OWNER, env.sid)
    with pytest.raises(SessionNotFound):
        await service.resolve_interruption(OWNER, env.sid, "close_new_windows", seen)
    with pytest.raises(SessionNotFound):
        service.interruptions(OWNER, env.sid)
