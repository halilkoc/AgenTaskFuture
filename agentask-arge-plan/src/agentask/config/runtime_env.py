"""Settings değerlerini, kendi ayarını process env'den okuyan üçüncü taraf sürücülere aktarır.

Yalnızca burada process env'e yazılır; okuma yine Settings üzerinden yapılmıştır.
"""

from __future__ import annotations

import os

from agentask.config.settings import Settings


def apply_playwright_environment(settings: Settings) -> None:
    if settings.playwright_browsers_path is not None:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(settings.playwright_browsers_path)
