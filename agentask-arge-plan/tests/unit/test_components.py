"""Ana plan E: sürümlü, yeniden kullanılabilir bileşenler (pinli call_operation)."""

from __future__ import annotations

import pytest

from agentask.domain.catalog import (
    CallSpec,
    OperationDraft,
    ParameterDef,
    compile_operation,
    definition_schema,
)
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from tests.wizard import CASE_NO, CUSTOMER_NO, CUSTOMER_SCREEN

GUARD = {"kind": "textbox", "labels": ["Müşteri No"], "region": "Müşteri"}


def component(title: str = "Müşteri no yaz ve vaka oku") -> OperationDraft:
    """Bileşen: müşteri numarasını yazar ve vaka numarasını okur (çıktı: vaka_no)."""
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="musteri_yaz", title=title, description=""
    )
    d.parameters.append(
        ParameterDef(name="musteri_no", title="Müşteri No", max_length=20, source="user_input")
    )
    d.add_element("musteri", "Müşteri numarası", CUSTOMER_NO, "observed")
    d.add_element("vaka_no", "Vaka numarası", CASE_NO, "observed")
    w = d.add_step("Müşteri numarasını yaz")
    w.op, w.element_id, w.value_template = "ensure_value", "musteri", "{musteri_no}"
    r = d.add_step("Vaka numarasını oku")
    r.op, r.element_id = "read", "vaka_no"
    d.screen = CUSTOMER_SCREEN
    return d


def caller(comp: OperationDraft, arguments: dict[str, str] | None = None) -> OperationDraft:
    d = OperationDraft.new(
        created_by="ayse", application_id="lab", operation_id="akis", title="Akış", description=""
    )
    d.parameters.append(ParameterDef(name="no", title="Müşteri no", max_length=20, source="user_input"))
    call = d.add_step("Bileşeni çağır")
    call.op = "call_operation"
    call.call = CallSpec.of(comp, 3, {"musteri_no": "{no}"} if arguments is None else arguments)
    d.parameters.append(
        ParameterDef(
            name="vaka",
            title="Vaka",
            max_length=20,
            source="prior_output",
            prior_step=0,
            prior_output="vaka_no",
        )
    )
    d.add_element("musteri2", "Müşteri no (tekrar)", CUSTOMER_NO, "observed")
    w = d.add_step("Okunan vakayı yaz")
    w.op, w.element_id, w.value_template = "ensure_value", "musteri2", "{vaka}"
    d.screen = CUSTOMER_SCREEN
    return d


def lookup_for(*ops: tuple[OperationDraft, int]):  # type: ignore[no-untyped-def]
    table = {(o.operation_id, r): o for o, r in ops}
    return lambda op, rev: table.get((op, rev))


def test_pinned_component_is_inlined_with_bound_inputs_and_outputs() -> None:
    comp = component()
    d = caller(comp)
    assert definition_schema(d.definition()) == "catalog-v4"
    assert definition_schema(comp.definition()) == "catalog-v2"  # bileşen yokken eski şema değişmez
    commands = compile_operation(d, {"no": "123"}, LAB_ACTION_SET, components=lookup_for((comp, 3)))
    ops = [c["op"] for c in commands]
    assert ops == [
        "assert_screen",  # çağıranın ekranı
        "assert_screen",  # bileşenin kendi ekran doğrulaması
        "ensure_value",
        "assert_condition",
        "read",
        "ensure_value",
        "assert_condition",
    ]
    assert commands[2]["value"] == "123"
    assert commands[5]["value_from"]["step"] == 4 and commands[4]["op"] == "read"
    assert d.validation_issues(LAB_ACTION_SET)[:1] != ["no_steps"]
    assert not [i for i in d.validation_issues(LAB_ACTION_SET) if "call" in i or "component" in i]


def test_component_without_resolver_or_missing_revision_is_rejected() -> None:
    d = caller(component())
    with pytest.raises(ValueError, match="component_missing:musteri_yaz@3"):
        compile_operation(d, {"no": "1"}, LAB_ACTION_SET)
    with pytest.raises(ValueError, match="component_missing"):
        compile_operation(d, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((component(), 4)))


def test_changed_component_under_same_pin_is_rejected() -> None:
    d = caller(component())
    changed = component(title="Değişmiş")  # aynı revizyon numarası, farklı içerik
    with pytest.raises(ValueError, match="component_hash_mismatch"):
        compile_operation(d, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((changed, 3)))


def test_missing_input_is_reported_and_not_compiled() -> None:
    comp = component()
    d = caller(comp, arguments={})
    assert "step_1_call_input_missing:musteri_no" in d.validation_issues(LAB_ACTION_SET)
    with pytest.raises(ValueError, match="component_input_missing:musteri_no"):
        compile_operation(d, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((comp, 3)))
    extra = caller(comp, arguments={"musteri_no": "{no}", "yok": "x"})
    assert "step_1_call_input_unknown:yok" in extra.validation_issues(LAB_ACTION_SET)


def test_incompatible_output_is_reported_and_not_compiled() -> None:
    comp = component()
    d = caller(comp)
    d.parameters = [
        p if p.name != "vaka" else p.model_copy(update={"prior_output": "olmayan"}) for p in d.parameters
    ]
    assert "param_vaka_component_output_unknown" in d.validation_issues(LAB_ACTION_SET)
    with pytest.raises(ValueError, match="prior_output_unavailable:vaka"):
        compile_operation(d, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((comp, 3)))


def test_invalid_screen_order_is_reported() -> None:
    comp = component()
    d = caller(comp)
    d.steps[0].call = d.steps[0].call.model_copy(update={"start_screen": "basvuru_teminat"})  # type: ignore[union-attr]
    assert any(i.startswith("step_1_call_screen_mismatch") for i in d.validation_issues(LAB_ACTION_SET))


def test_cycle_and_depth_are_rejected_before_running() -> None:
    a = component()
    b = caller(a)  # b → a
    b.operation_id = "musteri_yaz"  # a ile aynı kimlik: kendini çağırma
    assert "step_1_call_cycle" in b.validation_issues(LAB_ACTION_SET)
    with pytest.raises(ValueError, match="component_cycle"):
        compile_operation(b, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((a, 3)))
    # Dolaylı döngü: x → y → x (pinli revizyonlar üzerinden)
    x = caller(a)
    x.operation_id = "x"
    y = caller(a)
    y.operation_id = "y"
    y.steps[0].call = CallSpec.of(x, 1, {"no": "{no}"})
    x.steps[0].call = CallSpec.of(y, 1, {"no": "{no}"})
    with pytest.raises(ValueError, match=r"component_(cycle|hash_mismatch|contract_mismatch)"):
        compile_operation(x, {"no": "1"}, LAB_ACTION_SET, components=lookup_for((x, 1), (y, 1)))


def test_call_round_trips_through_published_definition() -> None:
    comp = component()
    d = caller(comp)
    again = OperationDraft.from_definition(d.definition(), created_by="catalog", screen=CUSTOMER_SCREEN)
    assert again.content_hash() == d.content_hash()
    assert again.steps[0].call == d.steps[0].call
