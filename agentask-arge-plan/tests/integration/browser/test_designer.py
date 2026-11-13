"""Katalog Tasarımcısı akışı — gerçek Chromium + deney uygulaması, modelsiz (docs/04)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.errors import (
    CandidateStale,
    DraftNotReady,
    EffectNotAcknowledged,
    PlanInvalid,
    TargetNotUnique,
)
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.designer import DesignerService
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.observation import ObservationService
from agentask.application.services.runs import RunService
from agentask.domain.catalog import StepStatus
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"


@dataclass
class Env:
    designer: DesignerService
    sessions: BrowserSessionService
    sid: str
    lab: LabServer
    tmp: Path

    async def goto(self, path: str) -> None:
        await self.sessions.peek(OWNER, self.sid).navigate(
            f"{self.lab.primary}/__lab/autologin?user=ayse&next={path}"
        )

    def entry(self, path: str) -> str:
        return f"{self.lab.primary}/__lab/autologin?user=ayse&next={path}"


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    settings = lab_settings(
        make_env_file,
        lab,
        READINESS_TIMEOUT_MS="3000",
        OUTCOME_TIMEOUT_MS="3000",
        RECONCILE_TIMEOUT_MS="3000",
        BROWSER_MAX_SESSIONS_PER_USER="2",
    )
    factory = PlaywrightContextFactory(settings)
    sessions = BrowserSessionService(factory, SessionLimits(max_sessions=4, max_per_user=2, idle_seconds=600))
    run_repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(
        run_repo,
        sessions,
        Executor(run_repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)),
        LAB_ACTION_SET,
        100,
    )
    designer = DesignerService(
        LocalFileDraftRepository(tmp_path / "drafts"),
        sessions,
        ObservationService(sessions, 5000),
        runs,
        LAB_ACTION_SET,
        run_timeout_s=30,
    )
    view = await sessions.open(OWNER)
    lab.reset()
    yield Env(designer, sessions, view.session_id, lab, tmp_path)
    await runs.shutdown()
    await sessions.shutdown()


async def prepare_step(env: Env, draft: Any, step_id: str, label_hint: str | None = None) -> Any:
    proposal = await env.designer.propose_targets(OWNER, draft.draft_id, step_id, env.sid)
    return proposal


async def test_guided_authoring_end_to_end_without_json(env: Env) -> None:
    d = env.designer.create_draft(
        OWNER,
        application_id="lab",
        operation_id="kefil_musteri_no",
        title="Kefil müşteri numarasını gir",
        description="Deney",
        intent_phrases=["kefil müşteri numarası gir"],
    )
    d = env.designer.add_parameter(
        OWNER,
        d.draft_id,
        d.revision,
        name="musteri_no",
        title="Müşteri No",
        max_length=20,
        source="user_input",
    )
    d, step = env.designer.add_step(OWNER, d.draft_id, d.revision, "Kefil müşteri numarasını yaz")
    assert step.op == "ensure_value" and step.provenance["op"] == "rule_generated"

    await env.goto("/pages/duplicates")
    proposal = await env.designer.propose_targets(OWNER, d.draft_id, step.step_id, env.sid)
    top = proposal["candidates"][0]
    assert top["label"] == "Müşteri No" and top["contexts"][0]["name"] == "Kefil"
    assert any(
        c["contexts"][0]["name"] == "Başvuran" for c in proposal["candidates"]
    )  # alternatif de gösterilir

    d = env.designer.get(OWNER, d.draft_id)
    d = await env.designer.select_target(
        OWNER,
        d.draft_id,
        d.revision,
        step.step_id,
        env.sid,
        top["candidate_id"],
        element_id="kefil_musteri_no",
        meaning="Kefil müşteri numarası",
    )
    s = d.step(step.step_id)
    assert s.status is StepStatus.TARGET_SELECTED and s.element_id == "kefil_musteri_no"
    stored_target = d.elements["kefil_musteri_no"].target.model_dump(exclude_none=True)
    assert stored_target["region"] == "Kefil" and "candidate" not in str(stored_target)
    d = env.designer.configure_step(
        OWNER, d.draft_id, d.revision, step.step_id, value_template="{musteri_no}"
    )
    assert d.step(step.step_id).standard_text == "'Kefil müşteri numarası' alanına {musteri_no} değerini yaz"

    d = env.designer.confirm_step(
        OWNER, d.draft_id, d.revision, step.step_id, meaning=True, target=True, effect=True, params=True
    )
    d = await env.designer.trial_step(
        OWNER, d.draft_id, d.revision, step.step_id, env.sid, {"musteri_no": "00123"}
    )
    s = d.step(step.step_id)
    assert s.status is StepStatus.OBSERVED and s.trial is not None and s.trial.verified
    d = env.designer.confirm_outcome(OWNER, d.draft_id, d.revision, step.step_id)
    assert d.step(step.step_id).status is StepStatus.READY_FOR_REVIEW
    assert "fresh_session_test_missing" in env.designer.validate(OWNER, d.draft_id)
    assert "screen_missing" in env.designer.validate(OWNER, d.draft_id)
    with pytest.raises(DraftNotReady):  # ekran tanımı olmadan yeni oturum testi yapılmaz
        await env.designer.fresh_session_test(
            OWNER, d.draft_id, d.revision, {"musteri_no": "1"}, env.entry("/pages/duplicates")
        )

    # Ekran tanımı: güncel gözlemden işaretler; işlemin kendi hedefi tek başına işaret olamaz.
    snap = await env.designer.observation.observe(OWNER, env.sid)

    def cid(label: str, region: str) -> str:
        return next(
            c.candidate_id
            for c in snap.controls
            if c.label == label and any(x.name == region for x in c.contexts)
        )

    with pytest.raises(PlanInvalid) as only_target:
        await env.designer.define_screen(
            OWNER,
            d.draft_id,
            d.revision,
            env.sid,
            screen_id="basvuru_taraflar",
            title="Başvuru — taraf bilgileri",
            marker_candidate_ids=[cid("Müşteri No", "Kefil")],
        )
    assert only_target.value.details["reason"] == "screen_markers_only_targets"
    snap = await env.designer.observation.observe(OWNER, env.sid)  # doğrulama yeniden gözlemledi
    d, verdict = await env.designer.define_screen(
        OWNER,
        d.draft_id,
        d.revision,
        env.sid,
        screen_id="basvuru_taraflar",
        title="Başvuru — taraf bilgileri",
        marker_candidate_ids=[cid("Müşteri No", "Başvuran"), cid("Ad Soyad", "Kefil")],
        absent_markers=[{"kind": "textbox", "labels": ["Talep Notu"], "region": "Kefil"}],
    )
    assert verdict["recognized"] is True and d.screen is not None
    assert [r.name for r in d.screen.regions] == ["Başvuran", "Kefil"]
    stored = d.screen.model_dump_json()
    assert snap.revision not in stored and cid("Ad Soyad", "Kefil") not in stored  # aday kimliği saklanmaz
    assert (await env.designer.verify_screen(OWNER, d.draft_id, env.sid))["status"] == "recognized"

    d = await env.designer.fresh_session_test(
        OWNER, d.draft_id, d.revision, {"musteri_no": "00999"}, env.entry("/pages/duplicates")
    )
    assert d.fresh_test is not None and d.fresh_test.passed
    assert env.designer.validate(OWNER, d.draft_id) == []
    assert "00123" not in (env.tmp / "drafts").joinpath(f"{d.draft_id}.json").read_text(encoding="utf-8")

    d = env.designer.update_meta(OWNER, d.draft_id, d.revision, title="Kefil müşteri no (güncel)")
    assert "fresh_session_test_stale" in env.designer.validate(OWNER, d.draft_id)


async def test_ambiguous_target_cannot_be_confirmed(env: Env) -> None:
    d = env.designer.create_draft(OWNER, application_id="lab", operation_id="amb", title="A", description="")
    d, step = env.designer.add_step(OWNER, d.draft_id, d.revision, "Müşteri no yaz")
    await env.goto("/pages/duplicates")
    proposal = await env.designer.propose_targets(OWNER, d.draft_id, step.step_id, env.sid)
    applicant = next(c for c in proposal["candidates"] if c["contexts"][0]["name"] == "Başvuran")
    d = env.designer.get(OWNER, d.draft_id)
    # Bölge bağlamı olmadan türetilen tanım tekil değildir → seçim reddedilir
    with pytest.raises(TargetNotUnique):
        await env.designer.select_target(
            OWNER,
            d.draft_id,
            d.revision,
            step.step_id,
            env.sid,
            applicant["candidate_id"],
            element_id="musteri_no",
            meaning="Müşteri no",
            include_region=False,
        )
    proposal = await env.designer.propose_targets(OWNER, d.draft_id, step.step_id, env.sid)
    d = env.designer.get(OWNER, d.draft_id)
    stale_id = proposal["candidates"][0]["candidate_id"]
    await env.goto("/pages/duplicates")
    with pytest.raises(CandidateStale):
        await env.designer.select_target(
            OWNER,
            d.draft_id,
            d.revision,
            step.step_id,
            env.sid,
            stale_id,
            element_id="musteri_no",
            meaning="Müşteri no",
        )


async def test_picker_selection_and_mutating_trial_requires_ack(env: Env) -> None:
    d = env.designer.create_draft(
        OWNER, application_id="lab", operation_id="vaka_notu", title="Vakaya not ekle", description=""
    )
    d = env.designer.add_parameter(
        OWNER, d.draft_id, d.revision, name="metin", title="Not", max_length=200, source="user_input"
    )
    d, s1 = env.designer.add_step(OWNER, d.draft_id, d.revision, "Notu yaz")
    d, s2 = env.designer.add_step(OWNER, d.draft_id, d.revision, "Notu kaydet")
    assert s2.op == "invoke_approved_action"
    await env.goto("/pages/note-form")
    # manuel seçim: picker ile işaretlenen alan aday olarak kullanılır (sayfaya olay gitmez)
    observation = env.designer.observation
    await observation.start_picker(OWNER, env.sid)
    page = env.sessions.peek(OWNER, env.sid).page  # type: ignore[attr-defined]
    box = await page.get_by_label("Not", exact=True).bounding_box()
    await page.mouse.click(box["x"] + 5, box["y"] + 5)
    pick = await observation.wait_pick(OWNER, env.sid, 3000)
    await observation.stop_picker(OWNER, env.sid)
    assert pick is not None and pick.candidate_id
    d = await env.designer.select_target(
        OWNER,
        d.draft_id,
        d.revision,
        s1.step_id,
        env.sid,
        pick.candidate_id,
        element_id="not_alani",
        meaning="Vaka notu",
        provenance="human_verified",
    )
    d = env.designer.configure_step(
        OWNER, d.draft_id, d.revision, s1.step_id, value_template="{metin}", success_check="none"
    )
    d = env.designer.configure_step(
        OWNER,
        d.draft_id,
        d.revision,
        s2.step_id,
        action_id="lab.add_case_note",
        action_params={"text": "{metin}"},
    )
    for step_id in (s1.step_id, s2.step_id):
        d = env.designer.confirm_step(
            OWNER, d.draft_id, d.revision, step_id, meaning=True, target=True, effect=True, params=True
        )
    d = await env.designer.trial_step(
        OWNER, d.draft_id, d.revision, s1.step_id, env.sid, {"metin": "Deneme notu"}
    )
    with pytest.raises(EffectNotAcknowledged):
        await env.designer.trial_step(
            OWNER, d.draft_id, d.revision, s2.step_id, env.sid, {"metin": "Deneme notu"}
        )
    d = await env.designer.trial_step(
        OWNER, d.draft_id, d.revision, s2.step_id, env.sid, {"metin": "Deneme notu"}, acknowledge_effect=True
    )
    assert d.step(s2.step_id).trial.verified  # type: ignore[union-attr]
    assert [c["text"] for c in env.lab.control("GET", "/__lab/state").json()["commits"]] == ["Deneme notu"]


async def test_transition_saved_before_screens_and_prior_output_trial(env: Env) -> None:
    """C (yeni tasarımcı sırası): geçiş, hedef ekran tanıtılmadan kaydedilir (eksiklik olarak kalır);
    hedef ekran sonra tanıtılınca ek ekran olur. Önceki okuma çıktısına bağlı adımın denemesi kaynak okumayı
    da çalıştırır; değer gerçek okumadan gelir."""
    d = env.designer.create_draft(
        OWNER, application_id="lab", operation_id="vaka_kopyala", title="Vaka kopyala", description=""
    )
    await env.goto("/wizard/C-41")
    snap = await env.designer.observation.observe(OWNER, env.sid)

    def cid(label: str, region: str | None = None) -> str:
        return next(
            c.candidate_id
            for c in snap.controls
            if (c.label or c.accessible_name) == label
            and (region is None or any(x.name == region for x in c.contexts))
        )

    d, read = env.designer.add_step(OWNER, d.draft_id, d.revision, "Vaka numarasını oku")
    d = await env.designer.select_target(
        OWNER,
        d.draft_id,
        d.revision,
        read.step_id,
        env.sid,
        cid("Vaka No", "Vaka"),
        element_id="vaka_no",
        meaning="Vaka numarası",
    )
    d = env.designer.configure_step(OWNER, d.draft_id, d.revision, read.step_id, op="read")
    d = env.designer.add_parameter(
        OWNER,
        d.draft_id,
        d.revision,
        name="okunan_vaka",
        title="Okunan vaka no",
        max_length=20,
        source="prior_output",
        prior_step=0,
    )
    d, write = env.designer.add_step(OWNER, d.draft_id, d.revision, "Müşteri numarasına yaz")
    snap = await env.designer.observation.observe(OWNER, env.sid)
    d = await env.designer.select_target(
        OWNER,
        d.draft_id,
        d.revision,
        write.step_id,
        env.sid,
        cid("Müşteri No", "Müşteri"),
        element_id="musteri_no",
        meaning="Müşteri numarası",
    )
    d = env.designer.configure_step(
        OWNER, d.draft_id, d.revision, write.step_id, op="ensure_value", value_template="{okunan_vaka}"
    )
    snap = await env.designer.observation.observe(OWNER, env.sid)
    d = await env.designer.define_transition(
        OWNER,
        d.draft_id,
        d.revision,
        transition_id="teminata_gec",
        from_screen="ekran_1",
        to_screen="teminat",
        trigger_kind="control",
        session_id=env.sid,
        trigger_candidate_id=cid("Devam"),
    )
    assert "screen_missing" in env.designer.validate(OWNER, d.draft_id)
    d, go = env.designer.add_step(OWNER, d.draft_id, d.revision, "Teminat ekranına geç")
    d = env.designer.configure_step(
        OWNER, d.draft_id, d.revision, go.step_id, op="follow_transition", transition_id="teminata_gec"
    )
    snap = await env.designer.observation.observe(OWNER, env.sid)
    d, _ = await env.designer.define_screen(
        OWNER,
        d.draft_id,
        d.revision,
        env.sid,
        screen_id="ekran_1",
        title="Müşteri seçimi",
        marker_candidate_ids=[cid("Devam")],
    )
    assert d.screen is not None and d.screen.screen_id == "ekran_1"
    assert "transition_unknown_screen:teminata_gec:teminat" in env.designer.validate(OWNER, d.draft_id)

    # Önceki çıktıya bağlı adımın denemesi: kaynak okuma da çalışır, alan gerçekten okunan değeri alır.
    d = env.designer.confirm_step(
        OWNER, d.draft_id, d.revision, write.step_id, meaning=True, target=True, effect=True, params=True
    )
    d = await env.designer.trial_step(OWNER, d.draft_id, d.revision, write.step_id, env.sid, {})
    assert d.step(write.step_id).trial is not None and d.step(write.step_id).trial.verified  # type: ignore[union-attr]
    page = env.sessions.peek(OWNER, env.sid).page  # type: ignore[attr-defined]
    assert await page.get_by_role("region", name="Müşteri").get_by_label("Müşteri No").input_value() == "C-41"

    # Analist düğmeye kendisi basar (sistem tasarımda tıklamaz); hedef ekran tanıtılınca ek ekran olur.
    await page.get_by_role("button", name="Devam").click()
    await page.wait_for_url("**/collateral")
    snap = await env.designer.observation.observe(OWNER, env.sid)
    d, verdict = await env.designer.define_screen(
        OWNER,
        d.draft_id,
        d.revision,
        env.sid,
        screen_id="teminat",
        title="Teminat bilgileri",
        marker_candidate_ids=[cid("Gönder", "Teminat")],
    )
    assert verdict["recognized"] is True
    assert d.screen.screen_id == "ekran_1" and [s.screen_id for s in d.extra_screens] == ["teminat"]
    issues = env.designer.validate(OWNER, d.draft_id)
    assert not [i for i in issues if i.startswith("transition_unknown_screen")], issues
    assert d.route()[go.step_id] == "ekran_1"


async def test_fresh_test_without_login_explains_cause(env: Env) -> None:
    """Manuel kabuldeki hata: yeni oturum girişsiz açılır; başlangıç adresi giriş istiyorsa test başlangıç
    ekranında SESSION_EXPIRED ile durur, değer yazılmaz. Neden ve sonraki adım açıklanır; test gevşetilmez."""
    d = env.designer.create_draft(
        OWNER, application_id="lab", operation_id="kefil_no_giris", title="Kefil no", description=""
    )
    d = env.designer.add_parameter(
        OWNER, d.draft_id, d.revision, name="no", title="No", max_length=20, source="user_input"
    )
    d, step = env.designer.add_step(OWNER, d.draft_id, d.revision, "Kefil müşteri numarasını yaz")
    await env.goto("/pages/duplicates")
    snap = await env.designer.observation.observe(OWNER, env.sid)

    def cid(label: str, region: str) -> str:
        return next(
            c.candidate_id
            for c in snap.controls
            if c.label == label and any(x.name == region for x in c.contexts)
        )

    d = await env.designer.select_target(
        OWNER,
        d.draft_id,
        d.revision,
        step.step_id,
        env.sid,
        cid("Müşteri No", "Kefil"),
        element_id="kefil_no",
        meaning="Kefil numarası",
    )
    d = env.designer.configure_step(OWNER, d.draft_id, d.revision, step.step_id, value_template="{no}")
    snap = await env.designer.observation.observe(OWNER, env.sid)
    d, _ = await env.designer.define_screen(
        OWNER,
        d.draft_id,
        d.revision,
        env.sid,
        screen_id="taraflar",
        title="Taraflar",
        marker_candidate_ids=[cid("Ad Soyad", "Kefil")],
    )
    d = env.designer.confirm_step(
        OWNER, d.draft_id, d.revision, step.step_id, meaning=True, target=True, effect=True, params=True
    )
    d = await env.designer.trial_step(OWNER, d.draft_id, d.revision, step.step_id, env.sid, {"no": "00789"})
    d = env.designer.confirm_outcome(OWNER, d.draft_id, d.revision, step.step_id)
    # Uygulamanın kök adresi (girişsiz): yeni oturum giriş ekranına düşer.
    d = await env.designer.fresh_session_test(
        OWNER, d.draft_id, d.revision, {"no": "00789"}, f"{env.lab.primary}/pages/duplicates"
    )
    assert d.fresh_test is not None and not d.fresh_test.passed
    assert "fresh_session_test_failed" in env.designer.validate(OWNER, d.draft_id)
    failure = env.designer.fresh_test_failure(d)
    assert failure is not None and failure["code"] == "SESSION_EXPIRED" and failure["stage"] == "giriş"
    assert failure["step"] == 1 and failure["op"] == "assert_screen"  # başlangıç ekranında, yazmadan önce
    run = env.designer._runs.get(OWNER, d.fresh_test.run_id)
    assert all(s.state.value != "succeeded" for s in run.steps if s.command["op"] == "ensure_value")
    # Girişi de yapan başlangıç adresiyle aynı test geçer.
    d = await env.designer.fresh_session_test(
        OWNER, d.draft_id, d.revision, {"no": "00789"}, env.entry("/pages/duplicates")
    )
    assert d.fresh_test is not None and d.fresh_test.passed
    assert env.designer.fresh_test_failure(d) is None
