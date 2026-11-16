"""“Seçim yap” kabulü (gerçek Chromium + lab + geçici MongoDB): alan seç → tanımla → kaydet → yeniden aç →
gerçek deneme → sonuç onayı → yeni oturum testi → yayın → İşlem Asistanı. Lab; Pega uyumluluğu değildir."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.layout_probe import probe
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
OWNER = "dev.user"
PATH = "/pages/selections"


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
            MONGO_DATABASE="agentask_choice",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()
        lab.reset()


async def open_left(ui: Page) -> None:
    if await ui.locator("#pd-left").evaluate("e => e.classList.contains('is-collapsed')"):
        await ui.locator("#pd-left-toggle").click()


async def add_choice(ui: Page, field_name: str, *, open_list: bool = False) -> Any:
    editor = ui.locator("#pd-editor")
    await ui.locator("#pd-components").get_by_role("button", name="Seçim yap").click()
    await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
    await editor.get_by_role("button", name=field_name).click()
    await expect(editor.locator("[id$='-check']")).to_have_text("Ekranda tek olarak bulundu.", timeout=10000)
    if open_list:
        await expect(editor.get_by_role("button", name="Listeyi aç ve seçenekleri oku")).to_be_visible(
            timeout=10000
        )
        await editor.get_by_role("button", name="Listeyi aç ve seçenekleri oku").click()
    await expect(editor.locator(".pd-optlist")).to_be_visible(timeout=10000)
    return editor


async def test_choice_component_end_to_end(app_server: AppServer, lab: LabServer) -> None:
    sessions = app_server.app.state.container.sessions
    loop = asyncio.get_running_loop()

    async def in_server(coro: Coroutine[Any, Any, Any]) -> Any:
        return await loop.run_in_executor(None, app_server.run, coro)

    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        # Dar masaüstü penceresi: bütün akış bu genişlikte tamamlanır.
        ui = await browser.new_page(viewport={"width": 1100, "height": 900})
        await ui.goto(f"{base}/prototype/designer")
        await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
        await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill("Başvuru seçimleri")
        await open_left(ui)
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
        sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
        handle = sessions.peek(OWNER, sid)
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"))

        # 1) Sabit seçenek (standart select, aynı etiketli alanlar bölümle ayrılır)
        editor = await add_choice(ui, "Kefil bölümündeki Şube alanını seç")
        options = editor.locator(".pd-optlist")
        await expect(options).to_contain_text("Kapalı Şube (devre dışı)")
        await expect(options).to_contain_text("Yinelenen Şube (yinelenen; seçilemez)")
        await editor.get_by_label("Sabit seçenek").check()
        await editor.get_by_label("Seçilecek seçenek").select_option(label="Konak")
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()
        await expect(editor.locator("#pd-ed-summary")).to_contain_text("“Konak” seçeneğini seç")
        selected = await ui.evaluate("() => document.querySelector('#pd-editor select option:checked').value")
        assert selected == "Konak"  # analist teknik değer veya sıra numarası görmez
        assert await sessions_value(in_server, handle, "Kefil", "Şube") == ""  # tanımlama seçim yapmaz

        # 2) Her çalıştırmada sor (özel liste; okumak ayrı, açık kullanıcı eylemi)
        editor = await add_choice(ui, "Ürün bölümündeki Ürün Tipi alanını seç", open_list=True)
        await expect(editor.locator(".pd-optlist")).to_contain_text("Kapalı Kart (devre dışı)")
        await editor.get_by_label("Her çalıştırmada sor").check()
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()

        # 3-4) Önceki okuma çıktısı
        await ui.locator("#pd-components").get_by_role("button", name="Bilgi oku").click()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Kefil bölümündeki Şube alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        editor = await add_choice(ui, "Başvuran bölümündeki Şube alanını seç")
        await editor.get_by_label("Önceki adımın çıktısı").check()
        await editor.get_by_label("Hangi adımın değeri?").select_option(index=1)
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()

        # 5) Etkisi bilinmeyen, listesi değişebilen seçim + durum mesajı koşulu
        editor = await add_choice(ui, "Kayıt Etkili bölümündeki Öncelik alanını seç")
        await editor.get_by_label("Her çalıştırmada sor").check()
        await editor.get_by_label("Seçenekler kayda veya ekrana göre değişebilir").check()
        await editor.get_by_label("Kayıt veya ekran değişikliği tetikleyebilir / emin değilim").check()
        await expect(editor.get_by_label("Ek kontrol yapma")).to_be_disabled()
        await editor.get_by_label("Ekranda görünmesi gereken durum mesajı").fill("Öncelik güncellendi")

        await ui.evaluate(
            "document.querySelectorAll('.pd-toast').forEach((t) => t.remove())"
        )  # geçici bildirim
        found = await probe(ui)
        # Kapalı “Ayrıntılar” içindeki not alanı görünür değildir; ölçüm onu yanlışlıkla örtülü sayar.
        found["covered"] = [c for c in found["covered"] if "-note" not in c]
        bad = {k: v for k, v in found.items() if v}
        assert not bad, bad

        await ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)

        # Kalıcı kayıt: yeniden açınca bütün değer kaynakları ve etki beyanları korunur.
        await ui.reload()
        await ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await ui.get_by_role("button", name="“Başvuru seçimleri” taslağını aç").click()
        cards = ui.locator(".pd-card")
        await expect(cards).to_have_count(5)
        await expect(cards.nth(0)).to_contain_text("Sabit seçenek: “Konak”")
        await expect(cards.nth(1)).to_contain_text("Sorulur:")
        await expect(cards.nth(3)).to_contain_text("Önceki adımdan")
        await cards.nth(4).locator(".pd-card__main").click()
        editor = ui.locator("#pd-editor")
        await expect(
            editor.get_by_label("Kayıt veya ekran değişikliği tetikleyebilir / emin değilim")
        ).to_be_checked()
        await expect(editor.get_by_label("Ekranda görünmesi gereken durum mesajı")).to_have_value(
            "Öncelik güncellendi"
        )
        await expect(ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi")
        await open_left(ui)
        await ui.get_by_role("button", name="Gerçek oturum").click()
        await expect(ui.get_by_label("Tarayıcı oturumu")).to_have_value(sid, timeout=10000)

        panel = ui.locator("#pd-runpanel")
        await panel.get_by_role("button", name="Ekranı tanıt").click()
        await panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(panel).to_contain_text("Tanımlı:", timeout=15000)

        steps = panel.locator(".pd-live__step")
        await expect(steps).to_have_count(5)
        for i in range(5):
            step = steps.nth(i)
            for box in await step.locator("[data-ack]").all():
                await box.check()
            await step.get_by_role("button", name="Onayla", exact=True).click()
            await expect(step).to_contain_text("Denemeye hazır", timeout=10000)
        await expect(steps.nth(4).locator(".pd-check-row")).to_contain_text("işlem yapabilir")

        await panel.locator("select[id^='pd-arg-']").select_option(label="Ticari Kart")
        await panel.locator("input[id^='pd-arg-']").fill("Yüksek")
        for i in range(5):
            step = steps.nth(i)
            await step.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
            await step.get_by_role("button", name="Gerçek dene").click()
            await expect(step).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=25000)
            await step.get_by_role("button", name="Sonucu onayla").click()
            await expect(step).to_contain_text("Hazır", timeout=10000)

        assert await sessions_value(in_server, handle, "Kefil", "Şube") == "konak"
        assert await sessions_value(in_server, handle, "Başvuran", "Şube") == "konak"
        trial_commits = lab.control("GET", "/__lab/state").json()["selection_commits"]
        assert trial_commits == ["Y"]

        await panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill(PATH)
        run_status = ui.locator("#pd-runpanel-status")
        await panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(run_status).to_contain_text("Yeni oturum testi tamamlandı", timeout=40000)
        await expect(panel).to_contain_text("Eksik yok: incelemeye hazır.")
        await panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(run_status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await panel.get_by_role("button", name="Yayımla").click()
        await expect(run_status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)

        # İşlem Asistanı: sabit listede seçim, değişken listede açık ekrandan güncel seçenek.
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"))
        await ui.goto(f"{base}/assistant")
        await expect(ui.locator(".as-llm")).to_contain_text("Etkin yayında 1 işlem")
        await expect(ui.locator(".as-ack-wrap")).to_be_hidden()  # plan yokken etki onayı görünmez
        await ui.locator(".as-ready-wrap summary").click()
        await ui.locator(".as-ready").get_by_role("button", name="Başvuru seçimleri").click()
        form = ui.locator(".as-args")
        fixed_list = form.locator("select")
        await expect(fixed_list).to_have_count(1)
        assert "Kapalı Kart" not in await fixed_list.inner_text()
        await fixed_list.select_option(label="Bireysel Kart")
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await form.get_by_role("button", name="Ekrandaki güncel seçenekleri getir").click()
        await expect(form.locator("select")).to_have_count(2, timeout=10000)
        await form.locator("select").nth(1).select_option(label="Normal")
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-bindings")).to_contain_text("Bireysel Kart")
        await expect(ui.locator(".as-plan")).not_to_contain_text("Gerçek oturumda seçildi")
        start = ui.get_by_role("button", name="Başlat")
        await expect(ui.locator(".as-ack-wrap")).to_be_visible()
        await expect(ui.locator(".as-ack-wrap")).to_contain_text("tetikleyebilir")
        before = lab.control("GET", "/__lab/state").json()["selection_commits"]
        await start.click()  # etkisi bilinmeyen seçim açık onaysız başlamaz (sunucu kuralı)
        await expect(ui.locator(".tl-error")).not_to_be_empty(timeout=10000)
        assert lab.control("GET", "/__lab/state").json()["selection_commits"] == before
        await ui.locator("[name=ack]").check()
        await start.click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=40_000)
        assert await sessions_value(in_server, handle, "Kefil", "Şube") == "konak"
        assert lab.control("GET", "/__lab/state").json()["selection_commits"][-1] == "N"
        await expect(ui.locator(".rl-run")).to_contain_text("Destek numarası:")

        # Başarısız çalıştırma anlaşılır neden gösterir; sonraki başarılı çalıştırmada eski hata kalmaz.
        await in_server(handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next={PATH}"))
        lab.control("PUT", "/__lab/scenario", json={"selection_outcome": "reject"})
        await in_server(handle.navigate(f"{lab.primary}{PATH}"))
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-bindings")).to_contain_text("Normal")
        await ui.locator("[name=ack]").check()
        await start.click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarısız", timeout=40_000)
        await expect(ui.locator(".as-failure")).to_contain_text("Neden:")
        await expect(ui.locator(".as-failure")).to_contain_text("Sonraki adım:")
        assert not await ui.locator(".as-run-tech").evaluate("e => e.open")

        lab.control("PUT", "/__lab/scenario", json={"selection_outcome": "ok"})
        await in_server(handle.navigate(f"{lab.primary}{PATH}"))
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-bindings")).to_contain_text("Normal")
        await ui.locator("[name=ack]").check()
        await start.click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=40_000)
        await expect(ui.locator(".as-failure")).to_have_count(0)
        await expect(ui.locator(".tl-error")).to_be_empty()

        # Çalışmalar ekranı: ad, durum, neden, destek numarası; teknik ayrıntı kapalı; kayıt yeri açık.
        await ui.goto(f"{base}/runs")
        await expect(ui.locator(".rn-storage")).to_contain_text("yeniden başlatıldığında korunur")
        rows = ui.locator(".rn-list tr")
        failed = rows.filter(has_text="Başarısız").first
        await expect(failed).to_contain_text("Başvuru seçimleri")
        await failed.get_by_role("button", name="Ayrıntı").click()
        detail = ui.locator(".rn-detail")
        await expect(detail.locator(".rn-stage")).to_contain_text("adım")
        await expect(detail.locator(".rn-reason")).to_contain_text("Neden:")
        await expect(detail.locator(".rn-next")).to_contain_text("Sonraki adım:")
        await expect(detail.locator(".rn-support")).to_contain_text("Destek numarası:")
        assert not await detail.locator(".rn-tech").evaluate("e => e.open")
        await browser.close()


async def sessions_value(in_server: Any, handle: Any, section: str, label: str) -> str:
    async def read() -> str:
        return str(await handle.page.get_by_role("region", name=section).get_by_label(label).input_value())

    return str(await in_server(read()))
