"""Playwright adapteri: tek browser süreci, kullanıcı/oturum başına ayrı BrowserContext.

- Browser ilk oturumda (lock ile tek sefer) başlatılır; koptuysa bir sonraki oturumda yeniden başlatılır.
- İzinli olmayan origin'e giden bütün http(s) istekleri context seviyesinde abort edilir (iframe, popup,
  script yönlendirmesi, sunucu yönlendirmesi dahil). navigate() ayrıca istek atmadan önce reddeder.
- Playwright nesneleri oluşturuldukları event loop'ta kalır; thread'ler arası taşınmaz.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError

from agentask.application.errors import DependencyUnavailable, NavigationNotAllowed
from agentask.config.runtime_env import apply_playwright_environment
from agentask.config.settings import Settings
from agentask.domain.origins import OriginPolicy
from agentask.infrastructure.browser.driver import PlaywrightDriver
from agentask.infrastructure.browser.observer import PageObserver
from agentask.infrastructure.browser.picker_js import BINDING

logger = logging.getLogger(__name__)


class PlaywrightContextHandle:
    def __init__(
        self,
        context: BrowserContext,
        page: Page,
        policy: OriginPolicy,
        nav_timeout_ms: int,
        settings: Settings,
    ) -> None:
        self._context = context
        self._page = page
        self._observer = PageObserver(page, settings)
        self._driver = PlaywrightDriver(self._observer, page, settings)
        self._policy = policy
        self._nav_timeout_ms = nav_timeout_ms
        self._closed = False
        context.on("close", lambda _: self._mark_closed())

    def _mark_closed(self) -> None:
        self._closed = True

    # Yalnızca infrastructure ve testler kullanır; uygulama katmanı port arayüzünü görür.
    @property
    def context(self) -> BrowserContext:
        return self._context

    @property
    def page(self) -> Page:
        return self._page

    @property
    def observer(self) -> PageObserver:
        return self._observer

    @property
    def driver(self) -> PlaywrightDriver:
        return self._driver

    @property
    def current_url(self) -> str:
        return self._page.url

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def navigate(self, url: str) -> None:
        if not self._policy.allows(url):
            raise NavigationNotAllowed()
        await self._page.goto(url, timeout=self._nav_timeout_ms)

    async def close(self) -> None:
        if not self._closed:
            await self._context.close()
            self._closed = True


class PlaywrightContextFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._policy = OriginPolicy(settings.target_allowed_origins)
        self._lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def _ensure_browser(self) -> Browser:
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            if self._playwright is None:
                apply_playwright_environment(self._settings)
                self._playwright = await async_playwright().start()
            settings = self._settings
            engine = getattr(self._playwright, settings.browser_engine.value)
            executable = settings.browser_executable_path
            try:
                self._browser = await engine.launch(
                    headless=settings.browser_headless,
                    executable_path=str(executable) if executable is not None else None,
                    timeout=settings.browser_launch_timeout_ms,
                )
            except PlaywrightError as exc:
                # Ayrıntı (yol vb.) yalnız loga; istemciye güvenli mesaj gider.
                logger.error(
                    "browser_launch_failed engine=%s detail=%s", settings.browser_engine.value, exc.message
                )
                raise DependencyUnavailable("Tarayıcı başlatılamadı.") from None
            logger.info("browser_launched engine=%s", settings.browser_engine.value)
            return self._browser

    async def _guard(self, route: Route, request: Request) -> None:
        url = request.url
        if not url.startswith(("http://", "https://")):
            await route.continue_()
            return
        if not self._policy.allows(url):
            logger.warning("navigation_blocked resource=%s", request.resource_type)
            await route.abort("blockedbyclient")
            return
        # Playwright route handler'ı yönlendirme adımlarında çağırmaz. Bu yüzden yanıt max_redirects=0 ile
        # alınır, Location hedefi politikaya göre denetlenir, sonra tarayıcıya verilir. Tarayıcı izinli
        # Location'a yeni bir istek yapar ve o istek de bu kontrolden geçer.
        try:
            response = await route.fetch(max_redirects=0)
        except Exception as exc:
            logger.warning("guarded_fetch_failed type=%s", type(exc).__name__)
            await route.abort("failed")
            return
        if 300 <= response.status < 400:
            location = response.headers.get("location")
            if location is not None and not self._policy.allows(urljoin(url, location)):
                logger.warning("redirect_blocked resource=%s", request.resource_type)
                await route.abort("blockedbyclient")
                return
        await route.fulfill(response=response)

    async def create_context(self, owner_id: str) -> PlaywrightContextHandle:
        browser = await self._ensure_browser()
        context = await browser.new_context(accept_downloads=False, service_workers="block")
        try:
            context.set_default_timeout(self._settings.action_timeout_ms)
            context.set_default_navigation_timeout(self._settings.navigation_timeout_ms)
            await context.route("**/*", self._guard)
            page = await context.new_page()
            handle = PlaywrightContextHandle(
                context, page, self._policy, self._settings.navigation_timeout_ms, self._settings
            )
            await context.expose_binding(BINDING, handle.observer.on_binding)
        except BaseException:
            await context.close()
            raise
        return handle

    async def shutdown(self) -> None:
        async with self._lock:
            browser, self._browser = self._browser, None
            playwright, self._playwright = self._playwright, None
            if browser is not None:
                try:
                    await browser.close()
                except Exception as exc:
                    logger.warning("browser_close_failed type=%s", type(exc).__name__)
            if playwright is not None:
                await playwright.stop()
