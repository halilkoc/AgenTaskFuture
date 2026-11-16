"""Akış Tasarımcısı → gerçek Playwright oturumundan alan seçimi (uçtan uca, lab).

Arayüz ayrı bir tarayıcıdadır; seçim, sunucudaki kullanıcı oturumunun sayfasında gerçek fare olayıyla yapılır.
Doğrulananlar:
- mevcut picker ile seçim ve seçimden sonra semantik yeniden çözüm;
- sayfaya yazma/tıklama olmaması;
- vazgeçince seçim katmanının kalkması;
- ekrandaki alanlardan seçim;
- tarayıcı dialog'unun otomatik kapatılmaması (yalnız açık kararla);
- gerçek adımların temsili denemeye katılmaması.
Gerçek Pega/SSO uyumluluğu değildir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "dev.user"  # dev kimliği, başlık yoksa


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer) -> Iterator[AppServer]:
    lab.reset()
    server = AppServer(create_app(lab_settings(make_env_file, lab)))
    server.start()
    yield server
    server.stop()


async def test_real_session_field_selection(app_server: AppServer, lab: LabServer) -> None:
    sessions = app_server.app.state.container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui: Page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"http://127.0.0.1:{app_server.port}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Gerçek seçim")

        # Kaynak: gerçek oturum. Oturum açılır ve kullanıcının girişi yapılmış ekran hazırlanır.
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        assert sid
        handle = sessions.peek(OWNER, sid)

        async def open_page() -> None:
            await handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/duplicates")

        await in_server(open_page())

        # Yol 1: tarayıcıda kendim seçeyim (mevcut picker). Seçim sayfaya olay göndermez.
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        editor = ui.locator("#pd-editor")
        await editor.get_by_role("button", name="Tarayıcıda kendim seçeyim").click()
        await expect(editor).to_contain_text("seçmeniz bekleniyor")

        async def click_guarantor() -> None:
            field = handle.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No")
            box = await field.bounding_box()
            await handle.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await handle.page.keyboard.type("00999")

        await in_server(click_guarantor())
        chosen = editor.locator(".pd-chosen")
        await expect(chosen).to_contain_text("Kefil › Müşteri No", timeout=15000)
        await expect(chosen).to_contain_text("Metin alanı · Gerçek oturum")
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Her çalıştırmada sor").check()
        await expect(editor.get_by_label("Çalıştırırken ne sorulsun?")).to_have_value(
            "Kefil bölümündeki “Müşteri No” nedir?"
        )
        await expect(ui.locator(".pd-card").first).to_contain_text("Hazır")

        async def page_state() -> tuple[str, int]:
            value = (
                await handle.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value()
            )
            pickers = await handle.page.locator("[data-agentask-ui=picker]").count()
            return value, pickers

        assert await in_server(page_state()) == ("", 0)  # yazılmadı; seçim katmanı kaldırıldı

        # Yeniden bul (yazmadan): hedef güncel ekranda yeniden çözülür.
        await editor.get_by_role("button", name="Alanı yeniden bul (yazmadan)").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("tek olarak bulundu", timeout=10000)

        # Vazgeç: seçim modu ve dinleyiciler kaldırılır.
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        await editor.get_by_role("button", name="Tarayıcıda kendim seçeyim").click()
        await expect(editor).to_contain_text("seçmeniz bekleniyor")

        async def picker_count() -> int:
            return await handle.page.locator("[data-agentask-ui=picker]").count()

        assert await in_server(picker_count()) == 1
        await editor.get_by_role("button", name="Vazgeç").first.click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Seçimden vazgeçildi")
        for _ in range(40):
            if await in_server(picker_count()) == 0:
                break
            await asyncio.sleep(0.1)
        assert await in_server(picker_count()) == 0

        # Yol 2: ekrandaki alanlardan seç (gözlem listesi; öneriyle sınırlı değil).
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Başvuran bölümündeki Müşteri No alanını seç").click()
        await expect(editor.locator(".pd-chosen")).to_contain_text("Başvuran › Müşteri No")

        # Tarayıcı dialog'u: otomatik kapatılmaz; kullanıcı açıkça karar verir.
        async def raise_confirm() -> None:
            await handle.page.evaluate("setTimeout(() => window.confirm('Kayıt silinsin mi?'), 10)")

        await in_server(raise_confirm())
        intr = ui.locator("#pd-real-intr")
        await expect(intr).to_contain_text("Müdahale gerekiyor", timeout=10000)
        await expect(intr).to_contain_text("Kayıt silinsin mi?")
        await intr.get_by_role("button", name="Pencereyi iptal ederek kapat").click()
        await expect(intr).to_be_hidden(timeout=10000)

        # Gerçek oturumda temsili deneme düğmesi yok; temsili moda dönülse de gerçek adımlar orada çalışmaz.
        await expect(ui.get_by_role("button", name="Akışı dene")).to_be_hidden()
        await ui.get_by_role("button", name="Temsili ekranlar").click()
        await ui.get_by_role("button", name="Akışı dene").click()
        await expect(ui.locator("#pd-trial")).to_contain_text("gerçek oturumdan seçildi")
        await browser.close()


async def test_real_selection_is_saved_as_persistent_draft_and_reopened(
    app_server: AppServer, lab: LabServer
) -> None:
    sessions = app_server.app.state.container.sessions
    designer = app_server.app.state.container.designer
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui: Page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        base = f"http://127.0.0.1:{app_server.port}"
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Kefil numarası gir")
        await expect(ui.locator("#pd-flow-app-name")).to_have_text(
            "Deney uygulaması"
        )  # tek uygulama: seçim yok
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
        status = ui.locator("#pd-draft-status")
        await expect(status).to_contain_text("Taslak kaydedildi", timeout=15000)
        link = ui.get_by_role("link", name="Dene, onayla ve yayımla")
        assert "/designer?draft=" in (await link.get_attribute("href") or "")

        # Sunucudaki taslak: semantik hedef (selector yok), kod üretimi parametre ve bağlamlı soru.
        drafts = designer.list_drafts(OWNER)
        assert len(drafts) == 1
        draft = drafts[0]
        assert draft.title == "Kefil numarası gir" and draft.application_id == "lab"
        assert [(str(getattr(x.source, "value", x.source)), x.title) for x in draft.parameters] == [
            ("user_input", "Kefil bölümündeki “Müşteri No” nedir?")
        ]
        step = draft.steps[0]
        element = draft.elements[step.element_id]
        assert str(getattr(step.op, "value", step.op)) == "ensure_value"
        assert step.value_template == "{" + draft.parameters[0].name + "}"
        assert element.target.labels == ["Müşteri No"] and element.target.region == "Kefil"
        dumped = element.model_dump_json()
        assert "#" not in dumped and "xpath" not in dumped.lower()

        # Değişiklik kaydedilmemiş olarak görünür; yeniden kaydetmede yeni adım (eski deneme/onay geçersiz).
        await editor.get_by_label("Çalıştırırken ne sorulsun?").fill("Kefilin müşteri numarası nedir?")
        await expect(status).to_contain_text("kaydedilmemiş değişiklik")
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(status).to_contain_text("Taslak kaydedildi", timeout=15000)
        draft = designer.list_drafts(OWNER)[0]
        assert len(draft.steps) == 1 and draft.steps[0].step_id != step.step_id
        # Soru değişince aynı parametrenin başlığı güncellendi.
        assert [x.title for x in draft.parameters] == ["Kefilin müşteri numarası nedir?"]

        # Akışlara dön → kayıtlı taslağı yeniden aç.
        await ui.get_by_role("button", name="Akışlara dön").click()
        await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await ui.get_by_role("button", name="“Kefil numarası gir” taslağını aç").click()
        await expect(ui.locator(".pd-card").first).to_contain_text("Kefil › Müşteri No")
        await expect(status).to_contain_text("Taslak kaydedildi")

        # Aşama D: yeni tasarımcıdan ekran tanımı, adım onayı, gerçek deneme, sonuç onayı, yeni oturum testi.
        panel = ui.locator("#pd-runpanel")
        await expect(panel).to_be_visible(timeout=10000)
        await panel.get_by_role("button", name="Ekranı tanıt").click()
        await expect(panel.locator("#pd-screen-proposal")).to_contain_text("Ad Soyad")
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Onay bekliyor")
        for box in await panel.locator("[data-ack]").all():
            await box.check()
        await panel.get_by_role("button", name="Onayla", exact=True).click()
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Denemeye hazır", timeout=10000)
        await panel.get_by_label("Kefilin müşteri numarası nedir?").fill("00456")
        await panel.get_by_role("button", name="Gerçek dene").click()
        await expect(ui.locator("#pd-runpanel-status")).to_contain_text("Gerçek denemenin etkisini onaylayın")
        await panel.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
        await panel.get_by_role("button", name="Gerçek dene").click()
        await expect(panel).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=20000)

        async def guarantor_value() -> str:
            return (
                await handle.page.get_by_role("region", name="Kefil").get_by_label("Müşteri No").input_value()
            )

        assert await in_server(guarantor_value()) == "00456"  # gerçek deneme gerçekten yazdı
        await panel.get_by_role("button", name="Sonucu onayla").click()
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Hazır", timeout=10000)
        # Yanlış başlangıç ekranı: test başarısız olur ve kod yerine neden + sonraki adım gösterilir.
        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill("/")
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        failure = panel.locator("#pd-fresh-failure")
        await expect(failure).to_contain_text("başlangıç ekranı", timeout=30000)
        await expect(failure).to_contain_text("Sonraki adım:")
        await expect(panel.locator("#pd-issues")).to_contain_text("Yeni oturum testi başarısız")
        # Lab: yeni oturum otomatik giriş yapılarak bu ekranda açılır (kullanıcının oturumu kullanılmaz).
        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill("/pages/duplicates")
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(ui.locator("#pd-runpanel-status")).to_contain_text(
            "Yeni oturum testi tamamlandı", timeout=30000
        )
        await expect(panel).to_contain_text("Eksik yok: incelemeye hazır.")
        # Bu lab yapılandırmasında katalog deposu kapalı: onay başarı gibi gösterilmez, açık hata verir.
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator("#pd-runpanel-status")).to_contain_text(
            "Katalog yayını devre dışı", timeout=10000
        )
        # Tanım değişince deneme/onay geçersizleşir: yeniden kayıt adımı yeniden oluşturur.
        await ui.locator(".pd-card__main").first.click()
        await editor.get_by_label("Çalıştırırken ne sorulsun?").fill("Kefilin numarası nedir?")
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(status).to_contain_text("Taslak kaydedildi", timeout=15000)
        await expect(panel.locator(".pd-live__step").first).to_contain_text("Onay bekliyor", timeout=10000)

        # Mevcut tasarımcı derin bağlantıyla aynı taslağı açar (deneme/onay/yayın orada).
        await ui.goto(f"{base}/designer?draft={draft.draft_id}")
        await expect(ui.locator("body")).to_contain_text("Kefil numarası gir", timeout=10000)
        await browser.close()
