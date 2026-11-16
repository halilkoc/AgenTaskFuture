"""Yürütme motoru: adapterler, toparlanma, dispatch/uzlaştırma, iptal ve eşzamanlılık — gerçek Chromium +
lab."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.errors import SessionBusy
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.runs import RunService
from agentask.config import Settings
from agentask.domain.runtime import RunStatus, StepState
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"


@dataclass
class Env:
    service: RunService
    sessions: BrowserSessionService
    sid: str
    lab: LabServer
    settings: Settings
    run_dir: Path

    @property
    def page(self) -> Any:
        return self.sessions.peek(OWNER, self.sid).page  # type: ignore[attr-defined]

    async def goto(self, path: str, user: str = "ayse") -> None:
        handle = self.sessions.peek(OWNER, self.sid)
        await handle.navigate(f"{self.lab.primary}/__lab/autologin?user={user}&next={path}")

    async def run(
        self, steps: list[dict[str, Any]], request_id: str | None = None, timeout: float = 30
    ) -> Any:
        run = await self.service.create(OWNER, self.sid, request_id or f"req-{id(steps)}-{len(steps)}", steps)
        return await self.service.wait(run.run_id, timeout)

    def commits(self) -> list[str]:
        return [c["text"] for c in self.lab.control("GET", "/__lab/state").json()["commits"]]


def build(
    settings: Settings, factory: PlaywrightContextFactory, run_dir: Path
) -> tuple[RunService, BrowserSessionService]:
    sessions = BrowserSessionService(factory, SessionLimits(max_sessions=4, max_per_user=2, idle_seconds=600))
    repo = LocalFileRunRepository(run_dir)
    executor = Executor(
        repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)
    )
    return RunService(repo, sessions, executor, LAB_ACTION_SET, max_steps=settings.run_max_steps), sessions


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    settings = lab_settings(
        make_env_file,
        lab,
        READINESS_TIMEOUT_MS="3000",
        OUTCOME_TIMEOUT_MS="3000",
        RECONCILE_TIMEOUT_MS="3000",
        ACTION_TIMEOUT_MS="3000",
    )
    factory = PlaywrightContextFactory(settings)
    service, sessions = build(settings, factory, tmp_path / "runs")
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()


T = {"kind": "textbox"}
NOTE = {"kind": "textbox", "labels": ["Not"]}


def states(run: Any) -> list[str]:
    return [s.state.value for s in run.steps]


async def test_textbox_write_verify_and_no_change(env: Env) -> None:
    await env.goto("/pages/duplicates")
    target = {**T, "labels": ["Müşteri No"], "region": "Kefil"}
    run = await env.run(
        [
            {"op": "ensure_value", "target": target, "value": "00123"},
            {
                "op": "assert_condition",
                "condition": {"type": "value_equals", "target": target, "value": "00123"},
            },
            {"op": "ensure_value", "target": target, "value": "00123"},
            {"op": "read", "target": target},
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert states(run) == ["succeeded"] * 4
    assert run.steps[0].result["changed"] is True
    assert run.steps[2].result["changed"] is False
    assert run.steps[3].result["value"] == "00123"
    assert (
        await env.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value() == "00123"
    )


async def test_card_application_reuses_adapters(env: Env) -> None:
    await env.goto("/pages/dropdowns")
    run = await env.run(
        [
            {"op": "ensure_choice", "target": {"kind": "select", "labels": ["Şube"]}, "choice": "Beşiktaş"},
            {
                "op": "ensure_choice",
                "target": {"kind": "combobox", "labels": ["Ürün Tipi"]},
                "choice": "Ek Kart",
            },
            {"op": "activate_tab", "target": {"kind": "tab", "labels": ["Teslimat"]}},
            {"op": "ensure_value", "target": {**T, "labels": ["Teslimat Adresi"]}, "value": "Konak / İzmir"},
            {
                "op": "assert_condition",
                "condition": {"type": "tab_active", "target": {"kind": "tab", "labels": ["Teslimat"]}},
            },
            {
                "op": "assert_condition",
                "condition": {
                    "type": "choice_equals",
                    "target": {"kind": "combobox", "labels": ["Ürün Tipi"]},
                    "choice": "Ek Kart",
                },
            },
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert [s.result.get("adapter") for s in run.steps[:4]] == [
        "native_select",
        "custom_combobox",
        "tab",
        "textbox",
    ]
    assert await env.page.get_by_label("Şube").input_value() == "besiktas"


async def test_find_record_by_business_key(env: Env) -> None:
    env.lab.set_scenario(table_rows=40, page_size=10, scroll_batch=15)
    await env.goto("/pages/table-paged")
    run = await env.run(
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Başvurular"]},
                "key": "B-1032",
                "navigation": "paged",
            }
        ]
    )
    assert run.status is RunStatus.COMPLETED and run.steps[0].result["pages_visited"] == 4
    await env.goto("/pages/table-scroll")
    await env.page.get_by_role("table", name="Hareketler").locator("tbody tr").nth(14).wait_for()
    run = await env.run(
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Hareketler"]},
                "key": "B-1037",
                "navigation": "scroll",
                "end_text": "Tüm kayıtlar yüklendi",
            }
        ]
    )
    assert run.status is RunStatus.COMPLETED
    missing = await env.run(
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Hareketler"]},
                "key": "B-9999",
                "navigation": "scroll",
                "end_text": "Tüm kayıtlar yüklendi",
            }
        ]
    )
    assert missing.status is RunStatus.FAILED and missing.steps[0].result["outcome"] == "not_found_at_end"


async def test_table_larger_than_its_scroll_area_is_not_reported_as_covered(env: Env) -> None:
    """Kaydırma alanından büyük tablonun merkezi alanın dışında kalabilir; o noktadaki komşu öğe tabloyu
    kapatan bir katman değildir (Firefox satır ölçüleriyle ortaya çıktı; test geometriyi kendi kurar)."""
    await env.goto("/pages/table-scroll")
    rows = env.page.get_by_role("table", name="Hareketler").locator("tbody tr")
    await rows.nth(14).wait_for()
    await env.page.evaluate("const r = document.querySelector('.scroll'); r.scrollTop = r.scrollHeight")
    await rows.nth(29).wait_for()
    above = await env.page.evaluate(
        """() => {
          const region = document.querySelector('.scroll'), table = region.querySelector('table');
          const block = document.createElement('div');
          block.id = 'komsu'; block.style.height = '200px'; block.textContent = 'Komşu içerik';
          region.before(block);
          region.scrollTop = Math.floor(table.offsetHeight / 2 + 60);
          const t = table.getBoundingClientRect(), g = region.getBoundingClientRect();
          const hit = document.elementFromPoint(t.left + t.width / 2, t.top + t.height / 2);
          return { clipped: t.top + t.height / 2 < g.top, hit: hit ? hit.id : null,
                   atEnd: region.scrollTop + region.clientHeight >= region.scrollHeight - 20 };
        }"""
    )
    assert above == {"clipped": True, "hit": "komsu", "atEnd": False}  # kurulum: merkez alanın üstünde
    run = await env.run(
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Hareketler"]},
                "key": "B-1037",
                "navigation": "scroll",
                "end_text": "Tüm kayıtlar yüklendi",
            }
        ]
    )
    assert run.status is RunStatus.COMPLETED and run.steps[0].result["outcome"] == "found"


async def test_ambiguous_target_is_not_dispatched(env: Env) -> None:
    await env.goto("/pages/duplicates")
    run = await env.run([{"op": "ensure_value", "target": {**T, "labels": ["Müşteri No"]}, "value": "1"}])
    assert run.status is RunStatus.PAUSED_AMBIGUOUS
    assert run.steps[0].state is StepState.KNOWN_FAILED and run.steps[0].error_class == "TARGET_AMBIGUOUS"
    for region in ("Başvuran", "Kefil"):
        assert (
            await env.page.get_by_role("region", name=region).get_by_label("Müşteri No").input_value() == ""
        )


class FrameReloadingDriver:
    """Test aracı: ilk yazmadan hemen önce hedefin frame'ini yeniden yükler (bayat aday senaryosu)."""

    def __init__(self, real: Any, page: Any) -> None:
        self._real, self._page, self.reloaded = real, page, False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def fill(self, cid: str, value: str) -> None:
        if not self.reloaded:
            self.reloaded = True
            level1 = next(f for f in self._page.frames if "/frames/level1" in f.url)
            async with self._page.expect_event("framenavigated"):
                await level1.evaluate("location.reload()")
            await (
                self._page.frame_locator("iframe[title='Vaka Ayrıntıları']")
                .frame_locator("iframe[title='Adres Bilgileri']")
                .get_by_label("Adres")
                .wait_for()
            )
        await self._real.fill(cid, value)


async def test_frame_recreated_before_write_is_safely_re_resolved(env: Env) -> None:
    env.lab.set_scenario(late_frame_delay_ms=30_000)
    await env.goto("/pages/frames")
    page = env.page
    await (
        page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .wait_for()
    )
    handle = env.sessions.peek(OWNER, env.sid)

    class Wrapped:
        observer = handle.observer
        driver = FrameReloadingDriver(handle.driver, page)

    from agentask.domain.runtime import Run

    repo = LocalFileRunRepository(env.run_dir)
    executor = Executor(
        repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(env.settings)
    )
    run = Run.new(
        owner_id=OWNER,
        session_id=env.sid,
        request_id="frame-1",
        payload_hash="h",
        commands=[{"op": "ensure_value", "target": {**T, "labels": ["Adres"]}, "value": "Atatürk Cad."}],
    )
    async with env.sessions.operation(OWNER, env.sid, "run"):
        run = await executor.execute(run, Wrapped())  # type: ignore[arg-type]
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert "FRAME_CHANGED" in run.steps[0].recoveries
    value = (
        await page.frame_locator("iframe[title='Vaka Ayrıntıları']")
        .frame_locator("iframe[title='Adres Bilgileri']")
        .get_by_label("Adres")
        .input_value()
    )
    assert value == "Atatürk Cad."


def note_plan(text: str) -> list[dict[str, Any]]:
    return [
        {"op": "ensure_value", "target": NOTE, "value": text},
        {"op": "invoke_approved_action", "action_id": "lab.add_case_note", "params": {"text": text}},
    ]


async def test_add_note_happy_path(env: Env) -> None:
    await env.goto("/pages/note-form")
    run = await env.run(note_plan("İlk arama yapıldı"))
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    invoke = run.steps[1]
    assert invoke.intent is not None and invoke.intent["baseline"] == 0
    assert invoke.result["verified_by"] == "outcome"
    assert env.commits() == ["İlk arama yapıldı"]


async def test_unknown_modal_stops_without_closing(env: Env) -> None:
    env.lab.set_scenario(dialog="unknown_modal")
    await env.goto("/pages/note-form")
    run = await env.run(note_plan("Gönderilmemeli"))
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "UNKNOWN_DIALOG"
    assert run.steps[0].state is StepState.PENDING
    assert await env.page.get_by_role("dialog", name="Onay Gerekli").is_visible()
    assert env.commits() == []


async def test_known_modal_handled_by_defined_behaviour(env: Env) -> None:
    env.lab.set_scenario(dialog="modal")
    await env.goto("/pages/note-form")
    run = await env.run(note_plan("Uyarı sonrası not"))
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert "KNOWN_OVERLAY:lab.case_updated_notice" in run.steps[0].recoveries
    assert env.commits() == ["Uyarı sonrası not"]


async def test_native_dialog_stops_and_is_not_dismissed(env: Env) -> None:
    env.lab.set_scenario(dialog="native")
    # alert 'load' öncesi açılır ve kapatılmadığı için sayfa yüklemesi tamamlanmaz; yalnız commit beklenir.
    observer = env.sessions.peek(OWNER, env.sid).observer  # type: ignore[attr-defined]
    await env.page.goto(
        f"{env.lab.primary}/__lab/autologin?user=ayse&next=/pages/note-form", wait_until="commit"
    )
    for _ in range(100):
        if observer.native_dialog is not None:
            break
        await asyncio.sleep(0.05)
    run = await env.run(note_plan("Gönderilmemeli"), timeout=40)
    assert run.status is RunStatus.PAUSED_BLOCKED and run.steps[0].error_class == "UNKNOWN_DIALOG"
    assert env.sessions.peek(OWNER, env.sid).observer.native_dialog is not None  # type: ignore[attr-defined]
    assert env.commits() == []


async def test_session_loss_before_run_pauses(env: Env) -> None:
    await env.goto("/pages/note-form")
    env.lab.control("POST", "/__lab/sessions/expire")
    await env.page.reload()
    run = await env.run(note_plan("Gönderilmemeli"))
    assert run.status is RunStatus.PAUSED_SESSION and run.steps[0].error_class == "SESSION_EXPIRED"
    assert states(run) == ["pending", "pending"]
    assert env.commits() == []


async def test_session_loss_at_dispatch_pauses_then_resumes_once(env: Env) -> None:
    await env.goto("/pages/note-form")
    env.lab.control("POST", "/__lab/sessions/expire")  # sayfa yüklü, sunucu oturumu düştü
    run = await env.run(note_plan("Oturum sonrası not"))
    assert run.status is RunStatus.PAUSED_SESSION, run.model_dump()
    assert run.steps[1].state is StepState.KNOWN_FAILED and run.steps[1].error_class == "SESSION_EXPIRED"
    assert env.commits() == []
    await env.goto("/pages/note-form")
    resumed = await env.service.resume(OWNER, run.run_id, env.sid)
    resumed = await env.service.wait(resumed.run_id, 30)
    assert resumed.status is RunStatus.COMPLETED, resumed.model_dump()
    assert env.commits() == ["Oturum sonrası not"]


async def test_lost_response_reconciled_without_double_commit(env: Env) -> None:
    env.lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=6000, client_timeout_ms=800)
    await env.goto("/pages/note-form")
    run = await env.run(note_plan("Yanıtı kaybolan not"))
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    invoke = run.steps[1]
    assert invoke.result["verified_by"] == "reconciliation"
    assert "WRITE_RESULT_UNKNOWN" in invoke.recoveries
    assert env.commits() == ["Yanıtı kaybolan not"]


async def test_interruption_after_dispatch_keeps_outcome_unknown(env: Env) -> None:
    env.lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=6000, client_timeout_ms=800)
    await env.goto("/pages/note-form")
    run = await env.service.create(OWNER, env.sid, "lost-and-expired", note_plan("Belirsiz not"))
    for _ in range(100):  # gönderim olduktan sonra oturumu düşür → uzlaştırma okuması giriş sayfasına düşer
        if env.commits():
            break
        await asyncio.sleep(0.05)
    env.lab.control("POST", "/__lab/sessions/expire")
    run = await env.service.wait(run.run_id, 30)
    assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
    assert run.steps[1].state is StepState.OUTCOME_UNKNOWN
    assert env.commits() == ["Belirsiz not"]

    await env.goto("/pages/note-form")
    resumed = await env.service.resume(OWNER, run.run_id, env.sid)
    resumed = await env.service.wait(resumed.run_id, 30)
    assert resumed.status is RunStatus.COMPLETED, resumed.model_dump()
    assert resumed.steps[1].result["verified_by"] == "reconciliation"
    assert env.commits() == ["Belirsiz not"], "uzlaştırma ikinci gönderim yapmamalı"


async def test_restart_after_dispatch_keeps_outcome_unknown(
    env: Env, factory: PlaywrightContextFactory
) -> None:
    env.lab.set_scenario(
        lose_next_commit_response=True, lost_response_hang_ms=20_000, client_timeout_ms=15_000
    )
    await env.goto("/pages/note-form")
    run = await env.service.create(OWNER, env.sid, "crash-1", note_plan("Çöküş notu"))
    for _ in range(200):
        stored = LocalFileRunRepository(env.run_dir).get(run.run_id)
        if stored and stored.steps[1].state is StepState.VERIFYING:
            break
        await asyncio.sleep(0.05)
    task = env.service.task_for(run.run_id)
    assert task is not None
    task.cancel()  # süreç çöküşü benzetimi: hiçbir son durum yazılmaz
    await asyncio.gather(task, return_exceptions=True)
    stored = LocalFileRunRepository(env.run_dir).get(run.run_id)
    assert stored is not None and stored.steps[1].state is StepState.VERIFYING

    restarted, _ = build(env.settings, factory, env.run_dir)
    recovered = restarted.start_recovery()
    assert [r.run_id for r in recovered] == [run.run_id]
    after = restarted.get(OWNER, run.run_id)
    assert after.status is RunStatus.OUTCOME_UNKNOWN and after.steps[1].state is StepState.OUTCOME_UNKNOWN
    assert after.status_reason == "process_restart"
    assert env.commits() == ["Çöküş notu"]


async def test_conflicting_execution_on_same_session_rejected(env: Env) -> None:
    env.lab.set_scenario(delay_ms=700, table_rows=40, page_size=10)
    await env.goto("/pages/table-paged")
    env.lab.set_scenario(delay_ms=700)
    first = await env.service.create(
        OWNER,
        env.sid,
        "busy-1",
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Başvurular"]},
                "key": "B-1039",
                "navigation": "paged",
            }
        ],
    )
    with pytest.raises(SessionBusy):
        await env.service.create(OWNER, env.sid, "busy-2", [{"op": "read", "target": {**T, "labels": ["X"]}}])
    done = await env.service.wait(first.run_id, 30)
    assert done.status is RunStatus.COMPLETED


async def test_cancel_prevents_next_step(env: Env) -> None:
    env.lab.set_scenario(table_rows=40, page_size=10)
    await env.goto("/pages/table-paged")
    env.lab.set_scenario(delay_ms=600)
    run = await env.service.create(
        OWNER,
        env.sid,
        "cancel-1",
        [
            {
                "op": "find_record",
                "table": {"kind": "table", "labels": ["Başvurular"]},
                "key": "B-1039",
                "navigation": "paged",
            },
            {"op": "read", "target": {"kind": "table", "labels": ["Başvurular"]}},
        ],
    )
    await asyncio.sleep(0.4)
    await env.service.cancel(OWNER, run.run_id)
    done = await env.service.wait(run.run_id, 30)
    assert done.status is RunStatus.CANCELLED
    assert done.steps[0].state is StepState.SUCCEEDED  # başlamış adım tamamlanır, geri alınmaz
    assert done.steps[1].state is StepState.SKIPPED and done.steps[1].attempts == 0


async def test_request_id_idempotency(env: Env) -> None:
    await env.goto("/pages/duplicates")
    steps = [{"op": "read", "target": {**T, "labels": ["Müşteri No"], "region": "Kefil"}}]
    first = await env.service.create(OWNER, env.sid, "same-req", steps)
    await env.service.wait(first.run_id, 20)
    again = await env.service.create(OWNER, env.sid, "same-req", steps)
    assert again.run_id == first.run_id
    from agentask.application.errors import IdempotencyConflict

    with pytest.raises(IdempotencyConflict):
        await env.service.create(
            OWNER, env.sid, "same-req", [{"op": "read", "target": {**T, "labels": ["Y"]}}]
        )


async def test_prior_read_output_is_bound_at_runtime(env: Env) -> None:
    """C3: önceki okuma çıktısı gerçek okumadan bağlanır; değer planda yoktur."""
    await env.goto("/wizard/C-778")
    case = {**T, "labels": ["Vaka No"], "region": "Vaka"}
    customer = {**T, "labels": ["Müşteri No"], "region": "Müşteri"}
    ref = {"step": 0, "max_length": 20}
    run = await env.run(
        [
            {"op": "read", "target": case},
            {"op": "ensure_value", "target": customer, "value_from": ref},
            {
                "op": "assert_condition",
                "condition": {"type": "value_equals", "target": customer, "value_from": ref},
            },
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.steps[1].result["value_from_step"] == 0
    assert await env.page.get_by_role("region", name="Müşteri").get_by_label("Müşteri No").input_value() == (
        "C-778"
    )


async def test_empty_prior_output_stops_without_writing(env: Env) -> None:
    await env.goto("/wizard/C-779")
    case = {**T, "labels": ["Vaka No"], "region": "Vaka"}
    customer = {**T, "labels": ["Müşteri No"], "region": "Müşteri"}
    run = await env.run(
        [
            {"op": "read", "target": customer},  # boş alan
            {"op": "ensure_value", "target": case, "value_from": {"step": 0, "max_length": 20}},
        ]
    )
    assert run.status is RunStatus.FAILED
    assert run.steps[1].error_class == "PRIOR_OUTPUT_UNAVAILABLE"
    assert run.steps[1].state is StepState.KNOWN_FAILED
    assert "boş" in (run.steps[1].message or "")
