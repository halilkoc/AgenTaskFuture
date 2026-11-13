"""R4 çok ekranlı yürütme — gerçek Chromium + deney sihirbazı, yayından derlenen planlar (sahte
katalog deposu).

Negatif testler yalnız hata koduna bakmaz: sürücü çağrıları (fill/click/select) sayılır, sunucu
tarafı sayaçlar
(geçiş tetiklemesi, gönderim) ve alan durumları kontrol edilir.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.services.assistant import AssistantService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.domain.runtime import Run, RunStatus, StepState
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.fake_catalog_store import FakeCatalogStore
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import HitCounterServer, LabServer
from tests.unit.test_publishing import ready_draft
from tests.wizard import ARGS, wizard_draft

pytestmark = pytest.mark.browser
OWNER = "ayse"
CASE = ARGS["vaka_no"]


@dataclass
class Env:
    assistant: AssistantService
    runs: RunService
    sessions: BrowserSessionService
    store: FakeCatalogStore
    sid: str
    lab: LabServer
    release_id: str
    writes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def page(self) -> Any:
        return self.sessions.peek(OWNER, self.sid).page  # type: ignore[attr-defined]

    async def goto(self, path: str) -> None:
        await self.sessions.peek(OWNER, self.sid).navigate(
            f"{self.lab.primary}/__lab/autologin?user=ayse&next={path}"
        )

    async def run(self, op: str = "basvuru_gonder", args: dict[str, str] | None = None) -> Run:
        run = await self.assistant.execute(
            OWNER, self.sid, self.release_id, op, args or ARGS, secrets.token_hex(6), acknowledge_effect=True
        )
        return await self.runs.wait(run.run_id, 60)

    def lab_state(self) -> dict[str, Any]:
        state: dict[str, Any] = self.lab.control("GET", "/__lab/state").json()
        return state

    def advances(self) -> int:
        return int(self.lab_state()["wizard_advances"].get(CASE, 0))

    def applications(self) -> list[dict[str, Any]]:
        return list(self.lab_state()["applications"])

    def kinds(self) -> list[str]:
        return [w[0] for w in self.writes]


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="2500", OUTCOME_TIMEOUT_MS="5000")
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), SessionLimits(4, 2, 600))
    repo = LocalFileRunRepository(tmp_path / "runs")
    executor = Executor(
        repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)
    )
    runs = RunService(repo, sessions, executor, LAB_ACTION_SET, 100)
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    store = FakeCatalogStore()
    publishing = PublishService(store, drafts, LAB_ACTION_SET, "arge")
    release = None
    wizard = wizard_draft()
    drafts.create(wizard)
    for d in (wizard, ready_draft(drafts, "kefil_musteri_no", "Kefil müşteri numarasını gir")):
        d = publishing.approve("pub", d.draft_id, d.revision)
        release = await publishing.publish("pub", d.draft_id, f"req-{d.operation_id}")
    assert release is not None
    view = await sessions.open(OWNER)
    e = Env(
        AssistantService(publishing, runs, LAB_ACTION_SET, UnavailableLLM("kapalı"), 2000, 200, 1, "lab"),
        runs,
        sessions,
        store,
        view.session_id,
        lab,
        release.release_id,
    )
    driver = sessions.peek(OWNER, view.session_id).driver  # type: ignore[attr-defined]
    for name in ("fill", "click", "select_option", "click_option"):
        original = getattr(driver, name)

        def spy(cid: str, *args: Any, _o: Any = original, _n: str = name) -> Any:
            e.writes.append((_n, cid))
            return _o(cid, *args)

        setattr(driver, name, spy)
    yield e
    await runs.shutdown()
    await sessions.shutdown()


def failed_step(run: Run) -> Any:
    return next(s for s in run.steps if s.state is StepState.KNOWN_FAILED)


def pending_after(run: Run, index: int) -> bool:
    return all(s.state is StepState.PENDING for s in run.steps[index + 1 :])


async def test_three_screen_flow_completes_once(env: Env) -> None:
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    ops = [s.command["op"] for s in run.steps]
    follow = run.steps[ops.index("follow_transition")]
    assert follow.result["transition_completed"] is True and follow.result["to_screen"] == "basvuru_teminat"
    submit = run.steps[ops.index("invoke_approved_action")]
    assert submit.result["verified_by"] == "outcome" and submit.result["to_screen"] == "basvuru_ozet"
    assert env.advances() == 1  # geçiş bir kez tetiklendi
    [application] = env.applications()
    assert (application["customer_no"], application["amount"], application["document_no"]) == (
        "00456",
        "1500",
        "B-77",
    )
    assert env.kinds() == ["fill", "click", "fill", "fill", "click"]  # 3 yazma + Devam + Gönder
    assert await env.page.get_by_role("heading", name="Başvuru — özet").count() == 1
    assert env.page.url.endswith(f"/wizard/{CASE}/summary?no=1")


async def test_delayed_target_waits_without_retriggering(env: Env) -> None:
    env.lab.set_scenario(wizard_delay_ms=2000)  # geçiş timeout'u (4000 ms) içinde
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert env.advances() == 1
    assert env.kinds().count("click") == 2


async def test_target_timeout_reports_and_never_retriggers(env: Env) -> None:
    env.lab.set_scenario(wizard_delay_ms=9000)  # timeout'tan uzun
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    assert run.status is RunStatus.FAILED, run.model_dump()
    step = failed_step(run)
    assert step.command["op"] == "follow_transition" and step.error_class == "TRANSITION_TIMEOUT"
    assert "kaynak ekran hâlâ görünüyor" in (step.message or "") and "yeniden tetiklenmedi" in (
        step.message or ""
    )
    assert env.kinds() == ["fill", "click"] and env.advances() == 1
    assert pending_after(run, step.index) and env.applications() == []


async def test_unexpected_target_screen_is_not_explored(env: Env) -> None:
    env.lab.set_scenario(wizard_target="unexpected")
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    step = failed_step(run)
    assert run.status is RunStatus.FAILED and step.error_class == "UNEXPECTED_SCREEN", run.model_dump()
    assert env.kinds() == ["fill", "click"] and env.advances() == 1
    assert await env.page.get_by_role("heading", name="Başvuru — red bilgisi").count() == 1
    assert await env.page.get_by_label("Açıklama").input_value() == ""


async def test_duplicated_target_evidence_pauses_ambiguous(env: Env) -> None:
    env.lab.set_scenario(wizard_target="duplicate")
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    step = failed_step(run)
    assert run.status is RunStatus.PAUSED_AMBIGUOUS and step.error_class == "SCREEN_NOT_RECOGNIZED"
    assert step.command["op"] == "follow_transition" and env.kinds() == ["fill", "click"]
    values = await env.page.get_by_label("Teminat Tutarı").evaluate_all("els => els.map(e => e.value)")
    assert values == ["", ""]


async def test_right_screen_type_wrong_case_is_rejected(env: Env) -> None:
    env.lab.set_scenario(wizard_target="other_case")
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    step = failed_step(run)
    assert step.error_class == "RECORD_CONTEXT_MISMATCH" and "kayıt bağlamı farklı" in (step.message or "")
    assert step.command["op"] == "follow_transition"  # geçişin tamamlanma koşulu reddetti
    assert env.kinds() == ["fill", "click"] and pending_after(run, step.index)
    assert await env.page.get_by_label("Teminat Tutarı").input_value() == ""


async def test_wrong_case_on_start_screen_does_nothing(env: Env) -> None:
    await env.goto(f"/wizard/{CASE}")
    run = await env.run(args={**ARGS, "vaka_no": "C-9999"})
    step = failed_step(run)
    assert step.index == 0 and step.error_class == "RECORD_CONTEXT_MISMATCH"
    assert env.writes == [] and env.advances() == 0


async def test_incomplete_scan_stops_before_any_action(env: Env, outsider: HitCounterServer) -> None:
    await env.goto(f"/wizard/{CASE}")
    async with env.page.expect_event("frameattached"):
        await env.page.evaluate(
            "o => { const f = document.createElement('iframe'); f.src = o; document.body.appendChild(f); }",
            outsider.origin,
        )
    await env.page.wait_for_timeout(300)
    run = await env.run()
    step = failed_step(run)
    assert step.error_class == "SCREEN_NOT_RECOGNIZED" and step.result["screen"]["status"] == "incomplete"
    assert env.writes == [] and env.advances() == 0


async def test_lost_response_on_mutating_transition_is_not_resent(env: Env) -> None:
    env.lab.set_scenario(lose_next_submit_response=True, client_timeout_ms=1200, lost_response_hang_ms=6000)
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    assert run.status is RunStatus.FAILED, run.model_dump()
    submit = run.steps[-1]
    assert submit.command["op"] == "invoke_approved_action"
    assert submit.state is StepState.SUCCEEDED and submit.result["verified_by"] == "reconciliation"
    assert submit.error_class == "TRANSITION_NOT_COMPLETED" and "yeniden gönderilmedi" in (
        submit.message or ""
    )
    assert len(env.applications()) == 1  # tek kayıt: tekrar gönderim yok
    assert env.kinds().count("click") == 2  # Devam + tek Gönder
    assert run.status_reason == "TRANSITION_NOT_COMPLETED"


async def test_resume_on_wrong_screen_stops_and_does_not_replay(env: Env) -> None:
    env.lab.set_scenario(wizard_dialog=True)
    await env.goto(f"/wizard/{CASE}")
    run = await env.run()
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert env.advances() == 1 and env.kinds() == ["fill", "click"]
    env.lab.set_scenario(wizard_dialog=False)

    await env.goto(f"/wizard/{CASE}")  # yanlış segment: başlangıç ekranı (teminat ekranı bekleniyor)
    env.writes.clear()
    resumed = await env.runs.wait((await env.runs.resume(OWNER, run.run_id, env.sid)).run_id, 30)
    assert (
        resumed.status is RunStatus.PAUSED_SESSION and resumed.status_reason == "context_revalidation_failed"
    )
    assert env.writes == [] and env.advances() == 1  # geçiş yeniden oynatılmadı, yazma yok

    await env.goto(f"/wizard/{CASE}/collateral")  # doğru ekran ve vaka
    done = await env.runs.wait((await env.runs.resume(OWNER, run.run_id, env.sid)).run_id, 40)
    assert done.status is RunStatus.COMPLETED, done.model_dump()
    assert env.advances() == 1 and len(env.applications()) == 1
    assert "click" in env.kinds() and env.kinds().count("click") == 1  # yalnız Gönder


async def test_only_forbidden_marker_added_rejects_without_writing(env: Env) -> None:
    env.lab.set_scenario(party_layout="with_change_note")  # bütün zorunlu işaretler mevcut + yasak işaret
    await env.goto("/pages/duplicates")
    assert await env.page.get_by_role("region", name="Kefil").get_by_label("Ad Soyad").count() == 1
    run = await env.run("kefil_musteri_no", {"no": "00456"})
    step = failed_step(run)
    assert step.error_class == "SCREEN_NOT_RECOGNIZED" and step.result["screen"]["status"] == "not_recognized"
    required = [m for m in step.result["screen"]["markers"] if m["role"] == "required"]
    assert all(m["outcome"] == "resolved" for m in required)
    assert "Talep Notu" in step.result["screen"]["explanation"] and env.writes == []
    assert await env.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value() == ""


async def test_single_screen_v2_operation_still_runs(env: Env) -> None:
    rev = env.store.revisions[("lab", "kefil_musteri_no", 1)]
    assert rev.schema_version == "catalog-v2" and "transitions" not in rev.definition
    await env.goto("/pages/duplicates")
    run = await env.run("kefil_musteri_no", {"no": "00456"})
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    page = env.page
    assert await page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value() == "00456"
    assert await page.get_by_role("region", name="Başvuran").get_by_label("Müşteri No").input_value() == ""


async def test_changes_analysis_uses_same_screen_core_for_every_screen(env: Env, lab: LabServer) -> None:
    from agentask.application.services.impact import ImpactService
    from agentask.application.services.observation import ObservationService

    publishing = env.assistant._publishing
    impact = ImpactService(publishing, ObservationService(env.sessions, 5000), None, "lab")  # type: ignore[arg-type]
    await env.goto(f"/wizard/{CASE}/collateral")
    result = await impact.analyze(OWNER, env.sid, "basvuru_gonder")
    statuses = {s["screen_id"]: s["status"] for s in result["screens"]}
    assert statuses == {
        "basvuru_musteri": "not_recognized",
        "basvuru_teminat": "recognized",
        "basvuru_ozet": "not_recognized",
    }
    assert result["screen"]["screen_id"] == "basvuru_teminat"
    deps = await impact.dependency_impact([], [], ["basvuru_teminat"])
    assert [i["operation_id"] for i in deps["impacted"]] == ["basvuru_gonder"]
