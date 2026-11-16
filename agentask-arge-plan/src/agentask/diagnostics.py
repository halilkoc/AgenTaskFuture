"""`agentask --doctor`: kurulum ve bağlantı ön kontrolü. Sır, tam adres veya yabancı hata metni yazdırmaz.

Geçen kontrol yalnız o bağlantının bu makineden açıldığını gösterir; gerçek kullanım kabulü yerine geçmez.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from agentask.application.ports.artifacts import ObjectStore
from agentask.config.errors import ConfigurationError
from agentask.config.settings import ApprovedActionSet, ArtifactBackend, AuthMode, CatalogBackend, Settings

OK, WARN, FAIL = "TAMAM", "UYARI", "HATA"


@dataclass(frozen=True, slots=True)
class Check:
    status: str
    name: str
    detail: str


def _python() -> Check:
    version = sys.version_info
    good = (version.major, version.minor) == (3, 12)
    return Check(OK if good else FAIL, "Python", f"{version.major}.{version.minor}; gereken 3.12")


def _directories(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    for label, path in (
        ("Çalışma kayıtları dizini", settings.run_directory),
        ("Taslak dizini", settings.draft_directory),
        ("Dosya/kanıt dizini", settings.artifact_directory),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path):
                pass
            checks.append(Check(OK, label, "yazılabilir"))
        except OSError as exc:
            checks.append(
                Check(FAIL, label, f"yazılamıyor ({type(exc).__name__}); dizin iznini kontrol edin")
            )
    return checks


def _identity(settings: Settings) -> Check:
    if settings.auth_mode is AuthMode.LOCAL_ADMIN:
        return Check(OK, "Kimlik", "geçici admin girişi (kurumsal SSO değildir)")
    if settings.auth_mode is AuthMode.DEV:
        return Check(WARN, "Kimlik", "AUTH_MODE=dev; yalnız kendi bilgisayarınızda ve loopback adreste")
    return Check(FAIL, "Kimlik", "AUTH_MODE=unconfigured; hiçbir istek kabul edilmez")


def _actions(settings: Settings) -> Check:
    if settings.approved_action_set is ApprovedActionSet.NONE:
        return Check(WARN, "Onaylı işlemler", "tanımlı değil; veri değiştiren adım kurulamaz")
    if settings.approved_action_set is ApprovedActionSet.LAB:
        return Check(WARN, "Onaylı işlemler", "deney seti; gerçek uygulamada kullanılmaz")
    return Check(OK, "Onaylı işlemler", "kurum dosyası doğrulandı")


async def _browser(settings: Settings) -> list[Check]:
    """Seçili motor, tarayıcı dosyasının varlığı ve başlatma sonucu. İndirme yapmaz, başka motora geçmez."""
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    from agentask.config.runtime_env import apply_playwright_environment

    apply_playwright_environment(settings)
    name = settings.browser_engine.value
    custom = settings.browser_executable_path
    source = "BROWSER_EXECUTABLE_PATH" if custom is not None else "Playwright tarayıcı dosyaları"
    checks = [Check(OK, "Tarayıcı motoru", f"BROWSER_ENGINE={name}; kaynak: {source}")]
    install = (
        f"Kurum aynasından veya çevrimdışı klasörden `playwright install {name}` ile sağlayın "
        "(INSTALL.md bölüm 3)"
    )
    if name == "chromium":
        install += " veya BROWSER_EXECUTABLE_PATH ile kurulu Edge/Chrome gösterin"
    try:
        async with async_playwright() as playwright:
            engine = getattr(playwright, name)
            binary = custom if custom is not None else Path(engine.executable_path)
            if not binary.is_file():
                missing = (
                    "BROWSER_EXECUTABLE_PATH dosyası yok"
                    if custom is not None
                    else f"{name} dosyaları bu makinede yok. {install}."
                )
                checks.append(Check(FAIL, "Tarayıcı dosyası", missing))
                checks.append(Check(FAIL, "Tarayıcı başlatma", "denenmedi (tarayıcı dosyası yok)"))
                return checks
            checks.append(Check(OK, "Tarayıcı dosyası", "mevcut"))
            browser = await engine.launch(
                headless=True,
                executable_path=str(custom) if custom else None,
                timeout=settings.browser_launch_timeout_ms,
            )
            version = browser.version
            await browser.close()
    except PlaywrightError as exc:
        checks.append(
            Check(FAIL, "Tarayıcı başlatma", f"{name} başlatılamadı ({type(exc).__name__}). {install}.")
        )
        return checks
    note = "" if not settings.browser_headless else "; BROWSER_HEADLESS=true iken elle giriş yapılamaz"
    checks.append(Check(WARN if note else OK, "Tarayıcı başlatma", f"{name} açıldı ({version}){note}"))
    return checks


async def _reachable(name: str, url: str, ca_bundle: Path | None, timeout_s: float) -> Check:
    verify: str | bool = str(ca_bundle) if ca_bundle else True
    try:
        async with httpx.AsyncClient(verify=verify, timeout=timeout_s, follow_redirects=False) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        tls = "; kurum CA sertifikasını kontrol edin" if type(exc).__name__ == "ConnectError" else ""
        return Check(WARN, name, f"bu makineden erişilemedi ({type(exc).__name__}){tls}")
    return Check(OK, name, f"sunucu yanıt verdi (HTTP {response.status_code}); kullanım kabulü değildir")


async def _mongo(settings: Settings) -> Check:
    if settings.catalog_backend is not CatalogBackend.MONGO:
        return Check(WARN, "MongoDB", "CATALOG_BACKEND=disabled; yayın yapılamaz")
    from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore

    store = MongoCatalogStore(
        settings.mongo_uri.get_secret_value(),
        settings.mongo_database,
        settings.mongo_server_selection_timeout_ms,
        settings.mongo_tls_ca_file,
    )
    try:
        reachable = await store.ping()
    finally:
        await store.close()
    if reachable:
        return Check(OK, "MongoDB", "bağlandı")
    return Check(
        FAIL, "MongoDB", "bağlanılamadı; MONGO_URI, ağ erişimi ve MONGO_TLS_CA_FILE ayarını kontrol edin"
    )


async def _s3(settings: Settings, store: ObjectStore) -> Check:
    try:
        await store.list_keys()
    except Exception as exc:  # teşhis: her hata türü yalnız adıyla raporlanır
        return Check(
            FAIL,
            "S3",
            f"listelenemedi ({type(exc).__name__}); uç nokta, kimlik, CA ve kova iznini kontrol edin",
        )
    return Check(OK, "S3", "kova listelendi (yazma denenmedi); kurum kabulü değildir")


async def _run_checks(settings: Settings) -> list[Check]:
    from agentask.bootstrap import object_store_for

    checks = [_python(), _identity(settings), _actions(settings), *_directories(settings)]
    checks.extend(await _browser(settings))
    timeout = settings.navigation_timeout_ms / 1000
    checks.append(await _reachable("Hedef uygulama", str(settings.target_base_url), None, timeout))
    checks.append(await _mongo(settings))
    if settings.llm_enabled and settings.llm_base_url is not None:
        checks.append(await _reachable("Model hizmeti", str(settings.llm_base_url), None, timeout))
    else:
        checks.append(Check(OK, "Model hizmeti", "LLM_ENABLED=false; kural tabanlı çalışır"))
    if settings.artifact_backend is ArtifactBackend.S3:
        checks.append(await _s3(settings, object_store_for(settings)))
    return checks


def run_doctor(settings: Settings, out: Callable[[str], None] = print) -> int:
    try:
        checks = asyncio.run(_run_checks(settings))
    except ConfigurationError as exc:
        out(str(exc))
        return 2
    for check in checks:
        out(f"[{check.status}] {check.name}: {check.detail}")
    failed = sum(c.status == FAIL for c in checks)
    out("SONUÇ: BAŞARISIZ" if failed else "SONUÇ: BAŞLATILABİLİR (uyarıları okuyun)")
    return 1 if failed else 0
