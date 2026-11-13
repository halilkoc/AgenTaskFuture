"""Kontrollü birleştirme: statik doğrulama ve düzleştirme (docs/02 Sonraki faz)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentask.domain.catalog import OperationDraft
from agentask.domain.composition import CompositePlan, CompositionRejected, compile_composite
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from tests.unit.test_catalog_domain import draft as kefil_draft

OPS = {"kefil_no": kefil_draft()}
OPS["kefil_no"].operation_id = "kefil_no"


def lookup(op_id: str) -> OperationDraft | None:
    return OPS.get(op_id)


def plan(nodes: list[dict]) -> CompositePlan:
    return CompositePlan.model_validate({"nodes": nodes})


CALL = {"kind": "call_operation", "operation_id": "kefil_no", "arguments": {"musteri_no": "1"}}
COND = {
    "type": "value_equals",
    "target": {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"},
    "value": "1",
}


def compile_(p: CompositePlan, **kw: int) -> list[dict]:
    limits = {"max_depth": 3, "max_items": 5, "max_steps": 50, **kw}
    return compile_composite(p, lookup, LAB_ACTION_SET, **limits)


def test_flatten_call_if_and_guard() -> None:
    entries = compile_(plan([CALL, {"kind": "if", "condition": COND, "then": [CALL]}]))
    ops = [e["command"]["op"] for e in entries]
    assert ops == [
        "assert_screen",
        "ensure_value",
        "assert_condition",
        "evaluate_condition",
        "assert_screen",
        "ensure_value",
        "assert_condition",
    ]
    assert entries[4]["when"] == {"step": 3, "is": True} and entries[0]["when"] is None


def test_for_each_bounded_and_substitutes() -> None:
    loop = {
        "kind": "for_each",
        "variable": "no",
        "items": ["7", "8"],
        "body": [{"kind": "call_operation", "operation_id": "kefil_no", "arguments": {"musteri_no": "{no}"}}],
    }
    entries = compile_(plan([loop]))
    assert [e["command"].get("value") for e in entries if e["command"]["op"] == "ensure_value"] == ["7", "8"]
    with pytest.raises(CompositionRejected, match="too_many_items"):
        compile_(plan([{**loop, "items": [str(i) for i in range(6)]}]))


def test_depth_budget_and_unknown_operation() -> None:
    nested = {
        "kind": "if",
        "condition": COND,
        "then": [
            {
                "kind": "if",
                "condition": COND,
                "then": [
                    {
                        "kind": "if",
                        "condition": COND,
                        "then": [{"kind": "if", "condition": COND, "then": [CALL]}],
                    }
                ],
            }
        ],
    }
    with pytest.raises(CompositionRejected, match="too_deep"):
        compile_(plan([nested]))
    with pytest.raises(CompositionRejected, match="too_many_steps"):
        compile_(plan([CALL] * 10), max_steps=5)
    with pytest.raises(CompositionRejected, match="unknown_operation"):
        compile_(plan([{**CALL, "operation_id": "yok"}]))
    with pytest.raises(CompositionRejected, match="argument"):
        compile_(plan([{**CALL, "arguments": {}}]))


def test_free_form_nodes_rejected() -> None:
    with pytest.raises(ValidationError):
        plan([{"kind": "while", "condition": COND, "body": [CALL]}])
    with pytest.raises(ValidationError):
        plan([{"kind": "call_operation", "operation_id": "kefil_no", "arguments": {}, "js": "x"}])
    with pytest.raises(ValidationError):
        plan([{"kind": "for_each", "variable": "x", "items": [], "body": [CALL]}])


def test_loop_variable_cannot_use_format_attribute_access() -> None:
    loop = {
        "kind": "for_each",
        "variable": "no",
        "items": ["7"],
        "body": [
            {
                "kind": "call_operation",
                "operation_id": "kefil_no",
                "arguments": {"musteri_no": "{no.__class__}"},
            }
        ],
    }
    with pytest.raises(CompositionRejected, match="argument"):
        compile_(plan([loop]))
