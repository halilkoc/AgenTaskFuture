"""Değişiklik/etki analizi gerçek tarayıcıyla: dinamik id yok sayılır, etiket değişimi yakalanır, onarım
taslağı."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.impact import ImpactService
from agentask.application.services.observation import ObservationService
from agentask.application.services.publishing import PublishService
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.conftest import EnvFileFactory
from tests.fake_catalog_store import FakeCatalogStore
from tests.integration.browser.helpers import lab_settings
from tests.screens import PARTIES_SCREEN
from tests.support_lab import LabServer
from tests.unit.test_publishing import ready_draft

pytestmark = pytest.mark.browser


async def test_label_change_detected_and_repair_draft(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path
) -> None:
    lab.reset()
    sessions = BrowserSessionService(
        PlaywrightContextFactory(lab_settings(make_env_file, lab)), SessionLimits(2, 1, 600)
    )
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_no", "Kefil no")
    d = publishing.approve("pub", d.draft_id, d.revision)
    release = await publishing.publish("pub", d.draft_id, "r1")
    impact = ImpactService(publishing, ObservationService(sessions, 5000), drafts, "lab")
    view = await sessions.open("ayse")
    handle = sessions.peek("ayse", view.session_id)
    try:
        await handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/duplicates")
        first = await impact.analyze("ayse", view.session_id, "kefil_no")
        assert [e["status"] for e in first["elements"]] == ["unchanged"] and first["impacted"] == []
        assert first["screen"]["status"] == "recognized"  # Assistant ile aynı ekran çekirdeği
        await handle.navigate(f"{lab.primary}/pages/duplicates")  # yeni dinamik id'ler
        again = await impact.analyze("ayse", view.session_id, "kefil_no")
        assert [e["status"] for e in again["elements"]] == ["unchanged"]

        lab.set_scenario(guarantor_customer_label="Müşteri Numarası")
        await handle.navigate(f"{lab.primary}/pages/duplicates")
        changed = await impact.analyze("ayse", view.session_id, "kefil_no")
        [element] = changed["elements"]
        assert element["status"] == "not_found"
        assert [s["label"] for s in element["suggestions"]] == ["Müşteri Numarası"]
        assert [i["operation_id"] for i in changed["impacted"]] == ["kefil_no"]
        assert changed["impacted"][0]["regression_tests"] == ["fresh_session_test:kefil_no"]
        # Etiket değişimi ekran işaretlerini (Başvuran › Müşteri No, Kefil › Ad Soyad) bozmaz: ekran tanınır.
        assert changed["screen"]["status"] == "recognized"

        lab.set_scenario(guarantor_customer_label="Müşteri No", party_layout="similar")
        await handle.navigate(f"{lab.primary}/pages/duplicates")
        wrong = await impact.analyze("ayse", view.session_id, "kefil_no")
        assert wrong["screen"]["status"] == "not_recognized"  # eleman bulunsa da ekran yanlış
        assert [e["status"] for e in wrong["elements"]] == ["unchanged"]

        repair = await impact.repair("ayse", "kefil_no", ["kefil_no"])
        assert repair.draft_id != d.draft_id and repair.steps[0].element_id is None
        assert repair.approval is None and drafts.get(repair.draft_id) is not None
        assert repair.screen == PARTIES_SCREEN  # onarım taslağı yayının ekran tanımını taşır
        active = await publishing.active_release("lab")
        assert active == release  # etkin yayın değişmedi
    finally:
        await sessions.shutdown()


async def test_dependency_impact_by_adapter_and_action(tmp_path: Path) -> None:
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_no", "Kefil no")
    d = publishing.approve("pub", d.draft_id, d.revision)
    await publishing.publish("pub", d.draft_id, "r1")
    impact = ImpactService(publishing, None, drafts, "lab")  # type: ignore[arg-type]
    result = await impact.dependency_impact(adapter_kinds=["textbox"], action_ids=[])
    assert [i["operation_id"] for i in result["impacted"]] == ["kefil_no"]
    assert (await impact.dependency_impact(adapter_kinds=["combobox"], action_ids=[]))["impacted"] == []
