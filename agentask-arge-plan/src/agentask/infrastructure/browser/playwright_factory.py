"""Playwright adapteri: tek browser süreci, kullanıcı/oturum başına ayrı BrowserContext.

- Browser ilk oturumda (lock ile tek sefer) başlatılır; koptuysa bir sonraki oturumda yeniden başlatılır.
- İzinli olmayan origin'e giden bütün http(s) istekleri context seviyesinde abort edilir (iframe, popup,
  script yönlendirmesi, sunucu yönlendirmesi dahil). navigate() ayrıca istek atmadan önce reddeder.
- Playwright nesneleri oluşturuldukları event loop'ta kalır; thread'ler arası taşınmaz.
"""

from __future__ import annotations

import asyncio
import contextlib
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
from agentask.domain.origins import OriginPolicy, origin_of
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
        self._settings = settings
        # Benimsenmiş beklenen pencere: (kesinti kimliği, sayfa, gözlemci, sürücü). En fazla bir tane.
        self._child: tuple[str, Page, PageObserver, PlaywrightDriver] | None = None
        context.on("close", lambda _: self._mark_closed())

    def _mark_closed(self) -> None:
        self._closed = True

    # Yalnızca infrastructure ve testler kullanır; uygulama katmanı port arayüzünü görür.
    @property
    def context(self) -> BrowserContext:
        return self._context

    @property
    def page(self) -> Page:
        return self._child[1] if self._child else self._page

    @property
    def observer(self) -> PageObserver:
        return self._child[2] if self._child else self._observer

    @property
    def driver(self) -> PlaywrightDriver:
        return self._child[3] if self._child else self._driver

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def adopted(self) -> bool:
        return self._child is not None

    @property
    def window_closed(self) -> bool:
        return self._child is not None and self._child[1].is_closed()

    @property
    def focused_origin(self) -> str | None:
        return (origin_of(self._child[1].url) or "boş sayfa") if self._child else None

    def _focus(self, window_id: str, page: Page) -> None:
        self._observer.window_list[:] = [w for w in self._observer.window_list if w[0] != window_id]
        observer = PageObserver(page, self._settings, shared_windows=self._observer.window_list)
        self._child = (window_id, page, observer, PlaywrightDriver(observer, page, self._settings))

    async def adopt_window(self, expected_origin: str | None) -> str:
        """Tek beklenen pencereyi etkin sayfa yapar. 'ok' dışındaki sonuçta hiçbir şey değişmez."""
        pending = list(self._observer.window_list)
        if self._child is not None or len(pending) != 1:
            return "multiple" if pending or self._child else "none"
        window_id, page = pending[0]
        with contextlib.suppress(PlaywrightError):
            await page.wait_for_load_state("domcontentloaded", timeout=self._nav_timeout_ms)
        if page.is_closed():
            return "closed"
        if not self._policy.allows(page.url):
            return "origin_not_allowed"
        if origin_of(page.url) != (expected_origin or origin_of(self._page.url)):
            return "wrong_origin"
        self._focus(window_id, page)
        return "ok"

    async def focus_window(self, window_id: str) -> bool:
        """Tasarım: analistin açtığı izinli pencerede alan seçmek için (yalnız açık kararıyla)."""
        found = next((p for i, p in self._observer.window_list if i == window_id), None)
        if (
            self._child is not None
            or found is None
            or found.is_closed()
            or not self._policy.allows(found.url)
        ):
            return False
        self._focus(window_id, found)
        return True

    async def return_main(self, close: bool, timeout_ms: int) -> bool:
        """Ana sayfaya döner. close=False: pencereyi uygulamanın kapatması sınırlı süre beklenir."""
        if self._child is None:
            return False
        page = self._child[1]
        if not page.is_closed():
            with contextlib.suppress(PlaywrightError):
                if close:
                    await page.close()
                else:
                    await page.wait_for_event("close", timeout=timeout_ms)
        if not page.is_closed():
            return False
        self._child = None
        return True

    def release_windows(self) -> None:
        """Yarıda kalan pencere ana sayfaya bırakılır; açıksa kesinti olarak görünür, insan karar verir."""
        if self._child is None:
            return
        window_id, page, _, _ = self._child
        self._child = None
        if not page.is_closed():
            self._observer.window_list.append((window_id, page))

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def navigate(self, url: str) -> None:
        if not self._policy.allows(url):
            raise NavigationNotAllowed()
        await self.page.goto(url, timeout=self._nav_timeout_ms)

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
                # Teşhis için `agentask --doctor`; yabancı hata metni loga yazılmaz (ADR 0022).
                logger.error(
                    "browser_launch_failed engine=%s type=%s",
                    settings.browser_engine.value,
                    type(exc).__name__,
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
