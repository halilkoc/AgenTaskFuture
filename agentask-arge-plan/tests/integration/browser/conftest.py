from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator

import pytest

from agentask.config import Settings, load_settings
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.support_lab import HitCounterServer, LabServer


@pytest.fixture(autouse=True)
def _reset_lab(lab: LabServer) -> None:
    lab.reset()


@pytest.fixture
def browser_settings(make_env_file: EnvFileFactory, lab: LabServer) -> Settings:
    return load_settings(
        make_env_file(
            TARGET_ALLOWED_ORIGINS=json.dumps([lab.primary, lab.secondary]),
            TARGET_BASE_URL=lab.primary,
            LAB_PRIMARY_ORIGIN=lab.primary,
            LAB_SECONDARY_ORIGIN=lab.secondary,
            AUTOMATION_APPLICATIONS_JSON=json.dumps(
                [{"id": "lab", "name": "Deney uygulaması", "base_url": f"{lab.primary}/"}]
            ),
            BROWSER_HEADLESS="true",
            BROWSER_MAX_SESSIONS="4",
            BROWSER_MAX_SESSIONS_PER_USER="1",
        )
    )


@pytest.fixture
async def factory(browser_settings: Settings) -> AsyncIterator[PlaywrightContextFactory]:
    instance = PlaywrightContextFactory(browser_settings)
    yield instance
    await instance.shutdown()


@pytest.fixture
def outsider() -> Iterator[HitCounterServer]:
    server = HitCounterServer()
    yield server
    server.stop()
