"""R4 uçtan uca (gerçek Chromium + geçici mongod, testlere özel veritabanı): arayüzden iki ekranlı
işlem tasarımı
(ekranlar, başlangıç bağlamı, onaylı geçiş, adım denemeleri) → yeni oturum testi → onay → yayın → asistandan
çalıştırma. JSON/API yazılmaz; yalnız ekran öğeleri kullanılır."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import Locator, Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_browser import ui_engine
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
VALUES = {"vaka_no": "C-2001", "musteri_no": "00456", "tutar": "1500"}


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
            MONGO_DATABASE="agentask_e2e_r4",
            READINESS_TIMEOUT_MS="2500",
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()


async def open_page(ui: Page, value: str, path: str) -> None:
    await ui.locator(".dz-nav [name=lab_page]").select_option(value)
    await ui.get_by_role("button", name="Ekranı aç").click()
    await expect(ui.locator(".dz-session")).to_contain_text(path)


async def define_screen(
    ui: Page, screen_id: str, title: str, markers: list[str], absent: tuple[str, str]
) -> None:
    form = ui.locator(".dz-screen-form")
    await form.locator("[name=screen_id]").fill(screen_id)
    await form.locator("[name=title]").fill(title)
    await form.get_by_role("button", name="Ekrandaki kontrolleri listele").click()
    for caption in markers:
        await form.locator(".dz-screen-controls li").filter(has_text=caption).first.locator("input").check()
    await form.locator("[name=absent_label]").fill(absent[0])
    await form.locator("[name=absent_region]").fill(absent[1])
    await form.get_by_role("button", name="Ekran tanımını doğrula ve kaydet").click()
    await expect(ui.locator(f".dz-screen-item[data-screen-id={screen_id}]")).to_contain_text(title)
    await expect(ui.locator(".dz-screen .dz-verdict")).to_contain_text("TANINDI")


def card(ui: Page, index: int) -> Locator:
    return ui.locator(".dz-card").nth(index)


async def confirm_and_try(ui: Page, index: int, ack: bool = False) -> None:
    c = card(ui, index)
    for name in ("meaning", "target", "effect", "params"):
        await c.locator(f".dz-confirm [name={name}]").check()
    await c.get_by_role("button", name="Onayla").click()
    c = card(ui, index)
    for name, value in VALUES.items():
        await c.locator(f"[name=arg_{name}]").fill(value)
    if ack:
        await expect(c.locator(".dz-ack")).to_contain_text("ekran geçişini tetikler")
        await c.get_by_role("button", name="Dene").click()
        await expect(ui.locator(".tl-error")).to_contain_text("ekran geçişini tetikler")  # onaysız tıklanmaz
        await c.locator(".dz-trial [name=ack]").check()
    await c.get_by_role("button", name="Dene").click()
    c = card(ui, index)
    await expect(c).to_contain_text("sistem doğrulaması: BAŞARILI", timeout=20_000)
    await c.get_by_role("button", name="Sonucu onayla").click()
    await expect(card(ui, index)).to_contain_text("İncelemeye hazır")


async def add_value_step(ui: Page, index: int, intent: str, candidate: str, template: str) -> None:
    await ui.locator(".dz-step [name=intent_text]").fill(intent)
    await ui.get_by_role("button", name="Adım ekle").click()
    c = card(ui, index)
    await c.get_by_role("button", name="Hedef adaylarını göster").click()
    await (
        c.locator(".dz-candidates li")
        .filter(has_text=candidate)
        .first.get_by_role("button", name="Bu hedefi seç")
        .click()
    )
    c = card(ui, index)
    await c.locator("[name=template]").fill(template)
    await c.get_by_role("button", name="Tanımı kaydet").click()
    await expect(card(ui, index)).to_contain_text("Hedef seçildi")


async def test_multi_screen_designed_published_and_run_from_ui(app_server: AppServer, lab: LabServer) -> None:
    base = f"http://127.0.0.1:{app_server.port}"
    async with async_playwright() as p:
        browser = await ui_engine(p).launch()
        ui = await browser.new_page()
        await ui.goto(f"{base}/designer")
        await ui.get_by_role("button", name="Yeni oturum aç").click()
        await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")
        await open_page(ui, "/wizard/C-2001", "/wizard/C-2001")

        create = ui.locator(".dz-create")
        await create.locator("[name=operation_id]").fill("teminat_gir")
        await create.locator("[name=title]").fill("Teminat tutarını gir")
        await create.get_by_role("button", name="Yeni taslak").click()
        await expect(ui.locator(".dz-title")).to_contain_text("teminat_gir")
        for name, title in (
            ("vaka_no", "Vaka No"),
            ("musteri_no", "Müşteri No"),
            ("tutar", "Teminat Tutarı"),
        ):
            param = ui.locator(".dz-param")
            await param.locator("[name=name]").fill(name)
            await param.locator("[name=title]").fill(title)
            await param.get_by_role("button", name="Parametre ekle").click()
            await expect(ui.locator(".dz-params")).to_contain_text("{" + name + "}")

        # Ekranlar: başlangıç (müşteri) ve teminat; teminat ekranına tasarım oturumunda doğrudan gidilir.
        await define_screen(
            ui,
            "basvuru_musteri",
            "Başvuru — müşteri seçimi",
            ["Vaka No · metin alanı · Vaka", "Müşteri No · metin alanı · Müşteri", "Devam · düğme"],
            ("Teminat Tutarı", "Teminat"),
        )
        ctx = ui.locator(".dz-context-form")
        await ctx.locator("[name=s_label]").fill("Vaka No")
        await ctx.locator("[name=s_region]").fill("Vaka")
        await ctx.locator("[name=s_template]").fill("{vaka_no}")
        await ctx.get_by_role("button", name="Başlangıç bağlamını kaydet").click()
        await expect(ui.locator(".dz-start-context")).to_contain_text("Vaka No = {vaka_no}")

        await open_page(ui, "/wizard/C-2001/collateral", "/collateral")
        await define_screen(
            ui,
            "basvuru_teminat",
            "Başvuru — teminat bilgileri",
            ["Vaka No · metin alanı · Vaka", "Gönder · düğme · Teminat"],
            ("Müşteri No", "Müşteri"),
        )

        # Geçiş: tetikleyici kaynak ekranda yalnız listelenir/seçilir; tanım sırasında tıklanmaz.
        await open_page(ui, "/wizard/C-2001", "/wizard/C-2001")
        tf = ui.locator(".dz-transition-form")
        await tf.locator("[name=transition_id]").fill("teminata_gec")
        await tf.locator("[name=from_screen]").select_option("basvuru_musteri")
        await tf.locator("[name=to_screen]").select_option("basvuru_teminat")
        await tf.locator("[name=timeout_ms]").fill("5000")
        await tf.get_by_role("button", name="Tetikleyici adaylarını listele").click()
        await tf.locator(".dz-trigger-controls li").filter(has_text="Devam").locator("input").check()
        await tf.locator("[name=c_label]").fill("Vaka No")
        await tf.locator("[name=c_region]").fill("Vaka")
        await tf.locator("[name=c_template]").fill("{vaka_no}")
        await tf.get_by_role("button", name="Geçişi kaydet").click()
        await expect(ui.locator(".dz-routes")).to_contain_text(
            "teminata_gec: Başvuru — müşteri seçimi → Başvuru — teminat bilgileri"
        )
        assert lab.control("GET", "/__lab/state").json()["wizard_advances"] == {}  # tanım tıklamadı

        # Adım 1 (müşteri ekranı), adım 2 (onaylı geçiş), adım 3 (teminat ekranı).
        await add_value_step(ui, 0, "Müşteri numarasını yaz", "Müşteri", "{musteri_no}")
        await confirm_and_try(ui, 0)
        await ui.locator(".dz-step [name=intent_text]").fill("Devam et")
        await ui.get_by_role("button", name="Adım ekle").click()
        c = card(ui, 1)
        await expect(c).to_contain_text("Ekran geçişi (onaylı düğme/sekme)")
        await c.locator("[name=transition_id]").select_option("teminata_gec")
        await c.get_by_role("button", name="Tanımı kaydet").click()
        await expect(card(ui, 1)).to_contain_text("EKRAN DEĞİŞTİRİR")
        await expect(card(ui, 1)).to_contain_text("→ geçiş: Başvuru — teminat bilgileri")
        await confirm_and_try(ui, 1, ack=True)
        assert lab.control("GET", "/__lab/state").json()["wizard_advances"] == {"C-2001": 1}
        await add_value_step(ui, 2, "Teminat tutarını yaz", "Teminat Tutarı", "{tutar}")
        await expect(card(ui, 2)).to_contain_text("Beklenen ekran: Başvuru — teminat bilgileri")
        await confirm_and_try(ui, 2)

        # Yeni oturum testi bütün akışı baştan sona çalıştırır.
        await ui.locator("[name=entry]").select_option("/wizard/C-2001")
        for name, value in VALUES.items():
            await ui.locator(f"[name=fresh_{name}]").fill(value)
        await ui.get_by_role("button", name="Yeni oturum testi").click()
        await expect(ui.locator(".dz-review")).to_contain_text(
            "İncelemeye hazır: bütün adımlar doğrulandı", timeout=40_000
        )
        await ui.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("Onaylandı")
        await ui.get_by_role("button", name="Yayımla").click()
        await expect(ui.locator(".dz-publish")).to_contain_text("teminat_gir r1")
        assert lab.control("GET", "/__lab/state").json()["wizard_advances"] == {"C-2001": 2}

        # Asistan: rota görünür, çalıştırma iki ekranı geçer.
        await ui.goto(f"{base}/assistant")
        await ui.locator("[name=prompt]").fill("Teminat tutarını gir")
        await ui.get_by_role("button", name="Yorumla").click()
        for name, value in VALUES.items():
            await ui.locator(f".as-args [name={name}]").fill(value)
        await ui.get_by_role("button", name="Planı göster").click()
        await expect(ui.locator(".as-route")).to_contain_text(
            "Başvuru — müşteri seçimi → Başvuru — teminat bilgileri"
        )
        await expect(ui.locator(".as-plan")).to_contain_text("→ ekran geçişi: Başvuru — teminat bilgileri")
        await ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await ui.locator("[name=lab_page]").select_option("/wizard/C-2001")
        await ui.get_by_role("button", name="Ekranı aç").click()
        await expect(ui.locator(".as-session")).to_contain_text("/wizard/C-2001")
        await ui.get_by_role("button", name="Başlat").click()
        await expect(ui.locator(".rl-run .badge")).to_have_text("Başarılı", timeout=30_000)
        await expect(ui.locator(".rl-steps")).to_contain_text("follow_transition")
        assert lab.control("GET", "/__lab/state").json()["wizard_advances"] == {
            "C-2001": 3
        }  # her çalıştırmada 1
        await browser.close()
