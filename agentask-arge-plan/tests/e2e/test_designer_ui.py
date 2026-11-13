"""Katalog Tasarımcısı ekranı uçtan uca: JSON/API yazmadan, modelsiz hazırlama ve incelemeye hazırlık."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import Page, async_playwright, expect

from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        RUN_DIRECTORY=str(tmp_path / "runs"),
        DRAFT_DIRECTORY=str(tmp_path / "drafts"),
    )
    server = AppServer(create_app(settings))
    server.start()
    yield server
    server.stop()


async def test_designer_screen_guided_authoring(app_server: AppServer, lab: LabServer) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page()
        await author_ready_draft(ui, app_server.port)
        await browser.close()


async def author_ready_draft(ui: Page, port: int) -> None:
    """Ekrandan, JSON yazmadan bir işlemi incelemeye hazır hale getirir (yayın testi de kullanır)."""
    await ui.goto(f"http://127.0.0.1:{port}/designer")
    await ui.get_by_role("button", name="Yeni oturum aç").click()
    await expect(ui.locator(".sp-current")).to_contain_text("Seçili oturum:")
    await ui.locator("[name=lab_page]").select_option("/pages/duplicates")
    await ui.get_by_role("button", name="Ekranı aç").click()
    await expect(ui.locator(".dz-session")).to_contain_text("/pages/duplicates")

    create = ui.locator(".dz-create")
    await create.locator("[name=operation_id]").fill("kefil_musteri_no")
    await create.locator("[name=title]").fill("Kefil müşteri numarasını gir")
    await create.get_by_role("button", name="Yeni taslak").click()
    await expect(ui.locator(".dz-title")).to_contain_text("kefil_musteri_no")

    param = ui.locator(".dz-param")
    await param.locator("[name=name]").fill("musteri_no")
    await param.locator("[name=title]").fill("Müşteri No")
    await param.get_by_role("button", name="Parametre ekle").click()
    await expect(ui.locator(".dz-params")).to_contain_text("{musteri_no}")

    await ui.locator(".dz-step [name=intent_text]").fill("Kefil müşteri numarasını yaz")
    await ui.get_by_role("button", name="Adım ekle").click()
    card = ui.locator(".dz-card").first
    await expect(card).to_contain_text("Değer yaz (rule_generated)")
    # U1: taslak listesi sayfa yenilenmeden adım sayısını gösterir.
    await expect(ui.locator(".dz-drafts li").filter(has_text="kefil_musteri_no")).to_contain_text("1 adım")

    await card.get_by_role("button", name="Hedef adaylarını göster").click()
    kefil = card.locator(".dz-candidates li").filter(has_text="Kefil").first
    await expect(kefil).to_be_visible()
    await expect(card.locator(".dz-candidates li").filter(has_text="Başvuran")).to_have_count(1)
    await kefil.get_by_role("button", name="Bu hedefi seç").click()
    card = ui.locator(".dz-card").first
    await expect(card).to_contain_text("Hedef seçildi")
    await expect(card).to_contain_text("bölüm Kefil")

    await card.locator("[name=template]").fill("{musteri_no}")
    await card.get_by_role("button", name="Tanımı kaydet").click()
    card = ui.locator(".dz-card").first
    await expect(card).to_contain_text("alanına {musteri_no} değerini yaz")

    for name in ("meaning", "target", "params"):
        await card.locator(f".dz-confirm [name={name}]").check()
    await card.get_by_role("button", name="Onayla").click()
    await expect(ui.locator(".tl-error")).to_contain_text("mevcut durumda")  # etki onayı eksik
    await card.locator(".dz-confirm [name=effect]").check()
    await card.get_by_role("button", name="Onayla").click()
    card = ui.locator(".dz-card").first
    await expect(card).to_contain_text("Anlam ve hedef onaylandı")

    await card.locator("[name=arg_musteri_no]").fill("00123")
    await card.get_by_role("button", name="Dene").click()
    card = ui.locator(".dz-card").first
    await expect(card).to_contain_text("sistem doğrulaması: BAŞARILI", timeout=20_000)
    await card.get_by_role("button", name="Sonucu onayla").click()
    await expect(ui.locator(".dz-card").first).to_contain_text("İncelemeye hazır")

    await expect(ui.locator(".dz-issues")).to_contain_text("Yeni oturum testi yapılmadı")
    await define_parties_screen(ui)
    await ui.locator("[name=entry]").select_option("/pages/duplicates")
    await ui.locator("[name=fresh_musteri_no]").fill("00999")
    await ui.get_by_role("button", name="Yeni oturum testi").click()
    await expect(ui.locator(".dz-review")).to_contain_text(
        "İncelemeye hazır: bütün adımlar doğrulandı", timeout=30_000
    )


async def define_parties_screen(ui: Page) -> None:
    """Ekran tanımı: güncel ekrandaki kontrollerden işaret seçimi + 'olmamalı' işareti; canlı doğrulanır."""
    await expect(ui.locator(".dz-issues")).to_contain_text("Ekran tanımı yok")
    form = ui.locator(".dz-screen-form")
    await form.locator("[name=screen_id]").fill("basvuru_taraflar")
    await form.locator("[name=title]").fill("Başvuru — taraf bilgileri")
    await form.get_by_role("button", name="Ekrandaki kontrolleri listele").click()
    controls = form.locator(".dz-screen-controls li")
    await controls.filter(has_text="Müşteri No · metin alanı · Başvuran").locator("input").check()
    await controls.filter(has_text="Ad Soyad · metin alanı · Kefil").locator("input").check()
    await form.locator("[name=absent_label]").fill("Talep Notu")
    await form.locator("[name=absent_region]").fill("Kefil")
    await form.get_by_role("button", name="Ekran tanımını doğrula ve kaydet").click()
    await expect(ui.locator(".dz-screen .dz-verdict")).to_contain_text("TANINDI")
    await expect(ui.locator(".dz-screen")).to_contain_text("bölgeler: Başvuran, Kefil")
    await expect(ui.locator(".dz-screen")).to_contain_text('Olmamalı: textbox "Talep Notu" · bölüm Kefil')
    await expect(ui.locator(".dz-issues")).not_to_contain_text("Ekran tanımı yok")
    await expect(ui.locator(".dz-drafts li").filter(has_text="kefil_musteri_no")).to_contain_text(
        "ekran basvuru_taraflar"
    )


async def test_form_validation_explains_field_and_reason(app_server: AppServer, lab: LabServer) -> None:
    """U2: hatalı parametre formunda hangi alanın neden hatalı olduğu Türkçe gösterilir."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ui = await browser.new_page()
        await ui.goto(f"http://127.0.0.1:{app_server.port}/designer")
        create = ui.locator(".dz-create")
        await create.locator("[name=operation_id]").fill("Kefil No")
        await create.locator("[name=title]").fill("Kefil")
        await create.get_by_role("button", name="Yeni taslak").click()
        errors = ui.locator(".tl-error .dz-field-errors li")
        await expect(errors.first).to_contain_text("İşlem kimliği: küçük harfle başlamalı")
        await create.locator("[name=operation_id]").fill("kefil_no")
        await create.get_by_role("button", name="Yeni taslak").click()
        await expect(ui.locator(".dz-title")).to_contain_text("kefil_no")
        param = ui.locator(".dz-param")
        await param.locator("[name=name]").fill("Müşteri No")
        await param.locator("[name=title]").fill("Müşteri No")
        await param.locator("[name=max_length]").fill(
            "600"
        )  # sunucu sınırı 500 (tarayıcı min=1 kontrolü geçer)
        await param.get_by_role("button", name="Parametre ekle").click()
        await expect(errors.filter(has_text="Ad:")).to_contain_text("küçük harfle başlamalı")
        await expect(errors.filter(has_text="En fazla:")).to_contain_text("500 veya daha küçük olmalı")
        await expect(ui.locator(".tl-error")).not_to_contain_text("Müşteri No")  # girilen değer yansıtılmaz
        await browser.close()
