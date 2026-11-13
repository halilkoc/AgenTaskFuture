"""Gerçek Chromium ile oturum izolasyonu, origin sınırı, kilit ve kaynak temizliği."""

from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import Error as PlaywrightError

from agentask.application.errors import NavigationNotAllowed, SessionBusy
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.support_lab import HitCounterServer, LabServer

pytestmark = pytest.mark.browser


async def _login(handle: object, lab: LabServer, user: str) -> None:
    page = handle.page  # type: ignore[attr-defined]
    await handle.navigate(f"{lab.primary}/login")  # type: ignore[attr-defined]
    await page.get_by_label("Kullanıcı adı").fill(user)
    await page.get_by_role("button", name="Giriş yap").click()
    await page.wait_for_url(f"{lab.primary}/")


async def test_users_are_isolated_by_context(factory: PlaywrightContextFactory, lab: LabServer) -> None:
    ayse = await factory.create_context("ayse")
    mehmet = await factory.create_context("mehmet")
    await _login(ayse, lab, "ayse")
    await ayse.navigate(f"{lab.primary}/pages/duplicates")
    assert ayse.current_url == f"{lab.primary}/pages/duplicates"

    await mehmet.navigate(f"{lab.primary}/pages/duplicates")
    assert "/login" in mehmet.current_url
    assert await mehmet.context.cookies() == []
    assert len(await ayse.context.cookies()) == 1


async def test_navigation_outside_allowed_origins_is_blocked(
    factory: PlaywrightContextFactory, lab: LabServer, outsider: HitCounterServer
) -> None:
    handle = await factory.create_context("ayse")
    with pytest.raises(NavigationNotAllowed):
        await handle.navigate(f"{outsider.origin}/direct")
    for bad in ("javascript:alert(1)", "file:///etc/passwd"):
        with pytest.raises(NavigationNotAllowed):
            await handle.navigate(bad)

    await _login(handle, lab, "ayse")
    page = handle.page
    # Sayfa içinden iframe, popup, script yönlendirmesi ve sunucu yönlendirmesi
    await page.evaluate(
        """o => {
            const f = document.createElement('iframe'); f.src = o + '/iframe'; document.body.appendChild(f);
            const img = new Image(); img.src = o + '/pixel';
            window.open(o + '/popup');
        }""",
        outsider.origin,
    )
    # İzinli origin'e yönlendirme çalışmaya devam eder (cookie korunur).
    await page.goto(f"{lab.primary}/lab-api/redirect-out?to={lab.primary}/pages/duplicates")
    assert page.url == f"{lab.primary}/pages/duplicates"
    with pytest.raises(PlaywrightError, match="ERR_BLOCKED_BY_CLIENT"):
        await page.goto(f"{lab.primary}/lab-api/redirect-out?to={outsider.origin}/redirect")
    await asyncio.sleep(0.5)
    with pytest.raises(Exception):  # noqa: B017
        await page.evaluate("o => { window.location.href = o + '/location'; }", outsider.origin)
        await page.wait_for_url(f"{outsider.origin}/location", timeout=1000)
    assert outsider.hits == []


async def test_shutdown_closes_contexts_and_browser(
    factory: PlaywrightContextFactory, lab: LabServer
) -> None:
    first = await factory.create_context("ayse")
    second = await factory.create_context("mehmet")
    browser = first.context.browser
    assert browser is not None and browser.is_connected()
    await factory.shutdown()
    assert first.is_closed and second.is_closed
    assert not browser.is_connected()
    await factory.shutdown()  # idempotent


async def test_browser_relaunches_after_disconnect(factory: PlaywrightContextFactory, lab: LabServer) -> None:
    first = await factory.create_context("ayse")
    browser = first.context.browser
    assert browser is not None
    await browser.close()
    assert first.is_closed
    second = await factory.create_context("ayse")
    await second.navigate(f"{lab.primary}/login")
    assert second.context.browser is not browser


async def test_concurrent_operations_on_real_session_conflict(
    factory: PlaywrightContextFactory, lab: LabServer
) -> None:
    lab.set_scenario(delay_ms=800)
    service = BrowserSessionService(factory, SessionLimits(max_sessions=2, max_per_user=1, idle_seconds=60))
    view = await service.open("ayse")
    started = asyncio.Event()

    async def slow_navigation() -> None:
        async with service.operation("ayse", view.session_id, "trial") as handle:
            started.set()
            await handle.navigate(f"{lab.primary}/login")

    task = asyncio.create_task(slow_navigation())
    await started.wait()
    with pytest.raises(SessionBusy):
        async with service.operation("ayse", view.session_id, "observe"):
            pass
    await task
    await service.shutdown()


async def test_guarded_context_is_transparent_for_lab_scenarios(
    factory: PlaywrightContextFactory, lab: LabServer
) -> None:
    from playwright.async_api import expect

    handle = await factory.create_context("ayse")
    await _login(handle, lab, "ayse")
    page = handle.page

    lab.set_scenario(table_rows=30, scroll_batch=15)
    await handle.navigate(f"{lab.primary}/pages/table-scroll")
    rows = page.get_by_role("table", name="Hareketler").locator("tbody tr")
    await expect(rows).to_have_count(15)
    await page.get_by_role("region", name="Hareketler listesi").evaluate(
        "el => { el.scrollTop = el.scrollHeight; }"
    )
    await expect(rows).to_have_count(30)

    lab.set_scenario(lose_next_commit_response=True, lost_response_hang_ms=2500, client_timeout_ms=800)
    await handle.navigate(f"{lab.primary}/pages/note-form")
    await page.get_by_label("Not", exact=True).fill("Korumalı context notu")
    await page.get_by_role("button", name="Kaydet").click()
    status = page.get_by_role("status")
    await expect(status).to_have_text("Yanıt alınamadı — işlem sonucu bilinmiyor", timeout=5000)
    await asyncio.sleep(2.2)  # askıdaki yanıt geldiğinde iptal edilmiş istek handler'ı çökertmemeli
    await page.get_by_label("Not", exact=True).fill("İkinci")
    await page.get_by_role("button", name="Kaydet").click()
    await expect(status).to_have_text("Kaydedildi (Not #2)")
    assert [c["text"] for c in lab.control("GET", "/__lab/state").json()["commits"]] == [
        "Korumalı context notu",
        "İkinci",
    ]


async def test_browser_launch_failure_is_dependency_unavailable(
    make_env_file: object, lab: LabServer, tmp_path: object
) -> None:
    from agentask.application.errors import DependencyUnavailable
    from agentask.config import load_settings

    settings = load_settings(
        make_env_file(BROWSER_HEADLESS="true", BROWSER_EXECUTABLE_PATH="/nonexistent/chrome")  # type: ignore[operator]
    )
    broken = PlaywrightContextFactory(settings)
    try:
        with pytest.raises(DependencyUnavailable) as exc:
            await broken.create_context("ayse")
        assert "/nonexistent" not in exc.value.safe_message
        assert not broken.is_running
    finally:
        await broken.shutdown()
