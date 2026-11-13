"""İşlem Asistanı: kural yolu (LLM kapalı), model önerisi doğrulama, yayına pinlenmiş run — gerçek
Chromium + lab."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.errors import EffectNotAcknowledged, PlanInvalid, ReleaseSuperseded
from agentask.application.ports.llm import LLMAvailability, LLMUnavailableError
from agentask.application.services.assistant import AssistantService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.domain.catalog import OperationDraft, ParameterDef
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.fake_catalog_store import FakeCatalogStore
from tests.integration.browser.helpers import lab_settings
from tests.screens import NOTE_SCREEN
from tests.support_lab import LabServer
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.browser
OWNER = "ayse"


class ScriptedLLM:
    """Test ikamesi: önceden belirlenmiş yanıt döndürür; çağrıları sayar."""

    def __init__(self, answer: Any) -> None:
        self.answer, self.calls, self.last_user = answer, 0, ""

    def availability(self) -> LLMAvailability:
        return LLMAvailability(True, "scripted")

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> Any:
        self.calls += 1
        self.last_user = user
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@dataclass
class Env:
    assistant: AssistantService
    publishing: PublishService
    drafts: LocalFileDraftRepository
    sessions: BrowserSessionService
    runs: RunService
    sid: str
    lab: LabServer

    async def goto(self, path: str) -> None:
        await self.sessions.peek(OWNER, self.sid).navigate(
            f"{self.lab.primary}/__lab/autologin?user=ayse&next={path}"
        )

    def with_llm(self, llm: Any) -> AssistantService:
        return AssistantService(
            self.publishing,
            self.runs,
            LAB_ACTION_SET,
            llm,
            max_input_tokens=2000,
            max_output_tokens=200,
            max_calls=2,
            application_id="lab",
        )


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    settings = lab_settings(make_env_file, lab)
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), SessionLimits(4, 2, 600))
    run_repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(
        run_repo,
        sessions,
        Executor(run_repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)),
        LAB_ACTION_SET,
        100,
    )
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_musteri_no", "Kefil müşteri numarasını gir")
    d.intent_phrases = ["kefil müşteri numarası gir"]
    d.record_fresh_test(run_id="run-fresh0001", passed=True)
    drafts.update(d, d.revision)
    d = publishing.approve("pub", d.draft_id, d.revision)
    await publishing.publish("pub", d.draft_id, "rel-req-1")
    view = await sessions.open(OWNER)
    lab.reset()
    e = Env(
        AssistantService(publishing, runs, LAB_ACTION_SET, UnavailableLLM("disabled"), 2000, 200, 2, "lab"),
        publishing,
        drafts,
        sessions,
        runs,
        view.session_id,
        lab,
    )
    yield e
    await runs.shutdown()
    await sessions.shutdown()


async def test_run_pinned_to_release(env: Env) -> None:
    interp = await env.assistant.interpret(OWNER, "Kefil müşteri numarasını gir")
    assert interp.operation_id == "kefil_musteri_no" and interp.missing == ["no"]
    preview = await env.assistant.preview(OWNER, interp.release_id, "kefil_musteri_no", {"no": "00123"})
    assert [s["op"] for s in preview["commands"]] == ["assert_screen", "ensure_value", "assert_condition"]
    await env.goto("/pages/duplicates")
    run = await env.assistant.execute(
        OWNER, env.sid, interp.release_id, "kefil_musteri_no", {"no": "00123"}, "a-1"
    )
    run = await env.runs.wait(run.run_id, 30)
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.binding is not None and run.binding["release_id"] == interp.release_id
    old_release = interp.release_id

    d = next(x for x in env.drafts.list_all() if x.operation_id == "kefil_musteri_no")
    d.description = "yeni sürüm"
    d.record_fresh_test(run_id="run-fresh0002", passed=True)
    env.drafts.update(d, d.revision)
    d = env.publishing.approve("pub", d.draft_id, d.revision)
    new = await env.publishing.publish("pub", d.draft_id, "rel-req-2")
    stored = env.runs.get(OWNER, run.run_id)
    assert stored.binding is not None and stored.binding["release_id"] == old_release  # eski run eski yayında
    with pytest.raises(ReleaseSuperseded):
        await env.assistant.execute(OWNER, env.sid, old_release, "kefil_musteri_no", {"no": "1"}, "a-2")
    again = await env.assistant.interpret(OWNER, "Kefil müşteri numarasını gir")
    assert again.release_id == new.release_id


async def test_mutating_operation_requires_acknowledgement(env: Env) -> None:
    from agentask.domain.catalog import Confirmation, OperationDraft, ParameterDef, StepStatus

    d = OperationDraft.new(
        created_by="ayse",
        application_id="lab",
        operation_id="vaka_notu",
        title="Vakaya not ekle",
        description="",
    )
    d.intent_phrases = ["vakaya not ekle"]
    d.parameters.append(ParameterDef(name="metin", title="Not", max_length=200, source="user_input"))
    d.add_element("not_alani", "Not", {"kind": "textbox", "labels": ["Not"]}, "observed")
    d.screen = NOTE_SCREEN
    s1, s2 = d.add_step("yaz"), d.add_step("kaydet")
    s1.op, s1.element_id, s1.value_template, s1.success_check = "ensure_value", "not_alani", "{metin}", "none"
    s2.op, s2.action_id, s2.action_params = "invoke_approved_action", "lab.add_case_note", {"text": "{metin}"}
    for s in (s1, s2):
        s.move(StepStatus.TARGET_SELECTED)
        s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")
        for st in (
            StepStatus.MEANING_AND_TARGET_CONFIRMED,
            StepStatus.TRIAL_REQUESTED,
            StepStatus.OBSERVED,
            StepStatus.OUTCOME_CONFIRMED,
            StepStatus.READY_FOR_REVIEW,
        ):
            s.move(st)
    d.record_fresh_test(run_id="run-fresh0003", passed=True)
    env.drafts.create(d)
    d = env.publishing.approve("pub", d.draft_id, d.revision)
    await env.publishing.publish("pub", d.draft_id, "rel-req-note")
    interp = await env.assistant.interpret(OWNER, "Vakaya not ekle: 'Müşteri arandı'")
    assert interp.status == "matched" and interp.arguments == {"metin": "Müşteri arandı"}
    preview = await env.assistant.preview(OWNER, interp.release_id, "vaka_notu", interp.arguments)
    assert preview["effect"] == "mutating"
    await env.goto("/pages/note-form")
    with pytest.raises(EffectNotAcknowledged):
        await env.assistant.execute(OWNER, env.sid, interp.release_id, "vaka_notu", interp.arguments, "n-1")
    run = await env.assistant.execute(
        OWNER, env.sid, interp.release_id, "vaka_notu", interp.arguments, "n-1", acknowledge_effect=True
    )
    run = await env.runs.wait(run.run_id, 30)
    assert run.status is RunStatus.COMPLETED
    assert [c["text"] for c in env.lab.control("GET", "/__lab/state").json()["commits"]] == ["Müşteri arandı"]


async def test_model_suggestion_validated_and_never_auto_executed(env: Env) -> None:
    llm = ScriptedLLM({"operation_id": "kefil_musteri_no", "arguments": {"no": "007"}})
    result = await env.with_llm(llm).interpret(OWNER, "şunu halledebilir misin", use_model=True)
    assert result.provenance == "model_suggested" and result.status == "needs_clarification"
    # Model talepte geçmeyen değeri uydurdu → düşürülür ve kullanıcıya sorulur.
    assert result.operation_id == "kefil_musteri_no" and result.arguments == {} and result.missing == ["no"]
    assert "şunu halledebilir misin" in llm.last_user and "kefil_musteri_no" in llm.last_user
    grounded = await env.with_llm(llm).interpret(OWNER, "şunu 007 için halledebilir misin", use_model=True)
    assert grounded.arguments == {"no": "007"} and grounded.status == "needs_clarification"
    assert "<" not in llm.last_user  # DOM/HTML gönderilmez

    bad = ScriptedLLM({"operation_id": "drop_everything", "arguments": {}})
    rejected = await env.with_llm(bad).interpret(OWNER, "şunu halledebilir misin", use_model=True)
    assert rejected.operation_id is None and "model_output_rejected" in rejected.explanation


async def test_llm_unavailable_falls_back_to_rules_without_external_model(env: Env) -> None:
    down = ScriptedLLM(LLMUnavailableError("timeout"))
    r = await env.with_llm(down).interpret(OWNER, "Kefil müşteri numarasını gir", use_model=True)
    assert r.operation_id == "kefil_musteri_no" and down.calls == 0  # kural eşleşmesi varken model çağrılmaz
    r2 = await env.with_llm(down).interpret(OWNER, "belirsiz bir istek", use_model=True)
    assert r2.status == "no_match" and "llm_unavailable" in r2.explanation and down.calls == 1


async def test_token_budget_prevents_model_call(env: Env) -> None:
    llm = ScriptedLLM({"operation_id": "kefil_musteri_no", "arguments": {}})
    tiny = AssistantService(
        env.publishing,
        env.runs,
        LAB_ACTION_SET,
        llm,
        max_input_tokens=10,
        max_output_tokens=50,
        max_calls=2,
        application_id="lab",
    )
    r = await tiny.interpret(OWNER, "çok uzun ve belirsiz bir istek " * 5, use_model=True)
    assert llm.calls == 0 and "budget_exceeded" in r.explanation


APPLICANT = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Başvuran"}


async def _publish_variant(
    env: Env, op_id: str, title: str, target: dict[str, Any], screen: Any, req: str
) -> None:
    from tests.unit.test_component_publishing import make_ready

    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id=op_id, title=title, description=""
    )
    d.parameters.append(ParameterDef(name="no", title="No", max_length=20, source="user_input"))
    d.add_element("hedef", "Hedef", target, "observed")
    s = d.add_step("yaz")
    s.op, s.element_id, s.value_template = "ensure_value", "hedef", "{no}"
    d.screen = screen
    make_ready(d)
    env.drafts.create(d)
    d = env.publishing.approve("pub", d.draft_id, d.revision)
    await env.publishing.publish("pub", d.draft_id, req)


async def test_model_plan_from_published_operations_is_checked_then_run(env: Env) -> None:
    """F: model yalnız yayındaki işlemlerden sıralı plan önerir; kod doğrular; kullanıcı açıkça başlatır."""
    from tests.screens import PARTIES_SCREEN

    await _publish_variant(env, "basvuran_no", "Başvuran numarasını gir", APPLICANT, PARTIES_SCREEN, "r-b")
    prompt = "Kefil için 00123, başvuran için 00456 yaz"
    llm = ScriptedLLM(
        {
            "steps": [
                {"operation_id": "kefil_musteri_no", "arguments": {"no": "00123"}},
                {"operation_id": "basvuran_no", "arguments": {"no": "99999"}},  # talepte yok → atılır
            ]
        }
    )
    assistant = env.with_llm(llm)
    proposal = await assistant.propose_plan(OWNER, prompt)
    assert proposal["status"] == "proposed" and proposal["provenance"] == "model_suggested"
    assert [s["operation_id"] for s in proposal["steps"]] == ["kefil_musteri_no", "basvuran_no"]
    assert proposal["steps"][1]["arguments"] == {} and proposal["steps"][1]["missing"] == [
        {"name": "no", "title": "No"}
    ]
    user = json.loads(llm.last_user)
    assert {o["operation_id"] for o in user["islemler"]} == {"kefil_musteri_no", "basvuran_no"}
    assert llm.calls == 1  # öneri kendiliğinden çalışmaz; run yok
    assert env.runs.list_runs(OWNER) == []

    steps = [
        {"operation_id": "kefil_musteri_no", "arguments": {"no": "00123"}},
        {"operation_id": "basvuran_no", "arguments": {"no": "00456"}},
    ]
    preview = await assistant.plan_preview(OWNER, proposal["release_id"], steps)
    assert preview["effect"] == "ui_local" and len(preview["operations"]) == 2
    await env.goto("/pages/duplicates")
    run = await assistant.plan_execute(OWNER, env.sid, proposal["release_id"], steps, "plan-1")
    run = await env.runs.wait(run.run_id, 30)
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.binding is not None and run.binding["kind"] == "sequence"
    page = env.sessions.peek(OWNER, env.sid).page  # type: ignore[attr-defined]
    assert await page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value() == "00123"
    assert (
        await page.get_by_role("region", name="Başvuran").get_by_label("Müşteri No").input_value() == "00456"
    )


async def test_model_plan_rejections(env: Env) -> None:
    await _publish_variant(
        env, "not_alani", "Başka ekranda yaz", {"kind": "textbox", "labels": ["Not"]}, NOTE_SCREEN, "r-n"
    )
    # Bilinmeyen işlem: reddedilir (model listeyi genişletemez).
    bad = env.with_llm(ScriptedLLM({"steps": [{"operation_id": "drop_everything", "arguments": {}}]}))
    assert (await bad.propose_plan(OWNER, "her şeyi sil"))["status"] == "rejected"
    # Geçersiz ekran sırası: önerilir ama çalıştırılamaz; önizleme/yürütme de reddeder.
    order = env.with_llm(
        ScriptedLLM(
            {
                "steps": [
                    {"operation_id": "kefil_musteri_no", "arguments": {}},
                    {"operation_id": "not_alani", "arguments": {}},
                ]
            }
        )
    )
    proposal = await order.propose_plan(OWNER, "iki işlem")
    assert proposal["status"] == "rejected" and proposal["issues"][0].startswith("screen_order:2")
    with pytest.raises(PlanInvalid) as exc:
        await order.plan_preview(
            OWNER,
            proposal["release_id"],
            [
                {"operation_id": "kefil_musteri_no", "arguments": {"no": "1"}},
                {"operation_id": "not_alani", "arguments": {"no": "2"}},
            ],
        )
    assert exc.value.details["reason"] == "screen_order_invalid"
    # Model kapalı: çağrı yok, açık durum.
    down = ScriptedLLM(LLMUnavailableError("timeout"))
    assert (await env.with_llm(down).propose_plan(OWNER, "x"))["status"] == "model_unavailable"
    # Hassas talep: model çağrılmaz.
    spy = ScriptedLLM({"steps": []})
    out = await env.with_llm(spy).propose_plan(OWNER, "parolam Gizli-Parola-77! ile gir")
    assert out["status"] == "needs_clarification" and spy.calls == 0
