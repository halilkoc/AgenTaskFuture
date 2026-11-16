"""Uçtan uca: tasarımcıda hazırla → onayla → yayımla (gerçek geçici Mongo) → Asistan ekranından doğal dil
talebiyle
çalıştır. LLM kapalı (kural yolu)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e import test_designer_ui as flow
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        lab.reset()
        settings = lab_settings(
            make_env_file,
            lab,
            RUN_DIRECTORY=str(tmp_path / "runs"),
            DRAFT_DIRECTORY=str(tmp_path / "drafts"),
            CATALOG_BACKEND="mongo",
            MONGO_URI=uri,
            MONGO_DATABASE="agentask_e2e_as",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_assistant_runs_published_operation(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        await flow.author_ready_draft(ui, app_server.port)
        await ui.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı")
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Yayımlandı ve etkin")

        await ui.goto(f"http://127.0.0.1:{app_server.port}/assistant")
        await expect(ui.locator(".as-llm")).to_contain_text("Etkin yayında 1 işlem · model: kapalı")
        await ui.locator("[name=prompt]").fill("Kefil müşteri numarasını gir")
        await ui.get_by_role("button", name="Yorumla").click()
        await expect(ui.locator(".as-result")).to_contain_text("Açıklama gerekli")
        await expect(ui.locator(".as-args")).to_contain_text("Müşteri No (eksik)")
        await ui.locator(".as-args [name=musteri_no]").fill("00456")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-plan")).to_contain_text("etki: yalnız ekran alanları")
        # U3: plan, şablon yerine bağlanan değeri gösterir ve ekran doğrulamasıyla başlar.
        await expect(ui.locator(".as-plan")).to_contain_text("alanına 00456 değerini yaz")
        await expect(ui.locator(".as-plan")).not_to_contain_text("{musteri_no}")
        await expect(ui.locator(".as-plan ol li").first).to_have_text(
            "Ekranı doğrula: Başvuru — taraf bilgileri"
        )
        await expect(ui.locator(".as-bindings")).to_contain_text("Müşteri No: 00456")
        # Sade görünüm: model seçimi politikada; teknik kimlikler katlanır; hazır işlemler seçilebilir.
        await expect(ui.locator("[name=use_model]")).to_have_count(0)
        await expect(ui.locator(".as-plan details.as-tech")).not_to_have_attribute("open", "")
        await expect(ui.locator(".as-ready li button")).to_have_count(1)
        # Özet gösterildikten sonra bilgi değişirse eski özetle başlatılamaz.
        await ui.locator(".as-args [name=musteri_no]").fill("00457")
        await expect(ui.locator(".as-plan")).to_be_hidden()
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".tl-error")).to_contain_text("özetini gösterin")
        await ui.locator(".as-args [name=musteri_no]").fill("00456")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-bindings")).to_contain_text("Müşteri No: 00456")

        # Sayfa değişti: yeni oturum açılmaz; tasarımcının etkileşimli oturumu listeden açıkça seçilir.
        await expect(ui.locator(".sp-quota")).to_contain_text("Etkileşimli oturum: 1/1")
        await expect(ui.get_by_role("button", name="Yeni oturum aç")).to_be_disabled()
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")
        await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".as-session")).to_contain_text("/pages/duplicates")
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=20_000)
        await expect(ui.locator(".rl-run")).to_contain_text("Tamamlandı")
        await expect(ui.locator(".rl-run")).to_contain_text("yayın rel-")
        await browser.close()
