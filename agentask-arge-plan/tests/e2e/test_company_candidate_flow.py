"""Şirket testi adayı bütünleşik kabul (Chromium + lab + geçici MongoDB; Pega/SSO değildir).

AgenTask admin girişi → hedefe elle giriş → doldur/oku/önceki çıktı/seçim → kalıcı kayıt ve yeniden açma →
onay ve gerçek deneme → yeni oturum testinde elle giriş bekleme → yayın → İşlem Asistanı → geçmiş → çıkış."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.domain.passwords import hash_password
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import changed_fields, page_fields
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "admin"
PASSWORD = "bu-test-parolasi-12345"
PATH = "/pages/selections"
Logs = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı")
        lab.reset()
        settings = lab_settings(
            make_env_file,
            lab,
            AUTH_MODE="local_admin",
            DEV_AUTH_ENABLED="false",
            ADMIN_USERNAME=OWNER,
            ADMIN_PASSWORD_HASH=hash_password(PASSWORD),
            RUN_DIRECTORY=str(tmp_path / "runs"),
            DRAFT_DIRECTORY=str(tmp_path / "drafts"),
            CATALOG_BACKEND="mongo",
            MONGO_URI=uri,
            MONGO_DATABASE="agentask_candidate",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()
        lab.reset()


async def pick(ui: Page, component: str, field: str) -> Any:
    editor = ui.locator("#pd-editor")
    await ui.locator("#pd-components").get_by_role("button", name=component).click()
    await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
    await editor.get_by_role("button", name=field).click()
    await expect(editor.locator("[id$='-check']")).to_have_text("Ekranda tek olarak bulundu.", timeout=10000)
    return editor


async def test_company_candidate_flow(app_server: AppServer, lab: LabServer, json_logs: Logs) -> None:
    container = app_server.app.state.container
    sessions = container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    async def lab_login(page: Any) -> None:
        await page.get_by_label("Kullanıcı adı").fill("pega.kullanici")
        await page.get_by_role("button", name="Giriş yap").click()

    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page(viewport={"width": 1440, "height": 1000})

        # 1) AgenTask girişi; hatalı parola genel mesaj verir, dev kimliğine düşülmez.
        await ui.goto(f"{base}/prototype/designer")
        await expect(ui).to_have_url(f"{base}/login?next=/prototype/designer")
        await ui.get_by_label("Kullanıcı adı").fill(OWNER)
        await ui.get_by_label("Parola").fill("yanlis-parola-000")
        await ui.get_by_role("button", name="Giriş yap").click()
        await expect(ui.locator(".tl-error")).to_contain_text("hatalı")
        await ui.get_by_label("Parola").fill(PASSWORD)
        await ui.get_by_role("button", name="Giriş yap").click()
        await expect(ui).to_have_url(f"{base}/prototype/designer")

        # 2) Hedef uygulamaya otomasyon penceresinde elle giriş (AgenTask oturumundan ayrı).
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Şirket adayı akışı")
        await expect(ui.locator("#pd-try-flow")).to_be_visible()
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await expect(ui.locator("#pd-try-flow")).to_be_hidden()  # temsili öğeler gerçek oturumda yok
        await expect(ui.locator("#pd-proto-badge")).to_be_hidden()
        await expect(ui.locator("#pd-publish")).to_be_hidden()
        assert "Prototip" not in await ui.title()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await ui.get_by_role("button", name="Uygulamayı oturumda aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Açıldı", timeout=10000)

        async def open_selections() -> None:
            await lab_login(handle.page)
            await handle.page.get_by_role("link", name="Seçim senaryoları").click()
            await handle.page.get_by_role("region", name="Kefil").get_by_label("Şube").wait_for()

        await in_server(open_selections())
        baseline = await in_server(page_fields(handle.page))
        assert baseline["Kefil › Şube"] == baseline["Başvuran › Şube"] == "Seçiniz"

        # Desteklenmeyen hedef: açık açıklamayla durur, kaydedilmez (rastgele işlem yok).
        async def add_rich_text() -> None:
            await handle.page.evaluate("""() => { const d = document.createElement('div');
                d.setAttribute('role', 'textbox'); d.setAttribute('aria-label', 'Zengin Metin');
                d.contentEditable = 'true'; d.textContent = 'x'; document.body.prepend(d); }""")

        await in_server(add_rich_text())
        editor = await pick(ui, "Alan doldur", "Zengin Metin alanını seç")
        await expect(editor).to_contain_text("biçimlendirilebilir")
        await editor.get_by_role("button", name="Adımı sil").click()

        # Betikle eklenen öğe yeni oturumda yoktur; ekran tanıtılmadan önce kaldırılır
        # (sayfa yeni oturumla aynı).
        async def remove_rich_text() -> int:
            return int(
                await handle.page.evaluate(
                    """() => {
                    document.querySelectorAll('[aria-label="Zengin Metin"]').forEach((e) => e.remove());
                    return document.querySelectorAll('[aria-label="Zengin Metin"]').length; }"""
                )
            )

        assert await in_server(remove_rich_text()) == 0

        # 3) Adımlar: doldur → oku → önceki çıktı → sabit seçim.
        editor = await pick(ui, "Alan doldur", "Kefil bölümündeki Ad Soyad alanını seç")
        await editor.get_by_label("Sabit değer").check()
        await editor.get_by_label("Yazılacak değer").fill("Test Kefil")
        await pick(ui, "Bilgi oku", "Kefil bölümündeki Ad Soyad alanını seç")
        editor = await pick(ui, "Alan doldur", "Başvuran bölümündeki Ad Soyad alanını seç")
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)
        editor = await pick(ui, "Seçim yap", "Ürün bölümündeki Merkez Kodu alanını seç")
        await expect(editor.locator(".pd-optlist")).to_contain_text("Merkez", timeout=10000)
        await editor.get_by_label("Sabit seçenek").check()
        await editor.get_by_label("Seçilecek seçenek").select_option(label="Merkez")
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()
        editor = await pick(ui, "Seçim yap", "Kefil bölümündeki Şube alanını seç")
        await expect(editor.locator(".pd-optlist")).to_contain_text("Konak", timeout=10000)
        await editor.get_by_label("Sabit seçenek").check()
        await editor.get_by_label("Seçilecek seçenek").select_option(label="Konak")
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()
        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)
        assert (
            await in_server(page_fields(handle.page)) == baseline
        )  # tanımlama ve kaydetme hiçbir alanı değiştirmez

        # 4) Sayfa yenilendi: AgenTask oturumu sürer, taslak tutarlı açılır, temsili etiket yok.
        await ui.reload()
        await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await ui.get_by_role("button", name="“Şirket adayı akışı” taslağını aç").click()
        cards = ui.locator(".pd-card")
        await expect(cards).to_have_count(5)
        await expect(cards.nth(0)).to_contain_text("Sabit değer: “Test Kefil”")
        await expect(cards.nth(2)).to_contain_text("Önceki adımdan")
        await expect(cards.nth(3)).to_contain_text("Sabit seçenek: “Merkez”")
        await expect(cards.nth(4)).to_contain_text("Sabit seçenek: “Konak”")
        await expect(ui.locator("#pd-steps")).not_to_contain_text("eksik")  # kayıtlı tanım eksik sayılmaz
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi")
        await expect(ui.locator("#pd-proto-badge")).to_be_hidden()
        await expect(ui.get_by_label("Tarayıcı oturumu")).to_have_value(sid, timeout=10000)

        panel = ui.locator("#pd-runpanel")
        status = ui.locator("#pd-runpanel-status")
        await panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)
        steps = panel.locator(".pd-live__step")
        for i in range(5):
            step = steps.nth(i)
            for box in await step.locator("[data-ack]").all():
                await box.check()
            await step.get_by_role("button", name="Onayla", exact=True).click()
            await expect(step).to_contain_text("Denemeye hazır", timeout=10000)
            await step.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
            await step.get_by_role("button", name="Gerçek dene").click()
            await expect(step).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=25000)
            await step.get_by_role("button", name="Sonucu onayla").click()
            await expect(step).to_contain_text("Hazır", timeout=10000)

        expected_change = {
            "Kefil › Ad Soyad": "Test Kefil",
            "Başvuran › Ad Soyad": "Test Kefil",
            "Ürün › Merkez Kodu": "Merkez",
            "Kefil › Şube": "Konak",
        }
        assert changed_fields(baseline, await in_server(page_fields(handle.page))) == expected_change

        # 5) Yeni oturum testi elle giriş bekler; girişsiz devam işlem başlatmaz.
        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill(PATH)
        await panel.get_by_label("Girişi yeni pencerede elle yapacağım").check()
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        wait = ui.locator("#pd-fresh-wait")
        await expect(wait).to_contain_text("Elle giriş bekleniyor", timeout=15000)
        await panel.get_by_role("button", name="Giriş yaptım, devam et").click()
        await expect(wait).to_contain_text("giriş ekranında", timeout=10000)
        await expect(status).not_to_contain_text("BAŞARILI")
        verification = next(r for r in sessions._records.values() if r.purpose == "verification")
        await in_server(lab_login(verification.handle.page))
        await panel.get_by_role("button", name="Giriş yaptım, devam et").click()
        await expect(status).to_contain_text("Yeni oturum testi tamamlandı: BAŞARILI", timeout=40000)
        await expect(wait).to_have_count(0)
        assert not [r for r in sessions._records.values() if r.purpose == "verification"]
        await expect(panel).to_contain_text("Eksik yok: incelemeye hazır.")
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await expect(panel.locator("#pd-approval-state")).to_contain_text("geçerli")
        await panel.get_by_role("button", name="Yayımla").click()
        await expect(status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)
        release = re.search(r"rel-[A-Za-z0-9_-]+", await status.inner_text())
        assert release is not None
        listing = await (await ui.request.get(f"{base}/api/catalogs/releases?application_id=lab")).json()
        assert listing["active_release_id"] == release[0]

        # 6) İşlem Asistanı (aynı AgenTask oturumu ve hedef oturumu).
        await ui.goto(f"{base}/assistant")
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await ui.get_by_role("button", name="Uygulamayı oturumda aç").click()
        await expect(ui.locator(".as-session")).to_contain_text("Uygulama açıldı", timeout=10000)

        async def reopen() -> None:
            await handle.page.get_by_role("link", name="Seçim senaryoları").click()
            await handle.page.get_by_role("region", name="Kefil").get_by_label("Ad Soyad").wait_for()

        await in_server(reopen())
        fresh = await in_server(page_fields(handle.page))
        assert fresh == baseline  # başlangıç koşulu: yeni açılan ekran boş
        await ui.locator(".as-ready-wrap summary").click()
        await ui.locator(".as-ready").get_by_role("button", name="Şirket adayı akışı").click()
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-plan")).to_contain_text("yalnız ekran alanları")
        await expect(ui.locator(".as-ack-wrap")).to_be_hidden()
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=40000)
        assert changed_fields(fresh, await in_server(page_fields(handle.page))) == expected_change
        support = (await ui.locator(".as-support").inner_text()).split(": ", 1)[1]

        async def field(section: str, label: str) -> str:
            return str(
                await handle.page.get_by_role("region", name=section).get_by_label(label).input_value()
            )

        assert await in_server(field("Kefil", "Ad Soyad")) == "Test Kefil"
        assert await in_server(field("Başvuran", "Ad Soyad")) == "Test Kefil"
        assert await in_server(field("Ürün", "Merkez Kodu")) == "M01"

        # 7) Geçmiş ve çıkış.
        await ui.goto(f"{base}/runs")
        await expect(ui.locator(".rn-list")).to_contain_text("Şirket adayı akışı")
        await ui.locator(".rn-list").get_by_role("button", name="Ayrıntı").first.click()
        await expect(ui.locator(".rn-support")).to_have_text(f"Destek numarası: {support}")
        await ui.get_by_role("button", name="Çıkış").click()
        await expect(ui).to_have_url(f"{base}/login")
        await ui.goto(f"{base}/runs")
        await expect(ui).to_have_url(f"{base}/login?next=/runs")
        await browser.close()

    text = json.dumps(json_logs(), ensure_ascii=False)
    assert PASSWORD not in text and "agentask_admin_session" not in text
    assert "pega.kullanici" not in text and "Test Kefil" not in text
    events = {x["event"] for x in json_logs()}
    assert {"auth_login", "auth_logout", "draft_saved", "draft_approved", "release_published"} <= events
