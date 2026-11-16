"""Ana plan C — yeni Akış Tasarımcısında gerçek oturumla çok ekranlı taslak (uçtan uca, lab).

Doğrulananlar:
- "Bilgi oku" adımı ve sonraki adımda gerçek okuma çıktısına bağlama (prior_output);
- sade "sonuç kontrolü" seçimi (success_check);
- gerçek düğmeyle "Ekrana geç": geçiş kalıcı kaydedilir (tetikleyici tekil çözülür, tıklanmaz), hedef ekran
  sonra tanıtılır;
- yeniden açıldığında adımların düzenlenebilir olarak gelmesi.
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
OWNER = "dev.user"


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer) -> Iterator[AppServer]:
    lab.reset()
    server = AppServer(create_app(lab_settings(make_env_file, lab)))
    server.start()
    yield server
    server.stop()


async def test_read_bind_transition_and_reopen(app_server: AppServer, lab: LabServer) -> None:
    sessions = app_server.app.state.container.sessions
    designer = app_server.app.state.container.designer
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui: Page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await ui.goto(f"http://127.0.0.1:{app_server.port}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Vaka kopyala")
        # Gerçek oturum gerektiren adımlar temsili kaynakta eklenmez (sahte çıktı üretilmez).
        await ui.locator("#pd-components").get_by_role("button", name="Bilgi oku").click()
        await expect(ui.locator(".pd-toast, [role=status]").first).to_be_attached()
        await expect(ui.locator(".pd-card")).to_have_count(0)

        await ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/wizard/C-51"))
        editor = ui.locator("#pd-editor")
        found = "Ekranda tek olarak bulundu."

        # 1) Bilgi oku: Vaka No
        await ui.locator("#pd-components").get_by_role("button", name="Bilgi oku").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Vaka bölümündeki Vaka No alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(found, timeout=10000)

        # 2) Alan doldur: Müşteri No ← 1. adımın okunan değeri; ek kontrol yok
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Müşteri bölümündeki Müşteri No alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(found, timeout=10000)
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)
        await editor.get_by_label("Ek kontrol yapma").check()
        await expect(editor).to_contain_text("yalnız alana yazar; kayıt yapmaz")

        # 3) Ekrana geç: gerçek "Devam" düğmesi; hedef ekranın adını analist yazar
        await ui.locator("#pd-components").get_by_role("button", name="Ekrana geç").click()
        await editor.get_by_role("button", name="Ekrandaki düğmeleri listele").click()
        await editor.get_by_role("button", name="Devam düğmesini seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(found, timeout=10000)
        await editor.get_by_label("Düğmeye basınca açılacak ekranın adı").fill("Teminat bilgileri")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()

        await ui.get_by_role("button", name="Taslağı kaydet").click()
        status = ui.locator("#pd-draft-status")
        await expect(status).to_contain_text("Taslak kaydedildi", timeout=20000)

        async def wizard_url() -> str:
            return str(handle.page.url)

        assert (await in_server(wizard_url())).endswith("/wizard/C-51")  # kaydetme düğmeye basmadı

        draft = designer.list_drafts(OWNER)[0]
        assert [str(s.op) for s in draft.steps] == ["read", "ensure_value", "follow_transition"]
        (prior,) = draft.parameters
        assert str(prior.source) == "prior_output" and prior.prior_step == 0
        assert draft.steps[1].value_template == "{" + prior.name + "}"
        assert draft.steps[1].success_check == "none"
        (transition,) = draft.transitions
        assert transition.trigger.target.labels == ["Devam"]  # type: ignore[union-attr]
        assert draft.steps[2].transition_id == transition.transition_id

        # Ekranlar: başlangıç ekranı şimdi, hedef ekran düğmeye analist basınca tanıtılır.
        panel = ui.locator("#pd-runpanel")
        await expect(panel).to_contain_text("tanıtılmadı", timeout=10000)
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(ui.locator("#pd-runpanel-status")).to_contain_text(
            "tanımlandı ve doğrulandı", timeout=15000
        )

        async def press_next() -> None:
            await handle.page.get_by_role("button", name="Devam").click()
            await handle.page.wait_for_url("**/collateral")

        await in_server(press_next())
        await expect(panel.get_by_label("Tarayıcıda şu an açık olan ekran")).to_have_value(
            transition.to_screen, timeout=10000
        )
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        draft = designer.get(OWNER, draft.draft_id)
        assert draft.screen is not None and [s.title for s in draft.extra_screens] == ["Teminat bilgileri"]
        issues = designer.validate(OWNER, draft.draft_id)
        assert not [i for i in issues if "unknown_screen" in i or "prior_output" in i], issues

        # Yeniden aç: adımlar düzenlenebilir gelir, kaydedilmemiş değişiklik görünmez.
        await ui.get_by_role("button", name="Akışlara dön").click()
        await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await ui.get_by_role("button", name="“Vaka kopyala” taslağını aç").click()
        cards = ui.locator(".pd-card")
        await expect(cards).to_have_count(3)
        await expect(cards.nth(0)).to_contain_text("Vaka › Vaka No")
        await expect(cards.nth(1)).to_contain_text("Önceki adımdan")
        await expect(cards.nth(2)).to_contain_text("Teminat bilgileri")
        await expect(status).to_contain_text("Taslak kaydedildi")
        await expect(status).not_to_contain_text("Salt okunur")
        await browser.close()
