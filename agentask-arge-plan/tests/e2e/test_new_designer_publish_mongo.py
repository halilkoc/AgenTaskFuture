"""Aşama D kabulü (gerçek geçici MongoDB).

Yeni tasarımcıdan taslak → ekran → onaylar → gerçek deneme → sonuç onayı → yeni oturum testi → yayıncı onayı →
yayın → İşlem Asistanından çalıştırma. Lab; Pega uyumluluğu değildir."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "dev.user"


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
            MONGO_DATABASE="agentask_new_designer",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def test_new_designer_to_published_operation_run_from_assistant(
    app_server: AppServer, lab: LabServer
) -> None:
    sessions = app_server.app.state.container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Kefil numarası gir")
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/duplicates"))

        editor = ui.locator("#pd-editor")
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Kefil bölümündeki Müşteri No alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Her çalıştırmada sor").check()
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=15000)

        panel = ui.locator("#pd-runpanel")
        run_status = ui.locator("#pd-runpanel-status")
        await panel.get_by_role("button", name="Ekranı tanıt").click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        for box in await panel.locator("[data-ack]").all():
            await box.check()
        await panel.get_by_role("button", name="Onayla", exact=True).click()
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Denemeye hazır", timeout=10000)
        await panel.get_by_label("Kefil bölümündeki “Müşteri No” nedir?").fill("00456")
        await panel.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
        await panel.get_by_role("button", name="Gerçek dene").click()
        await expect(panel).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=20000)
        await panel.get_by_role("button", name="Sonucu onayla").click()
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Hazır", timeout=10000)
        # Lab: yeni oturum otomatik giriş yapılarak bu ekranda açılır (kullanıcının oturumu kullanılmaz).
        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill("/pages/duplicates")
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(run_status).to_contain_text("Yeni oturum testi tamamlandı", timeout=30000)
        await expect(panel).to_contain_text("Eksik yok: incelemeye hazır.")
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(run_status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await panel.get_by_role("button", name="Yayımla").click()
        await expect(run_status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)

        # İş birimi: İşlem Asistanından hazır işlem → eksik bilgi → özet → başlat → sonuç.
        await ui.goto(f"{base}/assistant")
        await expect(ui.locator(".as-llm")).to_contain_text("Etkin yayında 1 işlem")
        await ui.locator(".as-ready-wrap summary").click()
        await ui.locator(".as-ready").get_by_role("button", name="Kefil numarası gir").click()
        await ui.locator(".as-args input").first.fill("00789")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-bindings")).to_contain_text("00789")
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".as-session")).to_contain_text("/pages/duplicates")
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=30_000)
        await expect(ui.locator(".rl-run")).to_contain_text("Tamamlandı")

        async def guarantor() -> str:
            return (
                await handle.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value()
            )

        assert await in_server(guarantor()) == "00789"
        await browser.close()
