"""Sınırlı komut dili ve onaylı aksiyon şeması (docs/02 Komut dili)."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from agentask.domain.actions import (
    ActionSet,
    AppProfile,
    ApprovedAction,
    EvidenceSpec,
    OutcomeSpec,
    ParamSpec,
    ReconcileSpec,
    TextMatch,
)
from agentask.domain.commands import Command, PlanRejected, validate_plan

COMMAND = TypeAdapter(Command)
TEXTBOX = {"kind": "textbox", "labels": ["Not"]}
BUTTON = {"kind": "button", "labels": ["Kaydet"]}


def action(**overrides: object) -> ApprovedAction:
    data: dict[str, object] = {
        "action_id": "lab.add_case_note",
        "title": "Vakaya not ekle",
        "target": BUTTON,
        "effect": "mutating",
        "retry_safe": False,
        "params": [{"name": "text", "title": "Not metni", "max_length": 200}],
        "outcome": {
            "evidence": {"kind": "status_text"},
            "success": {"mode": "prefix", "text": "Kaydedildi"},
            "unknown": [{"mode": "equals", "text": "Yanıt alınamadı — işlem sonucu bilinmiyor"}],
        },
        "reconcile": {
            "evidence": {"kind": "list_items", "name": "Mevcut notlar"},
            "match": {"mode": "contains", "text": "{text}"},
        },
    }
    data.update(overrides)
    return ApprovedAction.model_validate(data)


def action_set(*actions: ApprovedAction) -> ActionSet:
    return ActionSet(actions={a.action_id: a for a in actions}, blockers=[], profile=AppProfile())


@pytest.mark.parametrize(
    "payload",
    [
        {"op": "read", "target": TEXTBOX},
        {"op": "ensure_value", "target": TEXTBOX, "value": "007"},
        {"op": "ensure_choice", "target": {"kind": "select", "labels": ["Şube"]}, "choice": "Konak"},
        {"op": "ensure_choice", "target": {"kind": "combobox", "labels": ["Ürün Tipi"]}, "choice": "Ek Kart"},
        {"op": "activate_tab", "target": {"kind": "tab", "labels": ["Teslimat"]}},
        {
            "op": "find_record",
            "table": {"kind": "table", "labels": ["Başvurular"]},
            "key": "B-1003",
            "navigation": "paged",
        },
        {"op": "invoke_approved_action", "action_id": "lab.add_case_note", "params": {"text": "x"}},
        {"op": "assert_condition", "condition": {"type": "value_equals", "target": TEXTBOX, "value": "x"}},
        {
            "op": "assert_condition",
            "condition": {"type": "tab_active", "target": {"kind": "tab", "labels": ["A"]}},
        },
        {
            "op": "assert_condition",
            "condition": {
                "type": "text_present",
                "evidence": {"kind": "status_text"},
                "match": {"mode": "prefix", "text": "Kaydedildi"},
            },
        },
    ],
)
def test_supported_commands_parse(payload: dict[str, object]) -> None:
    assert COMMAND.validate_python(payload).op == payload["op"]


@pytest.mark.parametrize(
    "payload",
    [
        {"op": "click", "target": BUTTON},
        {"op": "eval", "code": "1+1"},
        {"op": "read", "target": TEXTBOX, "selector": "#x"},
        {"op": "read", "target": {**TEXTBOX, "xpath": "//input"}},
        {"op": "ensure_value", "target": {"kind": "select", "labels": ["Şube"]}, "value": "x"},
        {"op": "ensure_choice", "target": TEXTBOX, "choice": "x"},
        {"op": "activate_tab", "target": BUTTON},
        {"op": "find_record", "table": TEXTBOX, "key": "B-1"},
        {"op": "find_record", "table": {"kind": "table", "labels": ["T"]}, "key": ""},
        {"op": "invoke_approved_action", "action_id": "Lab Add; drop", "params": {}},
        {"op": "assert_condition", "condition": {"type": "js", "code": "true"}},
        {"op": "ensure_value", "target": TEXTBOX, "value": "x" * 501},
    ],
)
def test_unsupported_or_unsafe_commands_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        COMMAND.validate_python(payload)


def test_plan_rejects_unknown_action_and_wrong_params() -> None:
    known = action_set(action())
    ok = [
        COMMAND.validate_python(
            {"op": "invoke_approved_action", "action_id": "lab.add_case_note", "params": {"text": "a"}}
        )
    ]
    validate_plan(ok, known, max_steps=10)
    with pytest.raises(PlanRejected, match="unknown_action"):
        validate_plan(
            [COMMAND.validate_python({"op": "invoke_approved_action", "action_id": "lab.delete_all"})],
            known,
            max_steps=10,
        )
    with pytest.raises(PlanRejected, match="params_mismatch"):
        validate_plan(
            [
                COMMAND.validate_python(
                    {
                        "op": "invoke_approved_action",
                        "action_id": "lab.add_case_note",
                        "params": {"text": "a", "extra": "b"},
                    }
                )
            ],
            known,
            max_steps=10,
        )
    with pytest.raises(PlanRejected, match="param_too_long"):
        validate_plan(
            [
                COMMAND.validate_python(
                    {
                        "op": "invoke_approved_action",
                        "action_id": "lab.add_case_note",
                        "params": {"text": "a" * 201},
                    }
                )
            ],
            known,
            max_steps=10,
        )


def test_plan_step_budget() -> None:
    step = COMMAND.validate_python({"op": "read", "target": TEXTBOX})
    with pytest.raises(PlanRejected, match="too_many_steps"):
        validate_plan([step] * 3, action_set(), max_steps=2)
    with pytest.raises(PlanRejected, match="empty_plan"):
        validate_plan([], action_set(), max_steps=2)


def test_mutating_action_requires_target_outcome_and_reconcile() -> None:
    with pytest.raises(ValidationError):
        action(reconcile=None)
    with pytest.raises(ValidationError):
        action(outcome=None)
    with pytest.raises(ValidationError):
        action(target=None)
    with pytest.raises(ValidationError):
        action(target={"kind": "textbox", "labels": ["Not"]})
    with pytest.raises(ValidationError):
        action(effect="delete_everything")


def test_action_placeholders_must_be_declared_params() -> None:
    with pytest.raises(ValidationError):
        action(
            reconcile={
                "evidence": {"kind": "list_items", "name": "Mevcut notlar"},
                "match": {"mode": "contains", "text": "{secret}"},
            }
        )


def test_non_mutating_action_may_skip_reconcile() -> None:
    a = action(effect="non_mutating", retry_safe=True, reconcile=None)
    assert a.reconcile is None


def test_text_match_render_and_compare() -> None:
    m = TextMatch(mode="contains", text="{text}")
    assert m.matches("Not #1: Müşteri  arandı (ayse)", {"text": "Müşteri arandı"})
    assert not TextMatch(mode="equals", text="Kaydedildi").matches("Kaydedildi (Not #2)", {})
    assert TextMatch(mode="prefix", text="Kaydedildi").matches("Kaydedildi (Not #2)", {})


def test_list_items_evidence_requires_name() -> None:
    with pytest.raises(ValidationError):
        EvidenceSpec(kind="list_items")
    assert OutcomeSpec(evidence=EvidenceSpec(kind="status_text"), success=TextMatch(mode="prefix", text="A"))
    assert ReconcileSpec(
        evidence=EvidenceSpec(kind="list_items", name="L"), match=TextMatch(mode="contains", text="x")
    )
    assert ParamSpec(name="text", title="Metin", max_length=10)
