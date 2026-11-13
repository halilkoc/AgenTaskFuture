from __future__ import annotations

import json
from typing import Any

from agentask.config import Settings, load_settings
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextHandle
from tests.conftest import EnvFileFactory
from tests.support_lab import LabServer


async def login(handle: PlaywrightContextHandle, lab: LabServer, user: str = "ayse") -> None:
    await handle.navigate(f"{lab.primary}/login")
    await handle.page.get_by_label("Kullanıcı adı").fill(user)
    await handle.page.get_by_role("button", name="Giriş yap").click()
    await handle.page.wait_for_url(f"{lab.primary}/")


def lab_settings(make_env_file: EnvFileFactory, lab: LabServer, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "TARGET_ALLOWED_ORIGINS": json.dumps([lab.primary, lab.secondary]),
        "TARGET_BASE_URL": lab.primary,
        "LAB_PRIMARY_ORIGIN": lab.primary,
        "LAB_SECONDARY_ORIGIN": lab.secondary,
        "BROWSER_HEADLESS": "true",
        "CHOICE_OPTIONS_WAIT_MS": "1500",
        "CATALOG_BACKEND": "disabled",  # yayın testleri geçici mongod ile açıkça "mongo" seçer
        # Deney uygulaması rastgele portta: uygulama listesi aynı origin'e bağlanır (id=lab).
        "AUTOMATION_APPLICATIONS_JSON": json.dumps(
            [{"id": "lab", "name": "Deney uygulaması", "base_url": f"{lab.primary}/"}]
        ),
    }
    values.update(overrides)
    return load_settings(make_env_file(**values))
