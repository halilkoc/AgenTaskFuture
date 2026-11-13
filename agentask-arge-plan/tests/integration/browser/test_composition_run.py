"""Gösterilmemiş birleşik görev: iki yayımlanmış işlem + koşul + sınırlı döngü, gerçek Chromium + lab."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.errors import PlanInvalid
from agentask.application.services.assistant import AssistantService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.domain.runtime import RunStatus, StepState
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.fake_catalog_store import FakeCatalogStore
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.browser
KEFIL = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}


async def build(make_env_file: EnvFileFactory, lab: LabServer, tmp: Path, enabled: bool):  # type: ignore[no-untyped-def]
    settings = lab_settings(make_env_file, lab)
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), SessionLimits(2, 1, 600))
    repo = LocalFileRunRepository(tmp / "runs")
    runs = RunService(
        repo,
        sessions,
        Executor(repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)),
        LAB_ACTION_SET,
        100,
        allow_composition=enabled,
    )
    drafts = LocalFileDraftRepository(tmp / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    for op_id, region in (("kefil_no", "Kefil"), ("basvuran_no", "Başvuran")):
        d = ready_draft(drafts, op_id, f"{region} no")
        d.elements["kefil_no"] = d.elements["kefil_no"].model_copy(
            update={"target": d.elements["kefil_no"].target.model_copy(update={"region": region})}
        )
        d.record_fresh_test(run_id=f"run-fresh-{op_id}", passed=True)
        drafts.update(d, d.revision)
        d = publishing.approve("pub", d.draft_id, d.revision)
        await publishing.publish("pub", d.draft_id, f"rel-{op_id}")
    assistant = AssistantService(
        publishing,
        runs,
        LAB_ACTION_SET,
        UnavailableLLM("disabled"),
        1000,
        100,
        1,
        "lab",
        composition_enabled=enabled,
        composition_max_depth=3,
        composition_max_items=5,
    )
    view = await sessions.open("ayse")
    await sessions.peek("ayse", view.session_id).navigate(
        f"{lab.primary}/__lab/autologin?user=a&next=/pages/duplicates"
    )
    return assistant, runs, sessions, view.session_id


PLAN = {
    "nodes": [
        {"kind": "call_operation", "operation_id": "kefil_no", "arguments": {"no": "111"}},
        {
            "kind": "if",
            "condition": {"type": "value_equals", "target": KEFIL, "value": "111"},
            "then": [{"kind": "call_operation", "operation_id": "basvuran_no", "arguments": {"no": "222"}}],
        },
        {
            "kind": "if",
            "condition": {"type": "value_equals", "target": KEFIL, "value": "999"},
            "then": [{"kind": "call_operation", "operation_id": "basvuran_no", "arguments": {"no": "999"}}],
        },
        {
            "kind": "for_each",
            "variable": "x",
            "items": ["301", "302"],
            "body": [{"kind": "call_operation", "operation_id": "kefil_no", "arguments": {"no": "{x}"}}],
        },
    ]
}


async def test_composite_task_runs_with_guards(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    lab.reset()
    assistant, runs, sessions, sid = await build(make_env_file, lab, tmp_path, enabled=True)
    try:
        preview = await assistant.composite_preview("ayse", PLAN)
        # Her işlem çağrısı ekran doğrulamasıyla başlar: (1+2) + (1+1+2) + (1+1+2) + 2×(1+2) = 17
        assert preview["steps"] == 17
        assert [c["op"] for c in preview["commands"]].count("assert_screen") == 5
        release_id = preview["release_id"]
        run = await assistant.composite_execute("ayse", sid, release_id, PLAN, "comp-1")
        run = await runs.wait(run.run_id, 40)
        assert run.status is RunStatus.COMPLETED, run.model_dump()
        states = [(s.command["op"], s.state) for s in run.steps]
        skipped = [i for i, (_, st) in enumerate(states) if st is StepState.SKIPPED]
        assert skipped == [8, 9, 10]  # 'Kefil == 999' koşulu sağlanmadı → dalı (ekran kontrolü dahil) atlandı
        assert run.steps[3].result["satisfied"] is True and run.steps[7].result["satisfied"] is False
        assert all(run.steps[i].result.get("screen_id") == "basvuru_taraflar" for i in (0, 4, 11, 14))
        page = sessions.peek("ayse", sid).page  # type: ignore[attr-defined]
        assert (
            await page.get_by_role("region", name="Başvuran").get_by_label("Müşteri No").input_value()
            == "222"
        )
        assert (
            await page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value() == "302"
        )
        assert run.binding is not None and run.binding["kind"] == "composite"
    finally:
        await runs.shutdown()
        await sessions.shutdown()


async def test_composition_disabled_is_rejected(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    assistant, runs, sessions, sid = await build(make_env_file, lab, tmp_path, enabled=False)
    try:
        with pytest.raises(PlanInvalid) as exc:
            await assistant.composite_preview("ayse", PLAN)
        assert exc.value.details["reason"] == "composition_disabled"
        with pytest.raises(PlanInvalid):
            await runs.create(
                "ayse",
                sid,
                "direct",
                [{"op": "evaluate_condition", "condition": PLAN["nodes"][1]["condition"]}],
            )
    finally:
        await runs.shutdown()
        await sessions.shutdown()
