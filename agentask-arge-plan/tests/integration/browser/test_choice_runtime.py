"""Seçim adımı kabul senaryoları — gerçek Chromium + deney uygulaması (Pega uyumluluğu değildir)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentask.application.services.observation import ObservationService
from agentask.domain.runtime import RunStatus, StepState
from agentask.domain.targeting import TargetSpec
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from tests.conftest import EnvFileFactory
from tests.integration.browser.helpers import lab_settings
from tests.integration.browser.test_executor import OWNER, Env, build
from tests.support_lab import LabServer

pytestmark = pytest.mark.browser

SELECT = "select"
COMBO = "combobox"


@pytest.fixture
async def env(make_env_file: EnvFileFactory, lab: LabServer, tmp_path: Path) -> AsyncIterator[Env]:
    lab.reset()
    settings = lab_settings(
        make_env_file,
        lab,
        READINESS_TIMEOUT_MS="2500",
        OUTCOME_TIMEOUT_MS="2500",
        RECONCILE_TIMEOUT_MS="2500",
        ACTION_TIMEOUT_MS="3000",
    )
    factory = PlaywrightContextFactory(settings)
    service, sessions = build(settings, factory, tmp_path / "runs")
    view = await sessions.open(OWNER)
    yield Env(service, sessions, view.session_id, lab, settings, tmp_path / "runs")
    await service.shutdown()
    await sessions.shutdown()
    lab.reset()


def spec(kind: str, label: str, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "labels": [label], **extra}


def choose(target: dict[str, Any], choice: str, **extra: Any) -> dict[str, Any]:
    return {"op": "ensure_choice", "target": target, "choice": choice, **extra}


def equals(target: dict[str, Any], choice: str, **extra: Any) -> dict[str, Any]:
    return {
        "op": "assert_condition",
        "condition": {"type": "choice_equals", "target": target, "choice": choice, **extra},
    }


def scenario(env: Env, **values: Any) -> None:
    env.lab.control("PUT", "/__lab/scenario", json=values)


def commits(env: Env) -> list[str]:
    return list(env.lab.control("GET", "/__lab/state").json()["selection_commits"])


async def options(env: Env, target: dict[str, Any], open_list: bool = False) -> dict[str, Any]:
    service = ObservationService(env.sessions, picker_wait_max_ms=1000)
    return await service.choice_options(OWNER, env.sid, TargetSpec.model_validate(target), open_list)


def labels(result: dict[str, Any]) -> dict[str, str]:
    return {o["label"]: o["state"] for o in result["options"]}


def combo_ui(env: Env, name: str) -> Any:
    return env.page.get_by_role("combobox", name=name)


async def section_value(env: Env, section: str, label: str) -> str:
    field = env.page.get_by_role("region", name=section).get_by_label(label)
    return str(await field.input_value())


async def test_native_select_uses_label_and_verifies_real_value(env: Env) -> None:
    await env.goto("/pages/selections")
    target = spec(SELECT, "Merkez Kodu", region="Ürün")
    seen = await options(env, target)
    assert seen["status"] == "ok" and {o["label"]: o["value"] for o in seen["options"]}["Merkez"] == "M01"
    run = await env.run(
        [choose(target, "Merkez", expected_value="M01"), equals(target, "Merkez", expected_value="M01")]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await section_value(env, "Ürün", "Merkez Kodu") == "M01"


async def test_same_label_in_sections_is_separated(env: Env) -> None:
    await env.goto("/pages/selections")
    ambiguous = await env.run([choose(spec(SELECT, "Şube"), "Konak")], request_id="amb")
    assert ambiguous.status is RunStatus.PAUSED_AMBIGUOUS
    assert await section_value(env, "Başvuran", "Şube") == ""
    run = await env.run([choose(spec(SELECT, "Şube", region="Kefil"), "Konak")], request_id="kefil")
    assert run.status is RunStatus.COMPLETED
    assert await section_value(env, "Kefil", "Şube") == "konak"
    assert await section_value(env, "Başvuran", "Şube") == ""


async def test_marking_and_reading_options_changes_nothing(env: Env) -> None:
    await env.goto("/pages/selections")
    await env.page.evaluate("""() => { window.__ev = 0;
        for (const t of ['change','input','click','mousedown'])
          document.addEventListener(t, () => window.__ev++, true); }""")
    native = await options(env, spec(SELECT, "Şube", region="Kefil"))
    assert native["status"] == "ok"
    closed = await options(env, spec(COMBO, "Ürün Tipi"))
    assert closed["status"] == "needs_open" and closed["options"] == []
    assert await env.page.evaluate("window.__ev") == 0
    assert await combo_ui(env, "Ürün Tipi").get_attribute("aria-expanded") == "false"
    opened = await options(env, spec(COMBO, "Ürün Tipi"), open_list=True)
    assert labels(opened) == {
        "Bireysel Kart": "ok",
        "Ticari Kart": "ok",
        "Kapalı Kart": "disabled",
        "Çift Kart": "duplicate",
    }
    ui = combo_ui(env, "Ürün Tipi")
    assert await ui.get_attribute("aria-expanded") == "false" and "Seçiniz" in await ui.inner_text()


async def test_custom_dropdown_label_value_and_closed_after(env: Env) -> None:
    await env.goto("/pages/selections")
    target = spec(COMBO, "Ürün Tipi")
    run = await env.run(
        [
            choose(target, "Ticari Kart", expected_value="TCR"),
            equals(target, "Ticari Kart", expected_value="TCR"),
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    ui = combo_ui(env, "Ürün Tipi")
    assert (
        await ui.get_attribute("data-value") == "TCR" and await ui.get_attribute("aria-expanded") == "false"
    )


async def test_button_haspopup_and_inline_listbox(env: Env) -> None:
    await env.goto("/pages/selections")
    run = await env.run(
        [
            choose(spec(COMBO, "Kart Rengi"), "Gri", expected_value="GRY"),
            choose(spec(COMBO, "Teslimat Yöntemi"), "Kargo", expected_value="KRG"),
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await env.page.get_by_role("option", name="Kargo").get_attribute("aria-selected") == "true"


@pytest.mark.parametrize(
    ("kind", "label", "choice", "fragment"),
    [
        (SELECT, "Şube", "Kapalı Şube", "devre dışı"),
        (SELECT, "Şube", "Yinelenen Şube", "birden fazla"),
        (SELECT, "Şube", "Kon", "bulunamadı"),
        (SELECT, "Şube", "Seçiniz", "yer tutucu"),
    ],
)
async def test_native_bad_options_stop_without_change(
    env: Env, kind: str, label: str, choice: str, fragment: str
) -> None:
    await env.goto("/pages/selections")
    run = await env.run([choose(spec(kind, label, region="Kefil"), choice)], request_id=f"bad-{choice}")
    assert run.status is RunStatus.FAILED and run.steps[0].error_class == "BUSINESS_VALIDATION"
    assert fragment in (run.steps[0].message or "")
    assert await section_value(env, "Kefil", label) == ""


@pytest.mark.parametrize("choice", ["Kapalı Kart", "Çift Kart", "Ticari"])
async def test_custom_bad_options_stop_and_list_closes(env: Env, choice: str) -> None:
    await env.goto("/pages/selections")
    run = await env.run([choose(spec(COMBO, "Ürün Tipi"), choice)], request_id=f"cb-{choice}")
    assert run.status is RunStatus.FAILED and run.steps[0].error_class == "BUSINESS_VALIDATION"
    ui = combo_ui(env, "Ürün Tipi")
    assert await ui.get_attribute("aria-expanded") == "false" and "Seçiniz" in await ui.inner_text()


async def test_delayed_and_redrawn_options(env: Env) -> None:
    scenario(env, selection_options_delay_ms=700, selection_redraw=True)
    await env.goto("/pages/selections")
    run = await env.run(
        [
            choose(spec(COMBO, "Ürün Tipi"), "Ticari Kart", expected_value="TCR"),
            choose(spec(SELECT, "Bölge"), "Ege"),
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert await section_value(env, "Bağımlı Liste", "Bölge") == "ege"


async def test_design_time_list_is_not_trusted_at_runtime(env: Env) -> None:
    await env.goto("/pages/selections")
    target = spec(SELECT, "Merkez Kodu", region="Ürün")
    assert {o["label"]: o["value"] for o in (await options(env, target))["options"]}["Sahil"] == "S02"
    region = spec(SELECT, "Bölge")
    scenario(env, selection_catalog="changed")
    await env.goto("/pages/selections")
    moved = await env.run([choose(target, "Sahil", expected_value="S02")], request_id="value")
    assert moved.status is RunStatus.FAILED and "değeri farklı" in (moved.steps[0].message or "")
    assert await section_value(env, "Ürün", "Merkez Kodu") == ""
    gone = await env.run([choose(region, "Ege")], request_id="gone")
    assert gone.status is RunStatus.FAILED and gone.steps[0].error_class == "BUSINESS_VALIDATION"


async def test_nested_and_recreated_frames(env: Env) -> None:
    await env.goto("/pages/selections")
    target = spec(SELECT, "Teminat Türü", frame_title="Döviz Çerçevesi")
    custom = spec(COMBO, "Teminat Sınıfı", frame_title="Döviz Çerçevesi")
    first = await options(env, target)
    assert first["status"] == "ok"
    await env.page.evaluate("""() => { const f = document.querySelector('iframe[title="Teminat Çerçevesi"]');
        const n = f.cloneNode(); f.replaceWith(n); }""")
    await (
        env.page.frame_locator('iframe[title="Teminat Çerçevesi"]')
        .frame_locator('iframe[title="Döviz Çerçevesi"]')
        .get_by_label("Teminat Türü")
        .wait_for()
    )
    assert (await options(env, target))["status"] == "ok"
    run = await env.run(
        [
            choose(target, "Kefalet", expected_value="KFL"),
            choose(custom, "İkinci", expected_value="A2"),
            equals(custom, "İkinci"),
        ]
    )
    assert run.status is RunStatus.COMPLETED, run.model_dump()


async def test_control_behind_modal_is_not_used(env: Env) -> None:
    scenario(env, selection_modal=True)
    await env.goto("/pages/selections")
    behind = spec(SELECT, "Para Birimi", region="Ödeme")
    assert (await options(env, behind))["reason"] == "blocked"
    run = await env.run([choose(behind, "Dolar")])
    assert run.status is RunStatus.PAUSED_BLOCKED, run.model_dump()
    assert await section_value(env, "Ödeme", "Para Birimi") == ""
    inside = spec(SELECT, "Para Birimi", region="Döviz Onayı")
    assert (await options(env, inside))["status"] == "ok"


async def test_label_right_value_wrong_is_never_success(env: Env) -> None:
    scenario(env, selection_value_trap=True)
    await env.goto("/pages/selections")
    target = spec(COMBO, "Ürün Tipi")
    run = await env.run([choose(target, "Ticari Kart", expected_value="TCR", effect="unknown")])
    assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
    assert run.steps[0].state is StepState.OUTCOME_UNKNOWN


PRIORITY = spec(SELECT, "Öncelik", region="Kayıt Etkili")


async def test_result_condition_failure_is_not_success(env: Env) -> None:
    scenario(env, selection_outcome="reject")
    await env.goto("/pages/selections")
    check = {
        "op": "assert_condition",
        "condition": {
            "type": "text_present",
            "evidence": {"kind": "status_text"},
            "match": {"mode": "contains", "text": "Öncelik güncellendi"},
            "anchor": PRIORITY,
        },
    }
    run = await env.run([choose(PRIORITY, "Yüksek", effect="unknown"), equals(PRIORITY, "Yüksek"), check])
    assert run.status is RunStatus.FAILED and run.steps[1].state is StepState.SUCCEEDED
    assert run.steps[2].error_class == "VERIFICATION_FAILED"
    assert commits(env) == ["Y"]


async def test_result_condition_success(env: Env) -> None:
    await env.goto("/pages/selections")
    check = {
        "op": "assert_condition",
        "condition": {
            "type": "text_present",
            "evidence": {"kind": "status_text"},
            "match": {"mode": "contains", "text": "Öncelik güncellendi: Yüksek"},
            "anchor": PRIORITY,
        },
    }
    run = await env.run([choose(PRIORITY, "Yüksek", effect="unknown"), check])
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert commits(env) == ["Y"]


async def test_unknown_effect_is_not_reselected_when_result_unclear(env: Env) -> None:
    scenario(env, selection_outcome="revert")
    await env.goto("/pages/selections")
    run = await env.run([choose(PRIORITY, "Yüksek", effect="unknown")])
    assert run.status is RunStatus.OUTCOME_UNKNOWN, run.model_dump()
    assert run.steps[0].error_class == "WRITE_RESULT_UNKNOWN"
    assert commits(env) == ["Y"]  # tek gönderim
    resumed = await env.service.resume(OWNER, run.run_id, env.sid)
    resumed = await env.service.wait(resumed.run_id, 15)
    assert resumed.status is RunStatus.OUTCOME_UNKNOWN
    assert commits(env) == ["Y"]  # devam ettirme de yeniden seçmez


async def test_late_result_reconciled_by_reading_only(env: Env) -> None:
    scenario(env, selection_outcome="late")
    await env.goto("/pages/selections")
    run = await env.run([choose(PRIORITY, "Normal", effect="unknown")])
    assert run.status is RunStatus.COMPLETED, run.model_dump()
    assert run.steps[0].result["verified_by"] == "reconciliation"
    assert commits(env) == ["N"]


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (spec(SELECT, "Etiketler"), "multi_select_not_supported"),
        (spec(COMBO, "Şehir Ara"), "input_combobox_not_supported"),
    ],
)
async def test_unsupported_are_explained_without_interaction(
    env: Env, target: dict[str, Any], reason: str
) -> None:
    await env.goto("/pages/selections")
    result = await options(env, target, open_list=True)
    assert result["status"] == "unsupported" and result["reason"] == reason and result["message"]


async def test_list_that_cannot_be_read_is_unsupported_not_guessed(env: Env) -> None:
    await env.goto("/pages/selections")
    target = spec(COMBO, "Kırık Liste")
    assert (await options(env, target))["status"] == "needs_open"
    result = await options(env, target, open_list=True)
    assert result["status"] == "unsupported" and result["reason"] == "listbox_not_accessible"
    assert await combo_ui(env, "Kırık Liste").get_attribute("aria-expanded") == "false"
    run = await env.run([choose(target, "Bir Şey")])
    assert run.status is RunStatus.FAILED and run.steps[0].error_class == "CONTROL_UNSUPPORTED"
