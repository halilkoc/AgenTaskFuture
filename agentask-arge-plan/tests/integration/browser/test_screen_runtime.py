"""R3 çalışma anı ekran/bölge doğrulaması — gerçek Chromium + deney uygulaması, yayından derlenen planlar.

Her ret senaryosunda sürücü düzeyinde (fill/click/select) hiçbir yazma/tıklama olmadığı ve sayfadaki alanların
boş kaldığı doğrulanır. Ekran tanıma URL'ye bağlı değildir: doğru ekran farklı (rastgele vaka) adresinde de
tanınır; yanlış ekran tanıdık adreste de reddedilir.
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
from agentask.domain.catalog import Confirmation, OperationDraft, ParameterDef, StepStatus
from agentask.domain.runtime import Run, RunStatus, StepState
from agentask.domain.screens import ScreenDef
from agentask.domain.targeting import TargetSpec
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.fake_catalog_store import FakeCatalogStore
from tests.integration.browser.helpers import lab_settings
from tests.screens import APPLICANT_NO, GUARANTOR_NO, PARTIES_SCREEN
from tests.support_lab import HitCounterServer, LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"

ADDRESS = TargetSpec(kind="textbox", labels=["Adres"], frame_title="Adres Bilgileri")
FRAMES_SCREEN = ScreenDef(
    screen_id="vaka_frame",
    title="Vaka — frame ekranı",
    markers=[
        TargetSpec(kind="textbox", labels=["Vaka Durumu"], frame_title="Vaka Ayrıntıları"),
        TargetSpec(kind="textbox", labels=["Belge No"], frame_title="Ek Belgeler"),  # geç eklenen frame
    ],
)


def build_draft(
    op_id: str, screen: ScreenDef, steps: list[tuple[str, TargetSpec, str]], params: list[str]
) -> OperationDraft:
    d = OperationDraft.new(
        created_by=OWNER, application_id="lab", operation_id=op_id, title=op_id, description=""
    )
    d.parameters = [ParameterDef(name=p, title=p, max_length=30, source="user_input") for p in params]
    for element_id, spec, template in steps:
        d.add_element(element_id, element_id, spec, "observed")
        s = d.add_step(f"{element_id} yaz")
        s.op, s.element_id, s.value_template = "ensure_value", element_id, template
        s.move(StepStatus.TARGET_SELECTED)
        s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by=OWNER)
        for st in (
            StepStatus.MEANING_AND_TARGET_CONFIRMED,
            StepStatus.TRIAL_REQUESTED,
            StepStatus.OBSERVED,
            StepStatus.OUTCOME_CONFIRMED,
            StepStatus.READY_FOR_REVIEW,
        ):
            s.move(st)
    d.screen = screen
    d.record_fresh_test(run_id=f"run-{secrets.token_hex(4)}", passed=True)
    return d


@dataclass
class Env:
    assistant: AssistantService
    runs: RunService
    sessions: BrowserSessionService
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

    async def run(self, op: str, args: dict[str, str]) -> Run:
        run = await self.assistant.execute(OWNER, self.sid, self.release_id, op, args, secrets.token_hex(6))
        return await self.runs.wait(run.run_id, 40)

    async def value(self, region: str, label: str = "Müşteri No") -> str:
        return str(await self.page.get_by_role("region", name=region).get_by_label(label).input_value())


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="2500")
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), SessionLimits(4, 2, 600))
    repo = LocalFileRunRepository(tmp_path / "runs")
    executor = Executor(
        repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)
    )
    runs = RunService(repo, sessions, executor, LAB_ACTION_SET, 100)
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    release = None
    for d in (
        build_draft("kefil_musteri_no", PARTIES_SCREEN, [("kefil_no", GUARANTOR_NO, "{no}")], ["no"]),
        build_draft(
            "taraf_numaralari",
            PARTIES_SCREEN,
            [("basvuran_no", APPLICANT_NO, "{a}"), ("kefil_no", GUARANTOR_NO, "{b}")],
            ["a", "b"],
        ),
        build_draft("adres_yaz", FRAMES_SCREEN, [("adres", ADDRESS, "{adres}")], ["adres"]),
    ):
        drafts.create(d)
        d = publishing.approve("pub", d.draft_id, d.revision)
        release = await publishing.publish("pub", d.draft_id, f"req-{d.operation_id}")
    assert release is not None
    view = await sessions.open(OWNER)
    e = Env(
        AssistantService(publishing, runs, LAB_ACTION_SET, UnavailableLLM("kapalı"), 2000, 200, 1, "lab"),
        runs,
        sessions,
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


def assert_refused(run: Run, env: Env, status: RunStatus = RunStatus.FAILED) -> dict[str, Any]:
    assert run.status is status, run.model_dump()
    failed = next(s for s in run.steps if s.state is StepState.KNOWN_FAILED)
    assert failed.error_class == "SCREEN_NOT_RECOGNIZED" and "İşlem yapılmadı" in (failed.message or "")
    assert env.writes == [], env.writes  # hiçbir sürücü yazması/tıklaması yok
    screen: dict[str, Any] = failed.result["screen"]
    return screen


async def test_correct_screen_recognized_at_unrelated_url(env: Env) -> None:
    await env.goto(f"/cases/C-{secrets.token_hex(3)}/parties")  # sabit lab adresi değil
    run = await env.run("kefil_musteri_no", {"no": "00456"})
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.steps[0].command["op"] == "assert_screen"
    assert run.steps[0].result["screen_status"] == "recognized"
    assert run.steps[1].result["screen_reverified"] == "basvuru_taraflar"  # eylemden önce yeniden doğrulandı
    assert await env.value("Kefil") == "00456" and await env.value("Başvuran") == ""


async def test_similar_wrong_screen_refused_although_target_exists(env: Env) -> None:
    env.lab.set_scenario(party_layout="similar")
    await env.goto("/pages/duplicates")  # tanıdık adres, farklı ekran
    assert await env.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").count() == 1
    screen = assert_refused(await env.run("kefil_musteri_no", {"no": "00456"}), env)
    assert screen["status"] == "not_recognized" and "Talep Notu" in screen["explanation"]
    assert await env.value("Kefil") == ""


async def test_duplicated_region_is_ambiguous_and_untouched(env: Env) -> None:
    env.lab.set_scenario(party_layout="duplicate_guarantor")
    await env.goto("/pages/duplicates")
    run = await env.run("kefil_musteri_no", {"no": "00456"})
    screen = assert_refused(run, env, RunStatus.PAUSED_AMBIGUOUS)
    assert screen["status"] == "ambiguous"
    values = (
        await env.page.get_by_role("region", name="Kefil")
        .get_by_label("Müşteri No")
        .evaluate_all("els => els.map(e => e.value)")
    )
    assert values == ["", ""]


@pytest.mark.parametrize("switch", ["dom", "navigate"])
async def test_screen_change_before_next_action_stops_without_writing(env: Env, switch: str) -> None:
    env.lab.set_scenario(party_switch=switch)
    await env.goto("/pages/duplicates")
    run = await env.run("taraf_numaralari", {"a": "111", "b": "222"})
    assert run.status is RunStatus.FAILED, run.model_dump()
    failed = next(s for s in run.steps if s.state is StepState.KNOWN_FAILED)
    assert failed.error_class == "SCREEN_NOT_RECOGNIZED" and (failed.message or "").startswith(
        "Ekran değişti"
    )
    if switch == "dom":  # SPA içi değişim: yazma tamamlandı, sonraki adımdan önce ekran yeniden doğrulandı
        assert run.steps[1].state is StepState.SUCCEEDED and failed.index == 2
    elif failed.index == 1:  # gezinme yazmanın doğrulamasını bozdu; tekrar denemeden önce ekran reddetti
        assert "FRAME_CHANGED" in failed.recoveries
    else:  # gezinme doğrulamadan sonra tamamlandı (Firefox'ta görülür): sonraki adım durur
        assert run.steps[1].state is StepState.SUCCEEDED and failed.index == 2
    # Kefil adımına hiç gelinmedi: Başvuran'a tek yazma dışında sürücü eylemi yok.
    assert [w[0] for w in env.writes] == ["fill"]
    assert all(s.state is StepState.PENDING for s in run.steps[failed.index + 1 :])
    await env.page.wait_for_load_state()
    assert await env.page.get_by_role("heading", name="Kefil değişiklik talebi").count() == 1
    assert await env.value("Kefil") == ""


async def test_nested_and_late_frames_wait_for_evidence(env: Env) -> None:
    env.lab.set_scenario(late_frame_delay_ms=1200)  # işaret frame'i geç gelir; okuma timeout'undan kısa
    await env.goto("/pages/frames")
    run = await env.run("adres_yaz", {"adres": "Deney Sk. 1"})
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    nested = env.page.frame_locator("iframe[title='Vaka Ayrıntıları']").frame_locator(
        "iframe[title='Adres Bilgileri']"
    )
    assert await nested.get_by_label("Adres").input_value() == "Deney Sk. 1"


async def test_missing_late_frame_evidence_stops_before_nested_write(env: Env) -> None:
    env.lab.set_scenario(late_frame_delay_ms=20_000)  # kanıt süre içinde gelmez
    await env.goto("/pages/frames")
    screen = assert_refused(await env.run("adres_yaz", {"adres": "Deney Sk. 1"}), env)
    assert screen["status"] in {"not_recognized", "incomplete"}
    nested = env.page.frame_locator("iframe[title='Vaka Ayrıntıları']").frame_locator(
        "iframe[title='Adres Bilgileri']"
    )
    assert await nested.get_by_label("Adres").input_value() == ""


async def test_incomplete_scan_is_not_treated_as_recognized(env: Env, outsider: HitCounterServer) -> None:
    await env.goto("/pages/duplicates")
    async with env.page.expect_event("frameattached"):
        await env.page.evaluate(
            "o => { const f = document.createElement('iframe'); f.src = o; document.body.appendChild(f); }",
            outsider.origin,
        )
    await env.page.wait_for_timeout(300)
    screen = assert_refused(await env.run("kefil_musteri_no", {"no": "00456"}), env)
    assert screen["status"] == "incomplete"
    assert await env.value("Kefil") == ""
