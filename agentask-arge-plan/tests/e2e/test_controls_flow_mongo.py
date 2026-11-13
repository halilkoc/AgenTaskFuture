"""Onay kutusu + seçenek grubu + öneri alanı: tasarımdan İşlem Asistanı'na (lab + MongoDB)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright, expect

from tests.conftest import EnvFileFactory
from tests.e2e.flow_helpers import Flow, changed_fields, mongo_app, open_flow
from tests.e2e.support import AppServer
from tests.support_lab import LabServer

pytestmark = [pytest.mark.browser, pytest.mark.mongo]
PAGE = "/pages/controls"
FAILED = re.compile("Başarısız|Tamamlanamadı")
UNKNOWN = "Belirsiz"


@pytest.fixture
def app_server(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> Iterator[AppServer]:
    yield from mongo_app(make_env_file, lab, tmp_path, "agentask_controls")


async def page_state(flow: Flow) -> tuple[bool, bool, str, str | None]:
    async def read() -> tuple[bool, bool, str, str | None]:
        page = flow.handle.page
        start = page.get_by_role("region", name="Başvuru")
        city = page.get_by_role("region", name="Arama").get_by_label("Şehir", exact=True)
        return (
            await start.get_by_label("Onaylıyorum").is_checked(),
            await start.get_by_label("Şube").is_checked(),
            await city.input_value(),
            await city.get_attribute("data-value"),
        )

    result: tuple[bool, bool, str, str | None] = await flow.in_server(read())
    return result


async def test_checkbox_radio_autocomplete_from_design_to_assistant(
    app_server: AppServer, lab: LabServer
) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        flow = await open_flow(browser, app_server, lab, "Kontrolleri doldur", PAGE)

        editor = await flow.pick("İşaretle / kaldır", "Başvuru bölümündeki Onaylıyorum alanını seç")
        await editor.get_by_label("İşaretli olsun").check()
        await editor.get_by_label("Yalnız bu kutunun durumunu değiştirir").check()

        editor = await flow.pick("Seçim yap", "Başvuru bölümündeki Teslimat alanını seç")
        await expect(editor.locator("ul[id$='-options']")).to_contain_text("Şube")
        await editor.get_by_label("Sabit seçenek").check()
        await editor.get_by_label("Seçilecek seçenek").select_option(label="Şube")
        await editor.get_by_label("Yalnız bu alanın seçimini değiştirir").check()

        editor = await flow.add("Seçim yap")
        await editor.get_by_label("Bu alan yazınca öneri açıyor").check()
        await editor.get_by_role("button", name="Ekrandaki alanları listele").click()
        await editor.get_by_role("button", name="Arama bölümündeki Şehir alanını seç").click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        await editor.get_by_label("Örnek arama metni").fill("Ank")
        await editor.get_by_role("button", name="Örnek ara ve önerileri oku").click()
        await expect(editor.locator("ul[id$='-options']")).to_contain_text("Ankara Merkez", timeout=10000)
        assert (await page_state(flow))[2:] == ("", None)  # örnek arama alanı değiştirmeden bıraktı
        await editor.get_by_label("Her çalıştırmada sor").check()

        await flow.save()
        cards = await flow.reopen()
        await expect(cards).to_have_count(3)
        await cards.nth(0).click()
        await expect(flow.editor.get_by_label("İşaretli olsun")).to_be_checked()
        await cards.nth(2).click()
        await expect(flow.editor.get_by_label("Bu alan yazınca öneri açıyor")).to_be_checked()

        await flow.introduce_screen()
        arg = flow.panel.locator("input[id^='pd-arg-']")
        await arg.fill("Ankara Merkez")
        for i in range(3):
            await flow.confirm_and_try(i)
        assert await page_state(flow) == (True, True, "Ankara Merkez", "ANK")

        await arg.fill("Ankara Merkez")
        await flow.publish(PAGE)
        await flow.assistant_open(flow.name, PAGE)
        await flow.ui.locator(".as-args input").first.fill("Antalya Merkez")
        fresh = await flow.fields()
        await flow.assistant_start(ack=True)
        assert await page_state(flow) == (True, True, "Antalya Merkez", "ANT")
        assert changed_fields(fresh, await flow.fields()) == {
            "Başvuru › Onaylıyorum": True,
            "Başvuru › Şube": True,
            "Arama › Şehir": "Antalya Merkez",
        }  # Kefil bölümündeki aynı adlı alanlar değişmedi

        async def read_counts() -> tuple[Any, Any, int]:
            page = flow.handle.page
            start = page.get_by_role("region", name="Başvuru")
            return (
                await start.get_by_label("Onaylıyorum").get_attribute("data-clicks"),
                await start.get_by_label("Şube").get_attribute("data-clicks"),
                await page.evaluate("window.__autoSearches"),
            )

        async def counts() -> tuple[Any, Any, int]:
            # Hedef sayfa uygulama sunucusunun döngüsündedir; doğrudan beklenirse yanıt hiç
            # dönmez (2026-11-13 takılma teşhisi).
            result: tuple[Any, Any, int] = await flow.in_server(read_counts())
            return result

        # Aynı değerle ikinci çalıştırma: kutu, radyo ve arama için sıfır yeni işlem.
        once = await counts()
        assert once[:2] == ("1", "1")
        city = flow.ui.locator(".as-args input").first
        await city.fill("Antalya Merkez")
        await flow.assistant_start(ack=True)
        assert await counts() == once

        # Öneri yok: metin geri yazılır ama alandaki gerçek seçim (ANT) kaybolur; ürün bunu “döndü” saymaz,
        # sonuç belirsizdir. Kutu ve radyo yeniden tıklanmaz.
        await city.fill("Yok Böyle")
        await flow.assistant_start(ack=True, expected=UNKNOWN)
        assert await page_state(flow) == (True, True, "Antalya Merkez", None)
        assert (await counts())[:2] == once[:2]
        # İki eşleşme: alan şimdi seçimsiz; eski hali (metin, değer yok) okunarak doğrulanır, sonuç başarısız.
        await city.fill("Çift Şube")
        await flow.assistant_start(ack=True, expected=FAILED)
        assert await page_state(flow) == (True, True, "Antalya Merkez", None)
        assert (await counts())[:2] == once[:2]
        await browser.close()
