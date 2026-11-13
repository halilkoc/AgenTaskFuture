"""G: maskelemesi doğrulanmış kanıt üretimi — gerçek Chromium + deney uygulaması.

Doğrulananlar: form kontrolleri (parola dahil) maske rengiyle örtülür ve bu piksel düzeyinde doğrulanır;
maskesiz görüntü doğrulamadan geçemez; başarısız run kanıtı yalnız doğrulanmışsa depoya yazılır."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.application.controls import AdapterRegistry
from agentask.application.services.artifacts import ArtifactService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.runs import RunService
from agentask.bootstrap import _evidence_recorder
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore
from agentask.infrastructure.browser.evidence import (
    MASK_COLOR,
    MASK_SELECTOR,
    boxes_masked,
    capture_masked,
    decode_png,
)
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
OWNER = "ayse"


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Any]:
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="1500")
    sessions = BrowserSessionService(PlaywrightContextFactory(settings), SessionLimits(4, 2, 600))
    repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(
        repo,
        sessions,
        Executor(repo, LAB_ACTION_SET, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)),
        LAB_ACTION_SET,
        100,
    )
    artifacts = ArtifactService(
        LocalObjectStore(tmp_path / "art"), LocalArtifactIndex(tmp_path / "art"), 5_000_000, 7
    )
    view = await sessions.open(OWNER)
    handle = sessions.peek(OWNER, view.session_id)
    await handle.navigate(f"{lab.primary}/__lab/autologin?user=ayse&next=/pages/sensitive")
    yield sessions, runs, artifacts, view.session_id, handle
    await runs.shutdown()
    await sessions.shutdown()


async def test_form_values_are_masked_and_verified(env: Any) -> None:
    _, _, _, _, handle = env
    page = handle.page
    await page.get_by_label("Kullanıcı Parolası").fill("Gizli-Parola-77!")
    capture = await capture_masked(page)
    assert capture.verified and capture.boxes >= 5, capture.reason
    width, _, bpp, rows = decode_png(capture.png)
    box = await page.get_by_label("Kullanıcı Parolası").bounding_box()
    cx, cy = int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)
    assert tuple(rows[cy][cx * bpp : cx * bpp + 3]) == MASK_COLOR
    assert width > 0


async def test_unmasked_screenshot_fails_verification(env: Any) -> None:
    _, _, _, _, handle = env
    page = handle.page
    plain = await page.screenshot(type="png", full_page=False, scale="css")
    boxes = await page.evaluate(
        "(sel) => Array.from(document.querySelectorAll(sel)).map((e) => {"
        " const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; })",
        MASK_SELECTOR,
    )
    assert boxes_masked(plain, boxes) == (False, "unmasked_pixels")


async def test_failed_run_records_only_verified_evidence(env: Any) -> None:
    _, runs, artifacts, sid, _ = env
    runs.evidence = _evidence_recorder(artifacts)
    run = await runs.create(
        OWNER,
        sid,
        "ev-1",
        [{"op": "ensure_value", "target": {"kind": "textbox", "labels": ["Yok"]}, "value": "x"}],
    )
    run = await runs.wait(run.run_id, 30)
    for _ in range(50):  # kanıt kaydı run bittikten hemen sonra yazılır
        stored = runs.get(OWNER, run.run_id)
        if stored.evidence:
            break
        await asyncio.sleep(0.05)
    assert stored.status is RunStatus.FAILED and len(stored.evidence) == 1
    ref, data = await artifacts.fetch(OWNER, stored.evidence[0])
    assert ref.content_type == "image/png" and ref.run_id == run.run_id and data.startswith(b"\x89PNG")
