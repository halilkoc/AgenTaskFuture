"""Katalog taslağı, adım kartı durumları, parametre kaynakları, içerik hash'i ve derleyici (docs/04)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentask.domain.actions import ActionSet
from agentask.domain.catalog import (
    Confirmation,
    IllegalStepTransition,
    OperationDraft,
    ParameterDef,
    ParamSourceKind,
    StepCard,
    StepStatus,
    compile_operation,
    definition_schema,
    redact_intent,
)
from agentask.domain.routes import TransitionDef
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from tests.screens import ASSERT_PARTIES, PARTIES_SCREEN


def draft() -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse",
        application_id="lab",
        operation_id="add_guarantor_number",
        title="Kefil müşteri numarasını gir",
        description="Deney",
    )
    d.parameters.append(
        ParameterDef(name="musteri_no", title="Müşteri No", max_length=20, source="user_input")
    )
    d.add_element(
        "kefil_musteri_no",
        "Kefil müşteri numarası",
        {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"},
        "observed",
    )
    step = d.add_step("Kefil müşteri numarasını yaz")
    step.op = "ensure_value"
    step.element_id = "kefil_musteri_no"
    step.value_template = "{musteri_no}"
    step.success_check = "auto"
    d.screen = PARTIES_SCREEN
    return d


def ready(d: OperationDraft) -> None:
    for s in d.steps:
        s.move(StepStatus.TARGET_SELECTED)
        s.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")
        s.move(StepStatus.MEANING_AND_TARGET_CONFIRMED)
        s.move(StepStatus.TRIAL_REQUESTED)
        s.move(StepStatus.OBSERVED)
        s.move(StepStatus.OUTCOME_CONFIRMED)
        s.move(StepStatus.READY_FOR_REVIEW)


def test_step_flow_requires_order() -> None:
    step = draft().steps[0]
    with pytest.raises(IllegalStepTransition):
        step.move(StepStatus.TRIAL_REQUESTED)
    step.move(StepStatus.TARGET_SELECTED)
    with pytest.raises(IllegalStepTransition):
        step.move(StepStatus.MEANING_AND_TARGET_CONFIRMED)  # ayrı onaylar olmadan
    step.confirmation = Confirmation(meaning=True, target=True, effect=False, params=True, by="ayse")
    with pytest.raises(IllegalStepTransition):
        step.move(StepStatus.MEANING_AND_TARGET_CONFIRMED)  # etki onaylanmadı
    step.confirmation = Confirmation(meaning=True, target=True, effect=True, params=True, by="ayse")
    step.move(StepStatus.MEANING_AND_TARGET_CONFIRMED)


def test_content_hash_changes_only_with_definition() -> None:
    d = draft()
    h = d.content_hash()
    ready(d)
    assert d.content_hash() == h  # durum ilerlemesi içerik değildir
    d.steps[0].value_template = "{musteri_no} "
    assert d.content_hash() != h


def test_validation_issues_and_readiness() -> None:
    d = draft()
    assert "step_1_not_ready" in d.validation_issues()
    assert "fresh_session_test_missing" in d.validation_issues()
    ready(d)
    d.record_fresh_test(run_id="run-x", passed=True)
    assert d.validation_issues() == []
    assert d.is_ready_for_review


def test_edit_after_fresh_test_invalidates_readiness() -> None:
    d = draft()
    ready(d)
    d.record_fresh_test(run_id="run-x", passed=True)
    d.title = "Değişti"
    assert "fresh_session_test_stale" in d.validation_issues()


def test_undeclared_template_param_and_unknown_element_reported() -> None:
    d = draft()
    d.steps[0].value_template = "{baska}"
    d.steps[0].element_id = "yok"
    issues = d.validation_issues()
    assert "step_1_undeclared_param:baska" in issues and "step_1_unknown_element:yok" in issues


def test_param_sources() -> None:
    with pytest.raises(ValidationError):
        ParameterDef(name="sube", title="Şube", max_length=10, source="approved_constant")  # sabit yok
    with pytest.raises(ValidationError):
        ParameterDef(
            name="parola", title="Parola", max_length=10, source="approved_constant", constant="1234"
        )
    with pytest.raises(ValidationError):
        ParameterDef(name="x", title="X", max_length=10, source="user_input", constant="a")
    with pytest.raises(ValidationError):
        ParameterDef(name="p", title="P", max_length=10, source="secret_ref")  # referans yok
    ok = ParameterDef(name="p", title="P", max_length=10, source="secret_ref", secret_ref="vault:lab/p")
    assert "value" not in ok.model_dump()


def test_compile_operation_substitutes_and_validates_args() -> None:
    d = draft()
    commands = compile_operation(d, {"musteri_no": "00123"}, ActionSet())
    assert commands == [
        ASSERT_PARTIES,
        {
            "op": "ensure_value",
            "target": {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"},
            "value": "00123",
        },
        {
            "op": "assert_condition",
            "condition": {
                "type": "value_equals",
                "target": {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"},
                "value": "00123",
            },
        },
    ]
    with pytest.raises(ValueError, match="missing_argument"):
        compile_operation(d, {}, ActionSet())
    with pytest.raises(ValueError, match="unexpected_argument"):
        compile_operation(d, {"musteri_no": "1", "x": "2"}, ActionSet())
    with pytest.raises(ValueError, match="argument_too_long"):
        compile_operation(d, {"musteri_no": "1" * 21}, ActionSet())


def test_compile_approved_action_step() -> None:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="add_note", title="Not ekle", description=""
    )
    d.parameters.append(ParameterDef(name="metin", title="Not", max_length=200, source="user_input"))
    d.add_element("not_alani", "Not alanı", {"kind": "textbox", "labels": ["Not"]}, "observed")
    d.screen = PARTIES_SCREEN
    s1 = d.add_step("Notu yaz")
    s1.op, s1.element_id, s1.value_template, s1.success_check = "ensure_value", "not_alani", "{metin}", "none"
    s2 = d.add_step("Kaydet")
    s2.op, s2.action_id, s2.action_params = "invoke_approved_action", "lab.add_case_note", {"text": "{metin}"}
    assert s2.effect(LAB_ACTION_SET) == "mutating"
    commands = compile_operation(d, {"metin": "Arandı"}, LAB_ACTION_SET)
    assert commands[-1] == {
        "op": "invoke_approved_action",
        "action_id": "lab.add_case_note",
        "params": {"text": "Arandı"},
    }


def test_intent_redaction() -> None:
    assert redact_intent("Parolası Gizli123 olan alana yaz") == "Parolası [gizli] olan alana yaz"
    assert redact_intent("Kart 4111111111111111 numarasını gir") == "Kart [gizli] numarasını gir"
    assert redact_intent("Kefil müşteri no 00123 yaz") == "Kefil müşteri no 00123 yaz"


def test_step_card_rejects_selectors() -> None:
    with pytest.raises(ValidationError):
        StepCard.model_validate({"step_id": "s1", "intent_text": "x", "css": "#a"})


def test_template_rendering_is_not_python_format() -> None:
    d = draft()
    d.steps[0].value_template = "{musteri_no.__class__}"
    issues = d.validation_issues()
    assert any(i.startswith("step_1_invalid_template") for i in issues)
    with pytest.raises(ValueError, match="invalid_template"):
        compile_operation(d, {"musteri_no": "1"}, ActionSet())
    d.steps[0].value_template = "ön {musteri_no} son"
    assert compile_operation(d, {"musteri_no": "7"}, ActionSet())[1]["value"] == "ön 7 son"


BASE = {"steps": [], "parameters": [], "screen_ref": {"screen_id": "a", "content_hash": "x"}}


def test_new_optional_fields_do_not_change_old_definitions() -> None:
    """Eski yayınların içerik özeti korunur: yeni alanlar yalnız doluysa kanonik içeriğe girer."""
    param = ParameterDef(name="a", title="A", max_length=10, source=ParamSourceKind.USER_INPUT).definition()
    assert not {"multiple", "file", "choices"} & set(param)
    transition = TransitionDef.model_validate(
        {
            "transition_id": "git",
            "from_screen": "a",
            "to_screen": "b",
            "trigger": {"kind": "approved_action"},
        }
    ).definition()
    assert not {"window", "window_origin"} & set(transition)
    assert definition_schema({**BASE, "transitions": [transition]}) == "catalog-v3"


def test_window_and_optional_dialog_definitions_are_v6() -> None:
    window = {"trigger": {"kind": "control"}, "window": "new"}
    back = {"trigger": {"kind": "window_return", "close": True}}
    assert definition_schema({**BASE, "transitions": [window]}) == "catalog-v6"
    assert definition_schema({**BASE, "transitions": [back]}) == "catalog-v6"
    assert definition_schema({**BASE, "optional_dialogs": [{}]}) == "catalog-v6"
