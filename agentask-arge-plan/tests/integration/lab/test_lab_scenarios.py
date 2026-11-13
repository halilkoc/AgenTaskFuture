"""Deney uygulaması senaryoları — gerçek Chromium ile. Bu uygulama gerçek Pega değildir."""

from __future__ import annotations

import time

import pytest
from playwright.async_api import Dialog, Page, expect

from tests.support_lab import LabServer

pytestmark = pytest.mark.browser


async def test_lab_banner_says_not_real_pega(page: Page, lab: LabServer) -> None:
    await page.goto(f"{lab.primary}/login")
    await expect(page.get_by_text("Deney uygulaması — gerçek Pega değildir")).to_be_visible()


async def test_pages_require_login(page: Page, lab: LabServer) -> None:
    await page.goto(f"{lab.primary}/pages/duplicates")
    assert page.url.startswith(f"{lab.primary}/login")


async def test_ids_change_on_every_load(logged_in: Page, lab: LabServer) -> None:
    async def ids() -> set[str]:
        await logged_in.goto(f"{lab.primary}/pages/duplicates")
        values = await logged_in.locator("[id]").evaluate_all("els => els.map(e => e.id)")
        return set(values)

    first, second = await ids(), await ids()
    assert len(first) >= 4
    assert first.isdisjoint(second)


async def test_duplicate_labels_present(logged_in: Page, lab: LabServer) -> None:
    await logged_in.goto(f"{lab.primary}/pages/duplicates")
    await expect(logged_in.get_by_label("Müşteri No")).to_have_count(2)
    await expect(logged_in.get_by_label("Ad Soyad")).to_have_count(2)
    await expect(logged_in.get_by_role("button", name="Kaydet")).to_have_count(2)
    for section in ("Başvuran", "Kefil"):
        region = logged_in.get_by_role("region", name=section)
        await expect(region.get_by_label("Müşteri No")).to_have_count(1)


async def test_nested_cross_origin_and_late_frames(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(late_frame_delay_ms=800)
    await logged_in.goto(f"{lab.primary}/pages/frames")
    level2 = logged_in.frame_locator("iframe[title='Vaka Ayrıntıları']").frame_locator(
        "iframe[title='Adres Bilgileri']"
    )
    await expect(level2.get_by_label("Adres")).to_be_visible()
    cross = logged_in.frame_locator("iframe[title='Müşteri Kaydı (dış sistem)']")
    await expect(cross.get_by_label("Müşteri No")).to_be_visible()

    urls = [f.url for f in logged_in.frames]
    assert any(u.startswith(f"{lab.secondary}/frames/cross") for u in urls)
    assert not any("/frames/late" in u for u in urls), "geç frame hemen oluşmamalı"

    late = logged_in.frame_locator("iframe[title='Ek Belgeler']")
    await expect(late.get_by_label("Belge No")).to_be_visible(timeout=5000)
    level2_frame = next(f for f in logged_in.frames if "/frames/level2" in f.url)
    assert level2_frame.parent_frame is not None
    assert "/frames/level1" in level2_frame.parent_frame.url
    assert level2_frame.parent_frame.parent_frame == logged_in.main_frame


async def test_native_and_custom_dropdown(logged_in: Page, lab: LabServer) -> None:
    await logged_in.goto(f"{lab.primary}/pages/dropdowns")
    await logged_in.get_by_label("Şube").select_option(label="Konak")
    await expect(logged_in.get_by_label("Şube")).to_have_value("konak")

    combo = logged_in.get_by_role("combobox", name="Ürün Tipi")
    await expect(combo).to_have_attribute("aria-expanded", "false")
    await expect(logged_in.get_by_role("listbox")).to_have_count(0)
    await combo.click()
    option = logged_in.get_by_role("option", name="Ticari Kart")
    await option.click()
    await expect(combo).to_contain_text("Ticari Kart")
    await expect(combo).to_have_attribute("aria-expanded", "false")
    await expect(logged_in.get_by_role("listbox")).to_have_count(0)


async def test_paged_table_covers_all_rows_once(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(table_rows=23, page_size=10)
    await logged_in.goto(f"{lab.primary}/pages/table-paged")
    keys: list[str] = []
    pages_seen = 0
    while True:
        pages_seen += 1
        table = logged_in.get_by_role("table", name="Başvurular")
        keys += await table.locator("tbody tr td:first-child").all_inner_texts()
        next_link = logged_in.get_by_role("link", name="Sonraki")
        if await next_link.count() == 0:
            break
        await next_link.click()
        await expect(logged_in.get_by_text(f"Sayfa {pages_seen + 1} / 3")).to_be_visible()
    assert pages_seen == 3
    assert len(keys) == 23 == len(set(keys))
    assert keys[0] == "B-1000"


async def test_scroll_table_loads_incrementally(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(table_rows=40, scroll_batch=15)
    await logged_in.goto(f"{lab.primary}/pages/table-scroll")
    rows = logged_in.get_by_role("table", name="Hareketler").locator("tbody tr")
    await expect(rows).to_have_count(15)
    region = logged_in.get_by_role("region", name="Hareketler listesi")
    done = logged_in.get_by_text("Tüm kayıtlar yüklendi")
    for _ in range(10):
        if await done.is_visible():
            break
        await region.evaluate("el => { el.scrollTop = el.scrollHeight; }")
        await logged_in.wait_for_timeout(150)
    await expect(done).to_be_visible()
    keys = await rows.locator("td:first-child").all_inner_texts()
    assert len(keys) == 40 == len(set(keys))


async def test_server_delay_applies_to_pages(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(delay_ms=700)
    started = time.monotonic()
    await logged_in.goto(f"{lab.primary}/pages/duplicates")
    assert time.monotonic() - started >= 0.7


async def test_delayed_reveal(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(reveal_delay_ms=800)
    await logged_in.goto(f"{lab.primary}/pages/delayed")
    await expect(logged_in.get_by_text("Yükleniyor…")).to_be_visible()
    await expect(logged_in.get_by_label("Talep Açıklaması")).to_have_count(0)
    await expect(logged_in.get_by_label("Talep Açıklaması")).to_be_visible(timeout=5000)
    await expect(logged_in.get_by_text("Yükleniyor…")).to_be_hidden()


async def test_modal_dialog_blocks_until_dismissed(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(dialog="modal")
    await logged_in.goto(f"{lab.primary}/pages/note-form")
    dialog = logged_in.get_by_role("dialog", name="Uyarı")
    await expect(dialog).to_be_visible()
    with pytest.raises(Exception):  # noqa: B017
        await logged_in.get_by_role("button", name="Kaydet").click(timeout=800)
    await dialog.get_by_role("button", name="Tamam").click()
    await expect(dialog).to_be_hidden()


async def test_native_dialog(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(dialog="native")
    messages: list[str] = []

    async def _accept(d: Dialog) -> None:
        messages.append(d.message)
        await d.accept()

    logged_in.on("dialog", _accept)
    await logged_in.goto(f"{lab.primary}/pages/note-form")
    await expect(logged_in.get_by_label("Not", exact=True)).to_be_visible()
    await logged_in.wait_for_timeout(200)
    assert messages == ["Bu vaka başka bir kullanıcı tarafından güncellendi."]


async def test_session_expiry_redirects_to_login(logged_in: Page, lab: LabServer) -> None:
    await logged_in.goto(f"{lab.primary}/pages/duplicates")
    lab.control("POST", "/__lab/sessions/expire").raise_for_status()
    await logged_in.goto(f"{lab.primary}/pages/duplicates")
    assert "/login" in logged_in.url and "reason=expired" in logged_in.url
    await expect(logged_in.get_by_text("Oturumunuz sona erdi")).to_be_visible()
    api = await logged_in.request.get(f"{lab.primary}/lab-api/rows?offset=0&limit=1")
    assert api.status == 401


async def test_lost_response_commits_but_page_shows_unknown(logged_in: Page, lab: LabServer) -> None:
    lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=4000, client_timeout_ms=1000)
    await logged_in.goto(f"{lab.primary}/pages/note-form")
    await logged_in.get_by_label("Not", exact=True).fill("Müşteri arandı")
    await logged_in.get_by_role("button", name="Kaydet").click()
    status = logged_in.get_by_role("status")
    await expect(status).to_have_text("Yanıt alınamadı — işlem sonucu bilinmiyor", timeout=5000)

    state = lab.control("GET", "/__lab/state").json()
    assert [c["text"] for c in state["commits"]] == ["Müşteri arandı"]
    assert state["commits"][0]["client_request_id"]
    assert state["scenario"]["lose_next_commit_response"] is False

    await logged_in.reload()
    await expect(logged_in.get_by_role("list", name="Mevcut notlar")).to_contain_text("Müşteri arandı")
    await logged_in.get_by_label("Not", exact=True).fill("İkinci not")
    await logged_in.get_by_role("button", name="Kaydet").click()
    await expect(status).to_have_text("Kaydedildi (Not #2)")


def test_control_api_rejects_unknown_fields(lab: LabServer) -> None:
    assert lab.control("PUT", "/__lab/scenario", json={"delay": 5}).status_code == 422
    assert lab.control("PUT", "/__lab/scenario", json={"delay_ms": -1}).status_code == 422
    assert lab.control("PUT", "/__lab/scenario", json={"dialog": "popup"}).status_code == 422


def test_reset_restores_defaults(lab: LabServer) -> None:
    lab.set_scenario(delay_ms=50, table_rows=3)
    lab.reset()
    scenario = lab.control("GET", "/__lab/state").json()["scenario"]
    assert scenario["delay_ms"] == 0 and scenario["table_rows"] == 57


async def test_autologin_sets_session_and_redirects(page: Page, lab: LabServer) -> None:
    await page.goto(f"{lab.primary}/__lab/autologin?user=demo&next=/pages/duplicates")
    assert page.url == f"{lab.primary}/pages/duplicates"
    await expect(page.get_by_text("Kullanıcı: demo")).to_be_visible()
    await page.goto(f"{lab.primary}/__lab/autologin?user=demo&next=//evil.example")
    assert page.url == f"{lab.primary}/"
