"""Testlerin kullandığı tarayıcı motoru. `AGENTASK_TEST_BROWSER_ENGINE` hem testin kendi (arayüz) tarayıcısını
hem de uygulamanın `BROWSER_ENGINE` ayarını belirler; verilmezse chromium. Uygulama ayarı değildir."""

from __future__ import annotations

import os
from typing import Any

ENGINE_ENV = "AGENTASK_TEST_BROWSER_ENGINE"
ENGINES = ("chromium", "firefox")  # webkit ayar katmanında reddedilir (ADR 0025)


def engine_name() -> str:
    value = os.environ.get(ENGINE_ENV, "chromium")  # noqa: TID251 - test koşusu seçimi, uygulama ayarı değil
    if value not in ENGINES:
        raise RuntimeError(f"{ENGINE_ENV} geçersiz; beklenen: {', '.join(ENGINES)}")
    return value


def ui_engine(playwright: Any) -> Any:
    """Testin arayüzü sürdüğü tarayıcı türü: seçili motor, başka motora düşmez."""
    return getattr(playwright, engine_name())


def isolate_browser_home() -> str | None:
    """macOS'ta Firefox profil kökünü kullanıcının gerçek `~/Library` dizini yerine geçici bir dizine alır.
    Bu makinede Firefox gerçek dizinde "Could not find profile folder" ile kapanıyor (2026-11-16); ayrıca test
    tarayıcısı kullanıcının profil alanına yazmamış olur. Playwright tarayıcı dosyalarının yeri değişmez."""
    import platform
    import tempfile

    if engine_name() != "firefox" or platform.system() != "Darwin":
        return None
    home = tempfile.mkdtemp(prefix="agentask-test-home-")
    os.environ["CFFIXED_USER_HOME"] = home  # noqa: TID251 - tarayıcı alt sürecine aktarılır
    return home


def remove_browser_home(home: str | None) -> None:
    import shutil
    import subprocess

    if home is None:
        return
    # macOS, oluşturduğu Library/Downloads dizinlerine silmeyi engelleyen ACL koyar; önce ACL kaldırılır.
    subprocess.run(["/bin/chmod", "-R", "-N", home], check=False)  # noqa: S603 - sabit komut, kendi dizini
    shutil.rmtree(home, ignore_errors=True)
