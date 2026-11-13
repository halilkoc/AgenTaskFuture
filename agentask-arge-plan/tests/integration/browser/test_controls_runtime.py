"""Onay kutusu, seçenek grubu ve öneri alanı: gerçek Chromium + deney uygulaması (Pega değildir)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.domain.runtime import RunStatus
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env, build
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser
PAGE = "/pages/controls"


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    lab.reset()
    settings = lab_settings(make_env_file, lab, READINESS_TIMEOUT_MS="1500", ACTION_TIMEOUT_MS="3000")
    service, sessions = build(settings, PlaywrightContextFactory(settings), tmp_path / "runs")
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


def box(label: str, region: str = "Başvuru") -> dict[str, Any]:
    return {"kind": "checkbox", "labels": [label], "region": region}


def group(label: str, region: str = "Başvuru") -> dict[str, Any]:
    return {"kind": "radio_group", "labels": [label], "region": region}


def check(target: dict[str, Any], checked: bool = True, effect: str = "ui_local") -> dict[str, Any]:
    return {"op": "ensure_checked", "target": target, "checked": checked, "effect": effect}


def auto(choice: str, label: str = "Şehir", kind: str = "combobox", **extra: Any) -> dict[str, Any]:
    target = {"kind": kind, "labels": [label], "region": "Arama"}
    return {"op": "ensure_choice", "target": target, "choice": choice, "autocomplete": True, **extra}


def region(env: Env, name: str) -> Any:
    return env.page.get_by_role("region", name=name)


async def clicks(env: Env, label: str, section: str = "Başvuru") -> int:
    value = await region(env, section).get_by_label(label, exact=True).get_attribute("data-clicks")
    return int(value or 0)


async def searches(env: Env) -> int:
    return int(await env.page.evaluate("window.__autoSearches"))


async def test_checkbox_same_label_is_separated_by_section(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Onaylıyorum", "Kefil"))])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await region(env, "Kefil").get_by_label("Onaylıyorum").is_checked()
    assert not await region(env, "Başvuru").get_by_label("Onaylıyorum").is_checked()


async def test_checkbox_without_section_is_ambiguous_and_untouched(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check({"kind": "checkbox", "labels": ["Onaylıyorum"]})])
    assert run.status is not RunStatus.COMPLETED
    assert await clicks(env, "Onaylıyorum") == 0
    assert await clicks(env, "Onaylıyorum", "Kefil") == 0


async def test_already_in_state_makes_no_click(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Zaten İşaretli"), True, "unknown")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await clicks(env, "Zaten İşaretli") == 0


async def test_uncheck_is_verified(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Zaten İşaretli"), False)])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert not await region(env, "Başvuru").get_by_label("Zaten İşaretli").is_checked()


async def test_visually_hidden_input_goes_through_its_label(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Bildirim Al"))])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await region(env, "Başvuru").get_by_label("Bildirim Al").is_checked()


async def test_aria_checkbox(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Sözleşme"))])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert (
        await region(env, "Başvuru").get_by_role("checkbox", name="Sözleşme").get_attribute("aria-checked")
        == "true"
    )


async def test_disabled_checkbox_is_not_changed(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Kilitli"))])
    assert run.status is not RunStatus.COMPLETED
    assert not await region(env, "Başvuru").get_by_label("Kilitli").is_checked()


async def test_hidden_checkbox_is_not_changed(env: Env) -> None:
    await env.goto(PAGE)
    await env.page.evaluate(
        "document.querySelector('section[aria-label=\"Başvuru\"]').style.display = 'none'"
    )
    run = await env.run([check(box("Onaylıyorum"))])
    assert run.status is not RunStatus.COMPLETED
    assert await clicks(env, "Onaylıyorum", "Kefil") == 0


async def test_checkbox_behind_modal_is_not_changed(env: Env) -> None:
    await env.goto(PAGE)
    await env.page.evaluate(
        """() => { const d = document.createElement('div'); d.setAttribute('role', 'dialog');
        d.setAttribute('aria-modal', 'true'); d.setAttribute('aria-label', 'Uyarı'); d.textContent = 'Uyarı';
        document.body.appendChild(d); }"""
    )
    run = await env.run([check(box("Onaylıyorum"))])
    assert run.status is not RunStatus.COMPLETED
    assert await clicks(env, "Onaylıyorum") == 0


async def test_app_reverting_checkbox_is_single_send_and_never_success(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([check(box("Geri Alan"), True, "unknown")])
    assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
    assert await clicks(env, "Geri Alan") == 1
    resumed = await env.service.resume(OWNER, run.run_id, env.sid)
    resumed = await env.service.wait(resumed.run_id, 15)
    assert resumed.status is RunStatus.OUTCOME_UNKNOWN
    assert await clicks(env, "Geri Alan") == 1  # devam ettirme de yeniden tıklamaz


async def test_radio_groups_with_same_name_are_separated(env: Env) -> None:
    await env.goto(PAGE)
    step = {"op": "ensure_choice", "target": group("Teslimat", "Kefil"), "choice": "Şube"}
    run = await env.run([step])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await region(env, "Kefil").get_by_label("Şube").is_checked()
    assert not await region(env, "Başvuru").get_by_label("Şube").is_checked()


async def test_radio_second_time_makes_no_click(env: Env) -> None:
    await env.goto(PAGE)
    step = {"op": "ensure_choice", "target": group("Teslimat"), "choice": "Kurye", "expected_value": "K"}
    assert (await env.run([step], "first")).status is RunStatus.COMPLETED
    assert (await env.run([step], "second")).status is RunStatus.COMPLETED
    assert await clicks(env, "Kurye") == 1


async def test_aria_radiogroup(env: Env) -> None:
    await env.goto(PAGE)
    target = {"kind": "radio_group", "labels": ["Öncelik"], "region": "Başvuru"}
    run = await env.run(
        [{"op": "ensure_choice", "target": target, "choice": "Normal", "expected_value": "N"}]
    )
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert await env.page.get_by_role("radio", name="Normal").get_attribute("aria-checked") == "true"


@pytest.mark.parametrize(
    ("name", "choice"), [("Yinelenen", "Aynı"), ("Kısıtlı", "Kapalı"), ("Teslimat", "Posta")]
)
async def test_bad_radio_option_stops_without_change(env: Env, name: str, choice: str) -> None:
    await env.goto(PAGE)
    run = await env.run([{"op": "ensure_choice", "target": group(name), "choice": choice}])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert await region(env, "Başvuru").locator("input[type=radio]:checked").count() == 0


async def test_autocomplete_delayed_redrawn_exact_pick(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([auto("Ankara Merkez", expected_value="ANK", search_text="Ank")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    field = region(env, "Arama").get_by_label("Şehir", exact=True)
    assert await field.input_value() == "Ankara Merkez"
    assert await field.get_attribute("data-value") == "ANK"
    assert await searches(env) == 1


async def test_autocomplete_plain_input_when_declared(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([auto("Kuzey Bölge", "Düz Arama", "textbox")])
    assert run.status is RunStatus.COMPLETED, [s.model_dump() for s in run.steps]
    assert (
        await region(env, "Arama").get_by_label("Düz Arama", exact=True).get_attribute("data-value") == "KB"
    )


@pytest.mark.parametrize("choice", ["Yok Böyle", "Çift Şube", "Ankara"])
async def test_autocomplete_no_exact_match_restores_and_says_so(env: Env, choice: str) -> None:
    await env.goto(PAGE)
    field = region(env, "Arama").get_by_label("Şehir", exact=True)
    await field.fill("Eski Değer")
    run = await env.run([auto(choice)])
    assert run.status is RunStatus.FAILED, run.model_dump()
    assert run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert run.steps[0].result["restored"] is True
    assert await field.input_value() == "Eski Değer"
    assert await field.get_attribute("data-value") is None


async def test_autocomplete_lost_selection_is_not_reported_as_restored(env: Env) -> None:
    """Regresyon (2026-11-13): eşleşme yokken yalnız metin geri yazılır, alandaki gerçek seçim (data-value)
    kaybolabilir. Bu durumda “eski değerine döndü” denmez; sonuç belirsizdir ve arama tekrarlanmaz."""
    await env.goto(PAGE)
    assert (
        await env.run([auto("Ankara Merkez", expected_value="ANK")], "first")
    ).status is RunStatus.COMPLETED
    field = region(env, "Arama").get_by_label("Şehir", exact=True)
    assert await field.get_attribute("data-value") == "ANK"
    run = await env.run([auto("Yok Böyle")], "second")
    assert run.status is RunStatus.OUTCOME_UNKNOWN, [s.model_dump() for s in run.steps]
    assert run.steps[0].error_class == "WRITE_RESULT_UNKNOWN"
    assert run.steps[0].result.get("restored") is not True
    assert await field.input_value() == "Ankara Merkez"
    assert await field.get_attribute("data-value") is None  # gerçek seçim geri gelmedi
    # Girdi olayları: 1. çalıştırmada arama; 2.'de arama + eski metnin geri yazılması. Yeniden arama yok.
    assert await searches(env) == 3


async def test_autocomplete_already_selected_does_not_search(env: Env) -> None:
    await env.goto(PAGE)
    assert (
        await env.run([auto("Ankara Merkez", expected_value="ANK")], "first")
    ).status is RunStatus.COMPLETED
    before = await searches(env)
    assert (
        await env.run([auto("Ankara Merkez", expected_value="ANK")], "second")
    ).status is RunStatus.COMPLETED
    assert await searches(env) == before


async def test_autocomplete_label_right_value_wrong_is_not_success(env: Env) -> None:
    await env.goto(PAGE)
    run = await env.run([auto("Yanlış Değer", expected_value="Y1")])
    assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
    assert await searches(env) == 1


async def test_combobox_input_without_declaration_is_rejected(env: Env) -> None:
    await env.goto(PAGE)
    target = {"kind": "combobox", "labels": ["Şehir"], "region": "Arama"}
    run = await env.run([{"op": "ensure_choice", "target": target, "choice": "Ankara Merkez"}])
    assert run.status is not RunStatus.COMPLETED
    assert await searches(env) == 0
