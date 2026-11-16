"""/catalogs üzerinden etkin yayını geri alma: gerekçe, geçmiş, yetki (geçici MongoDB)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod
from tests.unit.test_component_publishing import component_draft, publish

pytestmark = [pytest.mark.browser, pytest.mark.mongo]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        settings = lab_settings(
            make_env_file,
            lab,
            RUN_DIRECTORY=str(tmp_path / "runs"),
            DRAFT_DIRECTORY=str(tmp_path / "drafts"),
            CATALOG_BACKEND="mongo",
            MONGO_URI=uri,
            MONGO_DATABASE="agentask_rollback",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_rollback_from_catalog_screen(app_server: AppServer) -> None:
    container = app_server.app.state.container
    publishing, repo = container.publishing, container.designer._drafts
    first = app_server.run(publish(publishing, repo, component_draft("Birinci"), "ui-1"))
    second = app_server.run(publish(publishing, repo, component_draft("İkinci"), "ui-2"))
    base = f"http://127.0.0.1:{app_server.port}"
    async with httpx.AsyncClient(base_url=base) as api:
        denied = await api.post(
            f"/api/catalogs/releases/{first}/activate",
            json={"expected_active_release_id": second, "reason": "Yetkisiz deneme gerekçesi"},
            headers={"X-Dev-Roles": "designer,operator"},
        )
        assert denied.status_code == 403
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        await ui.goto(f"{base}/catalogs")
        await expect(ui.locator(".ct-list")).to_contain_text(f"etkin: {second}")
        row = ui.locator(".ct-list li").filter(has_text=first)
        await row.get_by_role("button", name="Bu yayını etkinleştir").click()
        await ui.get_by_label("Gerekçe (en az 10 karakter)").fill("kısa")
        await ui.get_by_role("button", name="Etkinleştirmeyi onayla").click()
        await expect(ui.locator(".tl-error")).not_to_be_empty()
        await ui.get_by_label("Gerekçe (en az 10 karakter)").fill("İkinci sürüm hatalı bulundu")
        await ui.get_by_role("button", name="Etkinleştirmeyi onayla").click()
        await expect(ui.locator(".ct-list")).to_contain_text(f"etkin: {first}")
        await expect(ui.locator(".ct-history")).to_contain_text("İkinci sürüm hatalı bulundu")
        # İleri alma aynı yoldan; hiçbir yayın silinmez, geçmiş iki kaydı da gösterir.
        row = ui.locator(".ct-list li").filter(has_text=second)
        await row.get_by_role("button", name="Bu yayını etkinleştir").click()
        await ui.get_by_label("Gerekçe (en az 10 karakter)").fill("Düzeltme doğrulandı, ileri alındı")
        await ui.get_by_role("button", name="Etkinleştirmeyi onayla").click()
        await expect(ui.locator(".ct-list")).to_contain_text(f"etkin: {second}")
        listing = await (await ui.request.get(f"{base}/api/catalogs/releases")).json()
        assert listing["active_release_id"] == second
        assert {first, second} == {r["release_id"] for r in listing["releases"]}
        assert len(listing["activations"]) == 2
        await browser.close()
