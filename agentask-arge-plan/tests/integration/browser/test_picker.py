"""Manuel seçim modu: sayfaya gerçek click/submit/değer değişikliği ulaşmaz (T22); vurgu; geç/iç içe frame."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from playwright.async_api import FrameLocator, Locator, Page

from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.observation import ObservationService
from agentask.domain.observation import ControlKind
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.integration.browser.helpers import login
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"


@pytest.fixture
async def ctx(
    factory: PlaywrightContextFactory, lab: LabServer
) -> AsyncIterator[tuple[ObservationService, str, Page]]:
    sessions = BrowserSessionService(factory, SessionLimits(max_sessions=2, max_per_user=1, idle_seconds=600))
    service = ObservationService(sessions, picker_wait_max_ms=5000)
    view = await sessions.open(OWNER)
    handle = sessions.peek(OWNER, view.session_id)
    await login(handle, lab)  # type: ignore[arg-type]
    yield service, view.session_id, handle.page  # type: ignore[attr-defined]


async def click_center(page: Page, locator: Locator) -> None:
    """Gerçek kullanıcı gibi ekrandaki konuma fare tıklaması (önce görünür alana kaydırılır)."""
    await locator.scroll_into_view_if_needed()
    box = await locator.bounding_box()
    assert box is not None
    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


async def picked_control(service: ObservationService, sid: str):  # type: ignore[no-untyped-def]
    event = await service.wait_pick(OWNER, sid, 3000)
    assert event is not None and event.candidate_id is not None, event
    snapshot = service.sessions.peek(OWNER, sid).observer.current_snapshot
    assert snapshot is not None and snapshot.revision == event.snapshot_revision
    control = snapshot.control(event.candidate_id)
    assert control is not None
    return control


async def test_picking_submit_button_does_not_submit(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/note-form")
    await page.get_by_label("Not", exact=True).fill("seçim modunda gönderilmemeli")
    await service.start_picker(OWNER, sid)
    await click_center(page, page.get_by_role("button", name="Kaydet"))
    control = await picked_control(service, sid)
    assert control.kind is ControlKind.BUTTON and control.accessible_name == "Kaydet"
    await asyncio.sleep(0.5)
    assert lab.control("GET", "/__lab/state").json()["commits"] == []
    assert await page.get_by_role("status").inner_text() == ""
    box = page.locator("[data-agentask-ui=highlight]")
    assert "Kaydet · düğme" in await box.inner_text()
    await service.stop_picker(OWNER, sid)


async def test_picker_blocks_typing_and_select_changes(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/dropdowns")
    branch = page.get_by_label("Şube")
    await page.get_by_role("tab", name="Teslimat").focus()
    await service.start_picker(OWNER, sid)
    await page.keyboard.press("Enter")
    await page.keyboard.type("abc")
    await click_center(page, branch)
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    control = await picked_control(service, sid)
    assert control.kind is ControlKind.SELECT and control.label == "Şube"
    assert await branch.input_value() == ""
    combo = page.get_by_role("combobox", name="Ürün Tipi")
    await click_center(page, combo)
    await asyncio.sleep(0.6)
    assert await combo.get_attribute("aria-expanded") == "false"
    assert await page.get_by_role("listbox").count() == 0
    combo_pick = await picked_control(service, sid)
    assert combo_pick.kind is ControlKind.COMBOBOX


async def test_picker_in_nested_and_cross_origin_frames(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    lab.set_scenario(late_frame_delay_ms=30_000)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/frames")
    level2: FrameLocator = page.frame_locator("iframe[title='Vaka Ayrıntıları']").frame_locator(
        "iframe[title='Adres Bilgileri']"
    )
    await level2.get_by_label("Adres").wait_for()
    cross = page.frame_locator("iframe[title='Müşteri Kaydı (dış sistem)']")
    await cross.get_by_label("Müşteri No").wait_for()
    await service.start_picker(OWNER, sid)

    await click_center(page, level2.get_by_label("Adres"))
    address = await picked_control(service, sid)
    assert address.label == "Adres" and address.frame_titles == ("Vaka Ayrıntıları", "Adres Bilgileri")
    await page.keyboard.type("xyz")
    assert await level2.get_by_label("Adres").input_value() == ""

    await click_center(page, cross.get_by_label("Müşteri No"))
    customer = await picked_control(service, sid)
    assert customer.frame_titles == ("Müşteri Kaydı (dış sistem)",)


async def test_picker_installs_into_late_frame(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    lab.set_scenario(late_frame_delay_ms=1200)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/frames")
    await service.start_picker(OWNER, sid)
    late = page.frame_locator("iframe[title='Ek Belgeler']").get_by_label("Belge No")
    await late.wait_for()
    await page.wait_for_timeout(300)
    await click_center(page, late)
    control = await picked_control(service, sid)
    assert control.label == "Belge No" and control.frame_titles == ("Ek Belgeler",)
    await page.keyboard.type("123")
    assert await late.input_value() == ""


async def test_stop_picker_removes_overlays(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    lab.set_scenario(late_frame_delay_ms=30_000)
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/frames")
    await page.frame_locator("iframe[title='Vaka Ayrıntıları']").get_by_label("Vaka Durumu").wait_for()
    await service.start_picker(OWNER, sid)
    await service.stop_picker(OWNER, sid)
    await service.clear_highlight(OWNER, sid)
    counts = [await f.evaluate("document.querySelectorAll('[data-agentask-ui]').length") for f in page.frames]
    assert counts == [0] * len(page.frames)
    assert await service.wait_pick(OWNER, sid, 100) is None


async def test_page_script_cannot_forge_pick(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    service, sid, page = ctx
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    await service.start_picker(OWNER, sid)
    await page.evaluate("""() => {
        const el = document.querySelector('button');
        for (const k of Object.keys(window)) {
            if (typeof window[k] === 'function' && k.startsWith('__agentask')) {
                try { window[k]({ token: 'x', index: 0, fp: 'x' }); } catch (e) {}
            }
        }
    }""")
    assert await service.wait_pick(OWNER, sid, 300) is None


async def test_stop_picker_releases_pending_wait(
    ctx: tuple[ObservationService, str, Page], lab: LabServer
) -> None:
    import time

    service, sid, _ = ctx
    await service.navigate(OWNER, sid, f"{lab.primary}/pages/duplicates")
    await service.start_picker(OWNER, sid)
    started = time.monotonic()
    waiter = asyncio.create_task(service.wait_pick(OWNER, sid, 5000))
    await asyncio.sleep(0.2)
    await service.stop_picker(OWNER, sid)
    assert await waiter is None
    assert time.monotonic() - started < 2
