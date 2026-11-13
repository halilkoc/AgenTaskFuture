"""Yeni tasarımcı kabul testleri için ortak adımlar: akış, alan seçme, kaydetme, deneme, yayın, Asistan."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, expect

from agentask.domain.passwords import hash_password
from agentask.presentation.app import create_app
from tests.conftest import EnvFileFactory
from tests.e2e.support import AppServer
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer
from tests.support_mongo import ephemeral_mongod

OWNER = "dev.user"
ADMIN = "admin"
ADMIN_PASSWORD = "kabul-test-parolasi-12345"  # yalnız geçici test uygulaması; gerçek hesap değil

# Sayfadaki her alanın anlamsal anahtarla değeri: hedef dışı alanların değişmediğini kanıtlamak için.
_FIELDS_JS = """() => {
  const clean = (s) => String(s || '').replace(/\\s+/g, ' ').trim();
  const regionOf = (el) => {
    const r = el.closest('section,[role=dialog]');
    if (!r) return '';
    const id = r.getAttribute('aria-labelledby');
    return clean(r.getAttribute('aria-label') || (id && document.getElementById(id)?.textContent) || '');
  };
  const out = {};
  for (const el of document.querySelectorAll('input:not([type=hidden]),select,textarea')) {
    const first = el.labels && el.labels[0] && el.labels[0].textContent;
    const label = clean(first || el.getAttribute('aria-label'));
    const key = `${regionOf(el)} › ${label}`;
    if (el.type === 'checkbox' || el.type === 'radio') out[key] = el.checked;
    else if (el.tagName === 'SELECT') {
      out[key] = Array.from(el.selectedOptions).map((o) => clean(o.text)).join(', ');
    }
    else out[key] = el.value;
  }
  return out;
}"""


def admin_settings() -> dict[str, str]:
    return {
        "AUTH_MODE": "local_admin",
        "DEV_AUTH_ENABLED": "false",
        "ADMIN_USERNAME": ADMIN,
        "ADMIN_PASSWORD_HASH": hash_password(ADMIN_PASSWORD),
    }


async def page_fields(page: Any) -> dict[str, Any]:
    result: dict[str, Any] = await page.evaluate(_FIELDS_JS)
    return result


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Değişen alanlar. Beklenen dışında bir alan değiştiyse test birebir karşılaştırmayla yakalar."""
    return {k: v for k, v in after.items() if before.get(k) != v}


def mongo_app(
    make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path, database: str, **extra: Any
) -> Iterator[AppServer]:
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
            MONGO_DATABASE=database,
            **extra,
        )
        server = AppServer(create_app(settings))
        server.start()
        yield server
        server.stop()
        lab.reset()


@dataclass
class Flow:
    ui: Page
    server: AppServer
    lab: LabServer
    sid: str
    handle: Any
    name: str
    release: str = ""
    support: str = ""

    @property
    def editor(self) -> Any:
        return self.ui.locator("#pd-editor")

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.port}"

    async def in_server(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return await asyncio.get_running_loop().run_in_executor(None, self.server.run, coro)

    async def goto(self, path: str) -> None:
        await self.in_server(
            self.handle.navigate(f"{self.lab.primary}/__lab/autologin?user=ayse&next={path}")
        )

    async def add(self, component: str) -> Any:
        await self.ui.locator("#pd-components").get_by_role("button", name=component).click()
        return self.editor

    async def pick(self, component: str, field: str, *, listing: str = "Ekrandaki alanları listele") -> Any:
        editor = await self.add(component)
        await editor.get_by_role("button", name=listing).click()
        await editor.get_by_role("button", name=field).click()
        await expect(editor.locator("[id$='-check']")).to_have_text(
            "Ekranda tek olarak bulundu.", timeout=10000
        )
        return editor

    async def save(self) -> None:
        await self.ui.get_by_role("button", name="Taslağı kaydet").click()
        await expect(self.ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi", timeout=30000)
        await expect(self.ui.locator("#pd-draft-status")).not_to_contain_text("Kaydedilmeyen")

    async def reopen(self) -> Any:
        await self.ui.get_by_role("button", name="Akışlara dön").click()
        await self.ui.get_by_role("button", name="Kayıtlı taslakları göster").click()
        await self.ui.get_by_role("button", name=f"“{self.name}” taslağını aç").click()
        await expect(self.ui.locator("#pd-draft-status")).to_contain_text("Taslak kaydedildi")
        await expect(self.ui.locator("#pd-draft-status")).not_to_contain_text("Salt okunur")
        return self.ui.locator(".pd-card")

    @property
    def panel(self) -> Any:
        return self.ui.locator("#pd-runpanel")

    async def introduce_screen(self) -> None:
        await self.panel.get_by_role("button", name="Ekranı tanıt", exact=True).click()
        await self.panel.get_by_role("button", name="Bu işaretlerle ekranı tanıt").click()
        await expect(self.panel).to_contain_text("tanıtıldı", timeout=15000)

    async def confirm_and_try(self, index: int, before: Callable[[], Awaitable[None]] | None = None) -> None:
        step = self.panel.locator(".pd-live__step").nth(index)
        for box in await step.locator("[data-ack]").all():
            await box.check()
        await step.get_by_role("button", name="Onayla", exact=True).click()
        await expect(step).to_contain_text("Denemeye hazır", timeout=10000)
        if before is not None:
            await before()
        await step.get_by_label("Bu deneme hedef uygulamada işlem yapabilir").check()
        await step.get_by_role("button", name="Gerçek dene").click()
        await expect(step).to_contain_text("Sistem doğrulaması: BAŞARILI", timeout=25000)
        await step.get_by_role("button", name="Sonucu onayla").click()
        await expect(step).to_contain_text("Hazır", timeout=10000)

    async def publish(self, path: str) -> None:
        status = self.ui.locator("#pd-runpanel-status")
        await self.panel.get_by_label("Başlangıç ekranı (deney uygulamasındaki yol)").fill(path)
        await self.panel.get_by_role("button", name="Yeni oturum testi").click()
        await expect(status).to_contain_text("Yeni oturum testi tamamlandı: BAŞARILI", timeout=40000)
        await expect(self.panel).to_contain_text("Eksik yok: incelemeye hazır.")
        await self.panel.get_by_role("button", name="Onayla (yayıncı)").click()
        await expect(status).to_contain_text("Onaylandı (yayıncı)", timeout=10000)
        await self.panel.get_by_role("button", name="Yayımla").click()
        await expect(status).to_contain_text("Yayımlandı ve etkin: rel-", timeout=15000)
        found = re.search(r"rel-[A-Za-z0-9_-]+", await status.inner_text())
        assert found is not None
        self.release = found[0]
        listing = await (
            await self.ui.request.get(f"{self.base}/api/catalogs/releases?application_id=lab")
        ).json()
        assert listing["active_release_id"] == self.release  # yalnız mesaj değil, kayıtlı etkin yayın

    async def fields(self) -> dict[str, Any]:
        result: dict[str, Any] = await self.in_server(page_fields(self.handle.page))
        return result

    async def assistant_open(self, title: str, path: str) -> None:
        await self.ui.goto(f"{self.base}/assistant")
        await self.ui.locator(".sp-list li").first.get_by_role("button", name="Bu oturumu kullan").click()
        await self.goto(path)
        await self.ui.locator(".as-ready-wrap summary").click()
        await self.ui.locator(".as-ready").get_by_role("button", name=title).click()

    async def assistant_start(
        self, *, ack: bool = False, expected: str | re.Pattern[str] = "Başarılı"
    ) -> None:
        await self.ui.get_by_role("button", name="Planı göster").click()
        await expect(self.ui.locator(".as-plan")).to_contain_text("etki:", timeout=10000)
        if ack:
            await self.ui.locator("[name=ack]").check()
        await self.ui.get_by_role("button", name="Başlat").click()
        await expect(self.ui.locator(".rl-run .badge")).to_have_text(expected, timeout=45000)
        support = await self.ui.locator(".as-support").inner_text()
        assert re.fullmatch(r"Destek numarası: \S{8,}", support), support
        self.support = support.split(": ", 1)[1]

    async def history_detail(self) -> Any:
        """/runs: son çalışmanın ayrıntısı açılır; destek numarası Asistan'dakiyle aynı olmalı."""
        await self.ui.goto(f"{self.base}/runs")
        await self.ui.locator(".rn-list").get_by_role("button", name="Ayrıntı").first.click()
        detail = self.ui.locator(".rn-detail")
        await expect(detail.locator(".rn-support")).to_have_text(f"Destek numarası: {self.support}")
        return detail


async def open_flow(
    browser: Any, server: AppServer, lab: LabServer, name: str, path: str, *, admin: bool = False
) -> Flow:
    ui = await browser.new_page(viewport={"width": 1440, "height": 1000})
    await ui.goto(f"http://127.0.0.1:{server.port}/prototype/designer")
    if admin:
        await ui.get_by_label("Kullanıcı adı").fill(ADMIN)
        await ui.get_by_label("Parola").fill(ADMIN_PASSWORD)
        await ui.get_by_role("button", name="Giriş yap").click()
    await ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
    await ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill(name)
    await ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
    await ui.get_by_role("button", name="Yeni oturum aç").click()
    await expect(ui.locator("#pd-real-status")).to_contain_text("Yeni oturum açıldı")
    sid = await ui.get_by_label("Tarayıcı oturumu").input_value()
    owner = ADMIN if admin else OWNER
    flow = Flow(ui, server, lab, sid, server.app.state.container.sessions.peek(owner, sid), name)
    await flow.goto(path)
    return flow


async def next_flow(flow: Flow, name: str, path: str) -> Flow:
    """Aynı tarayıcı oturumuyla yeni akış."""
    await flow.ui.goto(f"{flow.base}/prototype/designer")
    await flow.ui.locator("#pd-home").get_by_role("button", name="Yeni akış").click()
    await flow.ui.get_by_role("textbox", name="Akışın adı (zorunlu)").fill(name)
    await flow.ui.get_by_role("button", name="Gerçek oturum", exact=True).click()
    await expect(flow.ui.get_by_label("Tarayıcı oturumu")).to_have_value(flow.sid, timeout=10000)
    await flow.goto(path)
    return Flow(flow.ui, flow.server, flow.lab, flow.sid, flow.handle, name)
