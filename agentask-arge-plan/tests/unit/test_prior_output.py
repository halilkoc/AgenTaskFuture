"""Önceki adım çıktısı (C3): okuma çıktısı yalnız çalışma anında, gerçek okumadan bağlanır."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from agentask.domain.catalog import OperationDraft, ParameterDef, compile_operation
from agentask.domain.commands import (
    Command,
    PlanRejected,
    bind_output,
    rebase_output_refs,
    validate_plan,
)
from agentask.domain.composition import CompositePlan, compile_composite
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from tests.screens import PARTIES_SCREEN

COMMAND_ADAPTER: TypeAdapter[Command] = TypeAdapter(Command)

CASE = {"kind": "textbox", "labels": ["Vaka No"], "region": "Vaka"}
GUAR = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Kefil"}


def draft(template: str = "{okunan}", prior_step: int = 0) -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="kopyala", title="Kopyala", description=""
    )
    d.add_element("vaka_no", "Vaka numarası", CASE, "observed")
    d.add_element("kefil_no", "Kefil numarası", GUAR, "observed")
    read = d.add_step("Vaka numarasını oku")
    read.op, read.element_id = "read", "vaka_no"
    write = d.add_step("Kefil numarasına yaz")
    write.op, write.element_id, write.value_template = "ensure_value", "kefil_no", template
    d.parameters.append(
        ParameterDef(
            name="okunan", title="Okunan vaka no", max_length=20, source="prior_output", prior_step=prior_step
        )
    )
    d.screen = PARTIES_SCREEN
    return d


def test_compiles_to_runtime_reference_not_a_value() -> None:
    commands = compile_operation(draft(), {}, LAB_ACTION_SET)
    ops = [c["op"] for c in commands]
    assert ops == ["assert_screen", "read", "ensure_value", "assert_condition"]
    assert commands[2]["value_from"] == {"step": 1, "max_length": 20}
    assert "value" not in commands[2]
    assert commands[3]["condition"]["value_from"] == {"step": 1, "max_length": 20}
    validate_plan([COMMAND_ADAPTER.validate_python(c) for c in commands], LAB_ACTION_SET, 50)


def test_prior_output_cannot_be_supplied_as_argument() -> None:
    with pytest.raises(ValueError, match="unexpected_argument:okunan"):
        compile_operation(draft(), {"okunan": "uydurma"}, LAB_ACTION_SET)


@pytest.mark.parametrize(
    ("template", "prior_step", "issue"),
    [
        ("Vaka {okunan}", 0, "step_2_prior_output_misuse:okunan"),  # karışık şablon yok
        ("{okunan}", 1, "param_okunan_prior_step_not_read"),  # kaynak okuma değil
        ("{okunan}", 5, "param_okunan_prior_step_not_read"),  # kaynak yok
    ],
)
def test_invalid_bindings_are_reported_and_not_compiled(template: str, prior_step: int, issue: str) -> None:
    d = draft(template, prior_step)
    assert issue in d.validation_issues(LAB_ACTION_SET)
    with pytest.raises(ValueError, match="prior_output"):
        compile_operation(d, {}, LAB_ACTION_SET)


def test_step_subset_without_source_read_is_rejected() -> None:
    d = draft()
    with pytest.raises(ValueError, match="prior_output_unavailable:okunan"):
        compile_operation(d, {}, LAB_ACTION_SET, steps=[d.steps[1]])


def test_plan_rejects_forward_or_non_read_reference() -> None:
    bad = [
        {"op": "ensure_value", "target": GUAR, "value_from": {"step": 1, "max_length": 5}},
        {"op": "read", "target": CASE},
    ]
    with pytest.raises(PlanRejected, match="invalid_output_ref"):
        validate_plan([COMMAND_ADAPTER.validate_python(c) for c in bad], LAB_ACTION_SET, 50)
    not_read = [
        {"op": "ensure_value", "target": CASE, "value": "x"},
        {"op": "ensure_value", "target": GUAR, "value_from": {"step": 0, "max_length": 5}},
    ]
    with pytest.raises(PlanRejected, match="invalid_output_ref"):
        validate_plan([COMMAND_ADAPTER.validate_python(c) for c in not_read], LAB_ACTION_SET, 50)


def test_reference_and_constant_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError):
        COMMAND_ADAPTER.validate_python(
            {"op": "ensure_value", "target": GUAR, "value": "x", "value_from": {"step": 0, "max_length": 5}}
        )


def test_context_checks_cannot_use_output_reference() -> None:
    plan = [
        {"op": "read", "target": CASE},
        {
            "op": "assert_screen",
            "screen": PARTIES_SCREEN.model_dump(mode="json"),
            "context": [{"type": "value_equals", "target": CASE, "value_from": {"step": 0, "max_length": 5}}],
        },
    ]
    with pytest.raises(PlanRejected, match="output_ref_not_allowed"):
        validate_plan([COMMAND_ADAPTER.validate_python(c) for c in plan], LAB_ACTION_SET, 50)


def test_bind_and_rebase_helpers() -> None:
    raw = {"op": "ensure_value", "target": GUAR, "value_from": {"step": 1, "max_length": 5}}
    assert bind_output(raw, "C-1") == {"op": "ensure_value", "target": GUAR, "value": "C-1"}
    assert rebase_output_refs(raw, 3)["value_from"]["step"] == 4
    cond = {
        "op": "assert_condition",
        "condition": {"type": "value_equals", "target": GUAR, "value_from": {"step": 1, "max_length": 5}},
    }
    assert rebase_output_refs(cond, 2)["condition"]["value_from"]["step"] == 3
    assert bind_output(cond, "C-1")["condition"]["value"] == "C-1"


def test_composition_rebases_references_of_flattened_operation() -> None:
    d = draft()
    plan = CompositePlan.model_validate(
        {"nodes": [{"kind": "call_operation", "operation_id": "kopyala"}] * 2}
    )
    entries = compile_composite(plan, lambda _: d, LAB_ACTION_SET, max_depth=3, max_items=5, max_steps=50)
    refs = [e["command"]["value_from"]["step"] for e in entries if e["command"]["op"] == "ensure_value"]
    assert refs == [1, 5]
    assert all(entries[r]["command"]["op"] == "read" for r in refs)
