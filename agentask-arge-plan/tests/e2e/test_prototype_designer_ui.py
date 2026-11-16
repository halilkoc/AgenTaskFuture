"""Akış Tasarımcısı prototipi (/prototype/designer) uçtan uca.

Prototip yalnız tarayıcı belleğinde çalışır: hiçbir /api çağrısı yapmamalı, dış kaynak yüklememeli.
Bu test gerçek Pega uyumluluğunu değil, prototipin temel etkileşimlerini doğrular.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.config import load_settings
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.test_app import TWO_APPS
from tests.support_browser import ui_engine

pytestmark = pytest.mark.browser


@pytest.fixture
def app_server(make_env_file: EnvFileFactory) -> Iterator[AppServer]:
    settings = load_settings(make_env_file(CATALOG_BACKEND="disabled", AUTOMATION_APPLICATIONS_JSON=TWO_APPS))
    server = AppServer(create_app(settings))
    server.start()
    yield server
    server.stop()


APP_ONE = "Yerel deney uygulaması"
APP_TWO = "Yerel deney uygulaması (ikinci origin)"


async def _new_flow(ui: Page, name: str, app: str = APP_ONE) -> None:
    await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
    await expect(ui.locator("#pd-editor-view")).to_be_visible()
    await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill(name)
    await ui.get_by_label("Uygulama (zorunlu)", exact=True).select_option(label=app)


async def _pick_field(ui: Page, screen: str, field_label: str) -> None:
    dialog = ui.locator("#pd-picker")
    await expect(dialog).to_be_visible()
    await dialog.get_by_role("button", name=screen, exact=True).click()
    await dialog.get_by_role("button", name=field_label).click()
    await expect(dialog).to_be_hidden()


async def test_prototype_designer_core_flow(app_server: AppServer) -> None:
    base = f"http://127.0.0.1:{app_server.port}"
    requests: list[str] = []
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
        ui.on("request", lambda r: requests.append(r.url))
        ui.on("pageerror", lambda e: errors.append(str(e)))
        ui.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        await ui.goto(f"{base}/prototype/designer")

        await expect(ui.get_by_role("heading", name="Akış Tasarımcısı")).to_be_visible()
        await expect(ui.locator(".pd-notice")).to_contain_text("yenileyince silinir")

        # Açık/koyu tema seçimi.
        root = ui.locator("html")
        theme = ui.get_by_role("button", name="Koyu tema")
        before = await theme.get_attribute("aria-pressed")
        await theme.click()
        after = "false" if before == "true" else "true"
        await expect(theme).to_have_attribute("aria-pressed", after)
        await expect(root).to_have_attribute("data-theme", "dark" if after == "true" else "light")

        # Akışlar görünümü; değişiklik yoksa geri dönüş onay istemez ve akış oluşturulmaz.
        home = ui.locator("#pd-home")
        await expect(home.get_by_role("heading", name="Akışlar")).to_be_visible()
        await expect(home).to_contain_text("Henüz akış yok")
        await home.get_by_role("button", name="Yeni akış").click()
        await expect(ui.locator("#pd-dirty")).to_contain_text("henüz oluşturulmadı")
        await ui.get_by_role("button", name="Akışlara dön").click()
        await expect(ui.locator("#pd-confirm")).to_be_hidden()
        await expect(home).to_be_visible()
        await expect(home).to_contain_text("Henüz akış yok")

        # Yapılandırmadaki iki uygulama listelenir (uygulama seçimi ekran seçiminden ayrı).
        await home.get_by_role("button", name="Yeni akış").click()
        app_select = ui.get_by_label("Uygulama (zorunlu)", exact=True)
        await expect(app_select.locator("option")).to_have_text(["Seçin…", APP_ONE, APP_TWO])
        await expect(ui.locator("#pd-flow-app-err")).to_contain_text("Uygulama seçin")
        await app_select.select_option(label=APP_ONE)
        await expect(ui.get_by_label("Başlangıç ekranı (temsili)")).to_be_visible()
        await expect(ui.locator("#pd-components-unsupported")).to_contain_text("Bu prototipte henüz yok")

        # 1-2. Akışa ad ver, Alan doldur ekle.
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Kefil ve teminat")
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        editor = ui.locator("#pd-editor")
        await expect(editor).to_contain_text("Değerin yazılacağı alanı seçin")
        await expect(editor.get_by_role("heading", name="Hangi alan?")).to_be_visible()
        await expect(editor.get_by_role("heading", name="Değer nereden gelsin?")).to_be_visible()
        details = editor.locator("details.pd-details")
        await expect(details).not_to_have_attribute("open", "")

        # Yol 1: önerilen alanlardan seç. Bilgiler ve bölüm bağlamlı soru güncellenir.
        await editor.get_by_role("button", name="Müşteri bölümündeki Müşteri No alanını seç").click()
        chosen = editor.locator(".pd-chosen")
        await expect(chosen).to_contain_text("Müşteri › Müşteri No")
        await expect(chosen).to_contain_text("Metin alanı · Müşteri Bilgileri ekranı")
        await editor.get_by_label("Her çalıştırmada sor").check()
        question = editor.get_by_label("Çalıştırırken ne sorulsun?")
        await expect(question).to_have_value("Müşterinin müşteri numarası nedir?")
        await expect(editor).to_contain_text("Önerilen soru · temsili")

        # Yol 2: ekrandan kendim seçeyim. Alan, bölüm ve soru güncellenir; uygulamada işlem yapılmaz.
        await editor.get_by_role("button", name="Değiştir").click()
        await editor.get_by_role("button", name="Ekrandan kendim seçeyim").click()
        await _pick_field(ui, "Müşteri Bilgileri", "Müşteri No, Kefil bölümü")
        await expect(chosen).to_contain_text("Kefil › Müşteri No")
        await expect(question).to_have_value("Kefilin müşteri numarası nedir?")
        await expect(ui.locator("#pd-toasts")).to_contain_text("Uygulamada işlem yapılmadı")
        await expect(editor.get_by_role("button", name="Değiştir")).to_be_focused()

        # Otomatik ad/açıklama ve teknik bilgiler "Ayrıntılar" altında, düzenlenebilir.
        await details.locator("summary").click()
        await expect(editor.get_by_label("Adım adı")).to_have_value("Kefilin müşteri numarası")
        await expect(editor.get_by_label("Alanın açıklaması")).to_have_value(
            "Müşteri Bilgileri ekranındaki Kefil bölümünde bulunan “Müşteri No” metin alanı. "
            "Ekranda gözlenen sınır: yalnız rakam, en fazla 10 karakter."
        )
        await expect(details).to_contain_text("kefilin_musteri_numarasi")

        # Kullanıcı soruyu değiştirebilir; sabit değerde geçersiz değer alanın yanında açıklanır.
        await question.fill("Kefilin müşteri no'su nedir?")
        await expect(editor).not_to_contain_text("Önerilen soru · temsili")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("12ab")
        await expect(editor).to_contain_text("yalnız rakam kabul ediyor")
        await editor.get_by_label("Her çalıştırmada sor").check()
        await expect(editor.get_by_label("Çalıştırırken ne sorulsun?")).to_have_value(
            "Kefilin müşteri no'su nedir?"
        )
        await expect(ui.locator("#pd-ed-summary")).to_have_text(
            "Kefil bölümündeki “Müşteri No” alanına her çalıştırmada sorulan değeri yaz."
        )
        card = ui.locator(".pd-card").first
        await expect(card).to_contain_text("Kefil › Müşteri No")
        await expect(card).to_contain_text("Hazır")

        # Başka ekrandaki alan: geçiş eksikliği açıklanır.
        await ui.locator("#pd-components").get_by_role("button", name="Alan doldur").click()
        # Önerilerde olmayan alan (başka ekranda) doğrudan ekrandan seçilebilir.
        await expect(editor.locator(".pd-fieldsugs")).not_to_contain_text("Teminat Tutarı")
        await editor.get_by_role("button", name="Ekrandan kendim seçeyim").click()
        await _pick_field(ui, "Teminat", "Teminat Tutarı")
        await expect(editor.locator(".pd-chosen")).to_contain_text("Teminat › Teminat Tutarı")
        await expect(editor.locator(".pd-chosen")).to_contain_text("Tutar alanı · Teminat ekranı")
        await expect(editor).to_contain_text("Önüne bir “Ekrana geç” adımı ekleyin")
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(
            label="1. adım: Kefilin müşteri numarası"
        )
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("15000")

        # Yazılı niyetten temsili öneri → ekran geçişi; yukarı taşı düğmesiyle sırala.
        await ui.get_by_label("Kendi cümlenizle yazın").fill("Teminat ekranına geç")
        await ui.get_by_role("button", name="Öneri al").click()
        await expect(ui.locator("#pd-intent-result")).to_contain_text("Temsili öneri")
        await ui.locator("#pd-intent-result").get_by_role("button", name="Ekle").click()
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        await ui.get_by_role("button", name="3. adımı yukarı taşı").click()
        await expect(ui.locator(".pd-card").nth(1)).to_contain_text("“Devam” düğmesi")
        await expect(ui.get_by_role("button", name="2. adımı yukarı taşı")).to_be_focused()
        for i in range(3):
            await expect(ui.locator(".pd-card").nth(i)).to_contain_text("Hazır")

        # 6. Dene: sorulan değer doğrulanır, sonra temsili uygulamada çalışır.
        await expect(ui.locator("#pd-trial-status")).to_contain_text("Denenmedi")
        await ui.get_by_role("button", name="Akışı dene").click()
        trial = ui.locator("#pd-trial")
        await trial.get_by_label("Kefilin müşteri no'su nedir?").fill("00456")
        await trial.get_by_role("button", name="Denemeyi başlat").click()
        await expect(trial.locator("#pd-trial-result")).to_contain_text("Deneme başarılı", timeout=10000)
        await expect(trial.locator("#mock-pd-trial-app-t_tutar")).to_have_value("15000")
        await trial.get_by_role("button", name="Kapat").last.click()
        await expect(ui.locator("#pd-trial-status")).to_contain_text("Deneme başarılı")

        # Sayfada sakla: kalıcı kayıt izlenimi verilmez.
        await ui.get_by_role("button", name="Sayfada sakla").click()
        await expect(ui.locator("#pd-toasts")).to_contain_text("Kalıcı kayıt değildir")
        await expect(ui.locator("#pd-dirty")).to_have_text("Değişiklik yok")

        # Yayımla ayrı: yalnız prototip gösterimi.
        await ui.get_by_role("button", name="Yayımla…").click()
        publish = ui.locator("#pd-publish-dialog")
        await publish.get_by_role("button", name="Yayımla (prototip gösterimi)").click()
        await expect(publish).to_contain_text("Gösterim sürümü 1 oluşturuldu", timeout=5000)
        await expect(publish).to_contain_text("hiçbir şey yazılmadı")
        await publish.get_by_role("button", name="Kapat").last.click()

        # Değişiklik denemeyi eskitir; yayın engellenir.
        await ui.locator(".pd-card__main").first.click()
        await editor.get_by_label("Çalıştırırken ne sorulsun?").fill("Kefilin numarası nedir?")
        await expect(ui.locator("#pd-trial-status")).to_contain_text("Deneme eskidi")
        await expect(ui.locator("#pd-dirty")).to_contain_text("Saklanmamış değişiklik var")
        confirm = ui.locator("#pd-confirm")
        await ui.get_by_role("button", name="Akışlara dön").click()
        await expect(confirm).to_be_visible()
        await expect(confirm.get_by_role("button", name="Düzenlemeye devam et")).to_be_focused()
        await confirm.get_by_role("button", name="Düzenlemeye devam et").click()
        await expect(confirm).to_be_hidden()
        await expect(ui.locator("#pd-editor-view")).to_be_visible()
        await expect(ui.get_by_label("Çalıştırırken ne sorulsun?")).to_have_value("Kefilin numarası nedir?")
        await ui.get_by_role("button", name="Yayımla…").click()
        await expect(publish.get_by_role("button", name="Yayımla (prototip gösterimi)")).to_be_disabled()
        await publish.get_by_role("button", name="Kapat").last.click()

        # Hata senaryosu: hedef yoksa açık hata, hiçbir şey yazılmaz, sonraki adımlar atlanır.
        await ui.get_by_role("button", name="Akışı dene").click()
        await trial.get_by_label("Temsili senaryo (prototip)").select_option("no-kefil")
        await trial.get_by_role("button", name="Denemeyi başlat").click()
        await expect(trial.locator("#pd-trial-result")).to_contain_text("1. adımda durdu", timeout=10000)
        await expect(trial.locator("#pd-trial-progress")).to_contain_text("hiçbir şey yazılmadı")
        await expect(trial.locator("#pd-trial-progress")).to_contain_text("Çalıştırılmadı.")
        await trial.get_by_role("button", name="Kapat").last.click()

        # 7. Bileşen oluşturmayı iptal etmek kaynak akışı değiştirmez.
        cards = ui.locator(".pd-card")
        before = await cards.all_inner_texts()
        await ui.get_by_label("2. adımı bileşen için işaretle").check()
        await ui.get_by_label("3. adımı bileşen için işaretle").check()
        comp = ui.locator("#pd-component-dialog")
        # Hiçbir şey yazılmadıysa Esc onay sormadan kapatır.
        await ui.get_by_role("button", name="Yeniden kullanılabilir bileşen olarak kaydet").click()
        await ui.keyboard.press("Escape")
        await expect(comp).to_be_hidden()
        await expect(confirm).to_be_hidden()
        # Yazılmışsa: devam et → bilgiler korunur; bırak → kapanır.
        await ui.get_by_role("button", name="Yeniden kullanılabilir bileşen olarak kaydet").click()
        await comp.get_by_label("Bileşenin adı").fill("Yarım kalan bileşen")
        await comp.get_by_role("button", name="Vazgeç").click()
        await confirm.get_by_role("button", name="Düzenlemeye devam et").click()
        await expect(comp).to_be_visible()
        await expect(comp.get_by_label("Bileşenin adı")).to_have_value("Yarım kalan bileşen")
        await comp.get_by_role("button", name="Vazgeç").click()
        await confirm.get_by_role("button", name="Değişiklikleri bırak").click()
        await expect(comp).to_be_hidden()
        assert await cards.all_inner_texts() == before
        await expect(ui.locator("#pd-library")).to_contain_text("Henüz yok")

        # Adımları yeniden kullanılabilir bileşen yap, başka akışta kullan.
        await ui.get_by_role("button", name="Yeniden kullanılabilir bileşen olarak kaydet").click()
        await comp.get_by_label("Bileşenin adı").fill("Teminata geç ve tutar gir")
        await comp.get_by_role("button", name="Kaydet").click()
        await expect(ui.locator("#pd-library")).to_contain_text("Teminata geç ve tutar gir")
        await expect(ui.locator(".pd-card")).to_have_count(2)
        await expect(ui.locator(".pd-card").nth(1)).to_contain_text("“Teminata geç ve tutar gir” bileşeni")

        # Değişiklikleri bırak: akış son saklanan haline döner (bileşen kütüphanede kalır).
        await ui.get_by_role("button", name="Akışlara dön").click()
        await confirm.get_by_role("button", name="Değişiklikleri bırak").click()
        await expect(home).to_be_visible()
        flow_items = home.locator(".pd-flowitem")
        await expect(flow_items).to_have_count(1)
        await expect(flow_items.first).to_contain_text("Kefil ve teminat")
        await expect(flow_items.first).to_contain_text(f"{APP_ONE} · 3 adım")
        await expect(home.get_by_role("button", name="“Kefil ve teminat” akışını düzenle")).to_be_focused()

        await _new_flow(ui, "İkinci akış")
        await ui.get_by_role("button", name="“Teminata geç ve tutar gir” bileşenini akışa ekle").click()
        await expect(ui.locator(".pd-card")).to_have_count(1)
        await expect(ui.locator(".pd-card").first).to_contain_text("Hazır")
        await ui.get_by_role("button", name="Akışı dene").click()
        await trial.get_by_role("button", name="Denemeyi başlat").click()
        await expect(trial.locator("#pd-trial-result")).to_contain_text("Deneme başarılı", timeout=10000)
        await trial.get_by_role("button", name="Kapat").last.click()

        await browser.close()

    assert not errors, errors
    # Prototip ürün API'lerine, MongoDB'ye veya dış kaynaklara erişmez.
    assert all(u.startswith(base) for u in requests), requests
    assert not [u for u in requests if "/api/" in u], requests


async def test_prototype_picker_does_not_trigger_actions_and_flags_ambiguity(app_server: AppServer) -> None:
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1280, "height": 900})
        await ui.goto(f"http://127.0.0.1:{app_server.port}/prototype/designer")
        await _new_flow(ui, "Seçici denemesi")

        # Belirsiz niyet: iki "Müşteri No" alanı → ilki seçilmez, kullanıcıya sorulur.
        await ui.get_by_label("Kendi cümlenizle yazın").fill("müşteri numarasını yaz")
        await ui.get_by_role("button", name="Öneri al").click()
        result = ui.locator("#pd-intent-result")
        await expect(result).to_contain_text("2 alan eşleşti")
        await expect(ui.locator(".pd-card")).to_have_count(0)

        # Desteklenmeyen istek sahte adım üretmez.
        await ui.get_by_label("Kendi cümlenizle yazın").fill("Kaydet düğmesine bas ve kaydet")
        await ui.get_by_role("button", name="Öneri al").click()
        await expect(result).to_contain_text("sahte bir adım oluşturulmadı")
        await expect(ui.locator(".pd-card")).to_have_count(0)

        # Düğme seçme modunda düğmeye basılmaz; ekran değişmez.
        await ui.locator("#pd-components").get_by_role("button", name="Ekrana geç").click()
        await ui.locator("#pd-editor").get_by_role("button", name="Ekrandan düğme seç").click()
        picker = ui.locator("#pd-picker")
        await picker.get_by_role("button", name="Kaydet düğmesi — bu düğmeyi seç").click()
        await expect(picker).to_be_hidden()
        await expect(ui.locator("#pd-toasts")).to_contain_text("Düğmeye basılmadı")
        editor = ui.locator("#pd-editor")
        await expect(editor).to_contain_text("iş etkisini ekrana bakarak bilemez")

        # Kullanıcı yanlış beyan ederse deneme açıkça durur ve tekrar basmaz.
        await editor.get_by_label("Düğmeye basınca hangi ekran açılmalı?").select_option(label="Teminat")
        await editor.get_by_label("Bu düğmenin yalnız ekran değiştirdiğini biliyorum").check()
        await editor.get_by_role("button", name="Bu adımı dene").click()
        trial = ui.locator("#pd-trial")
        await trial.get_by_role("button", name="Denemeyi başlat").click()
        await expect(trial.locator("#pd-trial-result")).to_contain_text(
            "adım otomatik olarak tekrarlanmadı", timeout=10000
        )

        # Klavye: Esc diyaloğu kapatır, odak tetikleyen düğmeye döner.
        await ui.keyboard.press("Escape")
        await expect(trial).to_be_hidden()
        await expect(editor.get_by_role("button", name="Bu adımı dene")).to_be_focused()
        await browser.close()


async def test_prototype_stop_and_application_switch(app_server: AppServer) -> None:
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page(viewport={"width": 1280, "height": 900})
        await ui.goto(f"http://127.0.0.1:{app_server.port}/prototype/designer")
        await _new_flow(ui, "Durdurma ve uygulama")
        await ui.get_by_role("button", name="Örnek akışla başla").click()

        # Durdurma: tamamlananlar geri alınmış gibi gösterilmez, sonraki adımlar başlatılmaz.
        await ui.get_by_role("button", name="Akışı dene").click()
        trial = ui.locator("#pd-trial")
        for field in await trial.locator("#pd-trial-setup input[type=text]").all():
            await field.fill("123")
        await trial.get_by_label("Temsili senaryo (prototip)").select_option("slow")
        await trial.get_by_role("button", name="Denemeyi başlat").click()
        progress = trial.locator("#pd-trial-progress")
        await expect(progress).to_contain_text("ekran bekleniyor", timeout=10000)
        await trial.get_by_role("button", name="Durdur").click()
        result = trial.locator("#pd-trial-result")
        await expect(result).to_contain_text("Deneme durduruldu", timeout=10000)
        await expect(result).to_contain_text("Tamamlanan 2 adım geri alınmadı")
        items = progress.locator(":scope > li")
        await expect(items.nth(0)).to_contain_text("yazıldı")
        await expect(items.nth(2)).to_contain_text("Düğmeye basılmıştı")
        await expect(items.nth(3)).to_contain_text("Çalıştırılmadı (deneme durduruldu).")
        await expect(items.nth(4)).to_contain_text("Çalıştırılmadı (deneme durduruldu).")
        await expect(trial.locator("#mock-pd-trial-app-k_no")).to_have_value("123")
        await trial.get_by_role("button", name="Kapat").last.click()

        # Uygulama değişimi: kayıp varsa sorulur; vazgeçilirse hiçbir şey değişmez.
        app_select = ui.get_by_label("Uygulama (zorunlu)", exact=True)
        confirm = ui.locator("#pd-confirm")
        await app_select.select_option(label=APP_TWO)
        await expect(confirm).to_be_visible()
        await confirm.get_by_role("button", name="Vazgeç").click()
        await expect(app_select).to_have_value("lab")
        await expect(ui.locator(".pd-card").first).to_contain_text("Müşteri › Müşteri No")

        # Değiştirilirse önceki uygulamanın hedefleri ve deneme sonucu taşınmaz.
        await app_select.select_option(label=APP_TWO)
        await confirm.get_by_role("button", name="Uygulamayı değiştir").click()
        await expect(app_select).to_have_value("lab_ikinci")
        await expect(ui.locator(".pd-card").first).to_contain_text("Alan seçilmedi")
        await expect(ui.locator(".pd-card").nth(2)).to_contain_text("Düğme seçilmedi")
        await expect(ui.locator("#pd-trial-status")).to_contain_text("Denenmedi")
        await ui.get_by_role("button", name="Akışı dene").click()
        await expect(trial).to_contain_text("Deneme başlatılamadı")
        await browser.close()
