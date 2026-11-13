"""Çoklu seçim, tarih ve dosya yükleme: gerçek Chromium + deney uygulaması (Pega uyumluluğu değildir)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from agentask.application.services.artifacts import ArtifactService
from agentask.domain.runtime import RunStatus
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env, build
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
PAGE = "/pages/controls"
PDF = b"%PDF-1.4 deneme"
TAGS = {"kind": "select", "labels": ["Etiketler"], "region": "Çoklu"}
PERMS = {"kind": "combobox", "labels": ["Yetkiler"], "region": "Çoklu"}


@dataclass
class FileEnv:
    env: Env
    files: ArtifactService


@pytest.fixture
async def ctx(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[FileEnv]:
    lab.reset()
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="1500", ACTION_TIMEOUT_MS="3000")
    service, sessions = build(settings, PlaywrightContextFactory(settings), tmp_path / "runs")
    files = ArtifactService(
        LocalObjectStore(tmp_path / "a"), LocalArtifactIndex(tmp_path / "a"), max_bytes=2000, retention_days=7
    )
    service.attach_file_reader(files.read_upload)
    view = await sessions.open(OWNER)
    yield FileEnv(Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs"), files)
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


def many(target: dict[str, Any], *choices: str, effect: str = "ui_local") -> dict[str, Any]:
    return {"op": "ensure_choices", "target": target, "choices": list(choices), "effect": effect}


def date_step(label: str, value: str, fmt: str = "DD.MM.YYYY") -> dict[str, Any]:
    target = {"kind": "textbox", "labels": [label], "region": "Tarih"}
    return {"op": "ensure_date", "target": target, "value": value, "date_format": fmt}


def upload(artifact: str, label: str = "Belge", **extra: Any) -> dict[str, Any]:
    target = {"kind": "file", "labels": [label], "region": "Yükleme"}
    return {"op": "upload_file", "target": target, "artifact_id": artifact, **extra}


async def selected(env: Env) -> list[str]:
    field = env.page.get_by_role("region", name="Çoklu").get_by_label("Etiketler")
    return list(await field.evaluate("e => Array.from(e.selectedOptions).map(o => o.text)"))


async def changes(env: Env) -> int:
    field = env.page.get_by_role("region", name="Çoklu").get_by_label("Etiketler")
    return int(await field.get_attribute("data-changes") or 0)


def field(env: Env, region: str, label: str) -> Any:
    return env.page.get_by_role("region", name=region).get_by_label(label, exact=True)


async def uploads(env: Env, label: str = "Belge") -> int:
    return int(await field(env, "Yükleme", label).get_attribute("data-uploads") or 0)


async def test_exact_set_replaces_current_selection(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([many(TAGS, "Gama", "Alfa")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert sorted(await selected(env)) == ["Alfa", "Gama"]


async def test_same_set_in_any_order_makes_no_change(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    assert (await env.run([many(TAGS, "Beta")], "a")).status is RunStatus.COMPLETED
    assert await changes(env) == 0
    assert (await env.run([many(TAGS, "Gama", "Beta")], "b")).status is RunStatus.COMPLETED
    first = await changes(env)
    assert (await env.run([many(TAGS, "Beta", "Gama")], "c")).status is RunStatus.COMPLETED
    assert await changes(env) == first


@pytest.mark.parametrize("bad", ["Yok", "Kapalı Seçenek"])
async def test_bad_member_stops_before_any_change(ctx: FileEnv, bad: str) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([many(TAGS, "Alfa", bad)])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert await selected(env) == ["Beta"]
    assert await changes(env) == 0


async def test_aria_multiselect_applies_only_the_difference(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([many(PERMS, "Okuma", "Yazma")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    box = env.page.get_by_role("listbox", name="Yetkiler")
    assert await box.get_attribute("data-clicks") == "1"
    assert await box.get_by_role("option", name="Okuma").get_attribute("aria-selected") == "true"


async def test_single_select_command_still_rejects_multi(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([{"op": "ensure_choice", "target": TAGS, "choice": "Alfa"}])
    assert run.status is not RunStatus.COMPLETED
    assert await selected(env) == ["Beta"]


async def test_native_date_is_written_iso_and_verified(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([date_step("Başlangıç", "09.11.2026")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await field(env, "Tarih", "Başlangıç").input_value() == "2026-11-09"


async def test_text_date_uses_declared_format(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([date_step("Bitiş", "2026-11-09", "DD/MM/YYYY")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await field(env, "Tarih", "Bitiş").input_value() == "09/11/2026"


@pytest.mark.parametrize("value", ["31.02.2026", "1.2.2026", "yarın"])
async def test_invalid_date_is_never_written(ctx: FileEnv, value: str) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([date_step("Bitiş", value)])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert await field(env, "Tarih", "Bitiş").input_value() == ""


async def test_app_changing_the_date_is_failure(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([date_step("Çeviren", "09.11.2026")])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert run.steps[0].error_class == "VERIFICATION_FAILED"


async def test_readonly_calendar_field_is_not_forced(ctx: FileEnv) -> None:
    env = ctx.env
    await env.goto(PAGE)
    run = await env.run([date_step("Takvimli", "09.11.2026")])
    assert run.status is not RunStatus.COMPLETED
    assert await field(env, "Tarih", "Takvimli").input_value() == ""


async def test_upload_sends_once_with_original_name(ctx: FileEnv) -> None:
    env = ctx.env
    ref = await ctx.files.store_upload(OWNER, "application/pdf", PDF, "rapor.pdf")
    await env.goto(PAGE)
    run = await env.run([upload(ref.artifact_id, allowed_types=["application/pdf"])])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await field(env, "Yükleme", "Belge").get_attribute("data-received") == (
        f"rapor.pdf|application/pdf|{len(PDF)}"
    )
    assert await uploads(env) == 1
    assert "rapor.pdf" not in str([s.model_dump() for s in run.steps])


async def test_visually_hidden_file_input_is_supported(ctx: FileEnv) -> None:
    env = ctx.env
    ref = await ctx.files.store_upload(OWNER, "application/pdf", PDF, "gizli.pdf")
    await env.goto(PAGE)
    run = await env.run([upload(ref.artifact_id, "Gizli Belge")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await uploads(env, "Gizli Belge") == 1


async def test_another_users_file_is_not_sent(ctx: FileEnv) -> None:
    env = ctx.env
    ref = await ctx.files.store_upload("baska.kullanici", "application/pdf", PDF, "rapor.pdf")
    await env.goto(PAGE)
    run = await env.run([upload(ref.artifact_id)])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert await uploads(env) == 0


async def test_disallowed_type_is_not_sent(ctx: FileEnv) -> None:
    env = ctx.env
    ref = await ctx.files.store_upload(OWNER, "text/plain", b"metin", "not.txt")
    await env.goto(PAGE)
    run = await env.run([upload(ref.artifact_id, allowed_types=["application/pdf"])])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert await uploads(env) == 0


async def test_uncertain_upload_is_not_resent_on_resume(ctx: FileEnv) -> None:
    env = ctx.env
    ref = await ctx.files.store_upload(OWNER, "application/pdf", PDF, "rapor.pdf")
    await env.goto(PAGE)
    driver_type = type(env.sessions.peek(OWNER, env.sid).driver)  # type: ignore[attr-defined]
    original = driver_type.set_file

    async def sent_then_lost(self: Any, cid: str, name: str, content_type: str, data: bytes) -> None:
        await original(self, cid, name, content_type, data)
        raise RuntimeError("bağlantı koptu")

    driver_type.set_file = sent_then_lost
    try:
        run = await env.run([upload(ref.artifact_id)])
        assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
        resumed = await env.service.resume(OWNER, run.run_id, env.sid)
        resumed = await env.service.wait(resumed.run_id, 15)
    finally:
        driver_type.set_file = original
    assert resumed.status is RunStatus.OUTCOME_UNKNOWN
    assert await uploads(env) == 1
