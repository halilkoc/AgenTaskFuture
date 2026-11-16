from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Browser, Page, async_playwright

from tests.support_browser import ui_engine
from tests.support_lab import LabServer


@pytest.fixture(autouse=True)
def _reset_lab(lab: LabServer) -> None:
    lab.reset()


@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        instance = await ui_engine(playwright).launch(headless=True)
        yield instance
        await instance.close()


@pytest.fixture
async def page(browser: Browser) -> AsyncIterator[Page]:
    context = await browser.new_context()
    yield await context.new_page()
    await context.close()


async def login(page: Page, lab: LabServer, user: str = "ayse") -> None:
    await page.goto(f"{lab.primary}/login")
    await page.get_by_label("Kullanıcı adı").fill(user)
    await page.get_by_role("button", name="Giriş yap").click()
    await page.wait_for_url(f"{lab.primary}/")


@pytest.fixture
async def logged_in(page: Page, lab: LabServer) -> Page:
    await login(page, lab)
    return page
