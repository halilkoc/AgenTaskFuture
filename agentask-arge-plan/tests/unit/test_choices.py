"""Seçim adımı kuralları: seçenek eşleştirme, kararlı değer, sözleşme (catalog-v5) ve geriye uyum."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from agentask.application.controls import (
    AdapterRegistry,
    ChoiceNotAvailable,
    ControlUnsupported,
    VerificationFailed,
)
from agentask.application.ports.controls import ControlState
from agentask.domain.actions import ActionSet
from agentask.domain.catalog import (
    OperationDraft,
    ParameterDef,
    ParamSourceKind,
    StepStatus,
    bind_arguments,
    compile_operation,
    definition_schema,
)
from agentask.domain.choices import (
    ChoiceIssue,
    ChoiceOption,
    choice_key,
    describe_options,
    pick_option,
    stable_value,
)
from agentask.domain.commands import Command, bind_output, output_refs, rebase_output_refs
from agentask.domain.observation import ControlKind, ObservedControl
from agentask.domain.screens import ScreenDef
from agentask.domain.targeting import TargetSpec

Opt = ChoiceOption


def test_exact_match_only_no_partial_or_accent_folding() -> None:
    opts = [Opt("Çek", "1a"), Opt("Ek Kart", "2b")]
    assert pick_option(opts, "ÇEK")[0] == opts[0]
    assert pick_option(opts, "ek  kart")[0] == opts[1]
    assert pick_option(opts, "Cek") == (None, ChoiceIssue.MISSING)  # aksan farkı aynı seçenek sayılmaz
    assert pick_option(opts, "Ek") == (None, ChoiceIssue.MISSING)


@pytest.mark.parametrize(
    ("options", "issue"),
    [
        ([Opt("A", "a"), Opt("A", "b")], ChoiceIssue.DUPLICATE),
        ([Opt("A", "a", enabled=False)], ChoiceIssue.DISABLED),
        ([Opt("A", "")], ChoiceIssue.PLACEHOLDER),
        ([Opt("A", "b")], ChoiceIssue.VALUE_MISMATCH),
    ],
)
def test_unsafe_options_stop(options: list[ChoiceOption], issue: ChoiceIssue) -> None:
    assert pick_option(options, "A", "a" if issue is ChoiceIssue.VALUE_MISMATCH else None) == (None, issue)


def test_turkish_dotted_letters_stay_distinct() -> None:
    assert choice_key("İzmir") == choice_key("izmir")
    assert choice_key("Isparta") == choice_key("ısparta")
    assert choice_key("Isparta") != choice_key("ispartA")


def test_stable_value_rejects_index_and_generated_ids() -> None:
    index = [Opt("A", "0"), Opt("B", "1"), Opt("C", "2")]
    assert stable_value(index[0], index) is None
    meaningful = [Opt("Merkez", "M01"), Opt("Sahil", "S02")]
    assert stable_value(meaningful[0], meaningful) == "M01"
    generated = [Opt("X", "pz1a2b3c4d"), Opt("Y", "550e8400-e29b-41d4-a716-446655440000")]
    assert [stable_value(o, generated) for o in generated] == [None, None]
    codes = [Opt("TL", "949"), Opt("USD", "840")]  # sıra olmayan sayısal kodlar anlamlıdır
    assert stable_value(codes[0], codes) == "949"


def test_describe_marks_unselectable_without_hiding() -> None:
    out = describe_options(
        [Opt("Seçiniz", ""), Opt("A", "a"), Opt("A", "b"), Opt("K", "k", enabled=False), Opt("T", "t")]
    )
    assert [x["state"] for x in out] == ["placeholder", "duplicate", "duplicate", "disabled", "ok"]


# ---- adapter ------------------------------------------------------------------


def control(kind: ControlKind, tag: str, role: str = "", multiple: bool = False) -> ObservedControl:
    return ObservedControl(
        candidate_id="c",
        frame_ref="f",
        kind=kind,
        role=role or kind.value,
        accessible_name="Alan",
        label="Alan",
        visible=True,
        enabled=True,
        sensitive=False,
        has_value=False,
        selected_text=None,
        options=(),
        contexts=(),
        frame_titles=(),
        tag=tag,
        multiple=multiple,
    )


class Driver:
    def __init__(self, state: ControlState, options: list[ChoiceOption], after: ControlState) -> None:
        self.current, self.options, self.after = state, options, after
        self.calls: list[str] = []

    async def state(self, cid: str) -> ControlState:
        return self.current

    async def choice_options(self, cid: str) -> list[ChoiceOption]:
        return self.options

    async def listbox_options(self, cid: str) -> list[ChoiceOption]:
        return self.options

    async def await_options_change(self, cid: str, previous: list[ChoiceOption]) -> None:
        return None

    async def settle(self) -> None:
        self.calls.append("settle")

    async def select_option(self, cid: str, label: str) -> None:
        self.calls.append(f"select:{label}")
        self.current = self.after

    async def click(self, cid: str) -> None:
        self.calls.append("click")
        self.current = ControlState(
            selected_text=self.current.selected_text, expanded=not self.current.expanded
        )

    async def click_option(self, cid: str, label: str, trial: bool = False) -> None:
        self.calls.append(f"{'trial' if trial else 'option'}:{label}")
        if not trial:
            self.current = self.after


REG = AdapterRegistry.default()
NATIVE = control(ControlKind.SELECT, "select")
CUSTOM = control(ControlKind.COMBOBOX, "div", "combobox")


async def test_dispatch_callback_runs_before_selection_and_only_when_needed() -> None:
    d = Driver(
        ControlState(selected_text="Seçiniz", selected_value=""),
        [Opt("Merkez", "M01")],
        ControlState(selected_text="Merkez", selected_value="M01"),
    )
    order: list[str] = []

    async def mark() -> None:
        order.append(f"mark@{len(d.calls)}")

    assert (await REG.for_control(NATIVE).ensure_choice(d, NATIVE, "Merkez", on_dispatch=mark)).changed
    assert order == ["mark@0"] and d.calls[0] == "select:Merkez"
    order.clear()
    assert not (await REG.for_control(NATIVE).ensure_choice(d, NATIVE, "Merkez", on_dispatch=mark)).changed
    assert order == []


async def test_label_right_but_value_wrong_is_not_success() -> None:
    d = Driver(
        ControlState(selected_text="Seçiniz", expanded=False),
        [Opt("Ticari", "TCR")],
        ControlState(selected_text="Ticari", selected_value="YANLIS", expanded=False),
    )
    with pytest.raises(VerificationFailed, match="gerçek değer"):
        await REG.for_control(CUSTOM).ensure_choice(d, CUSTOM, "Ticari", expected_value="TCR")


async def test_value_mismatch_stops_before_any_selection() -> None:
    d = Driver(
        ControlState(selected_text="Seçiniz", selected_value=""), [Opt("Merkez", "X9")], ControlState()
    )
    with pytest.raises(ChoiceNotAvailable, match="değeri farklı"):
        await REG.for_control(NATIVE).ensure_choice(d, NATIVE, "Merkez", expected_value="M01")
    assert d.calls == []


async def test_inspection_never_opens_custom_list_without_explicit_request() -> None:
    d = Driver(ControlState(selected_text="Seçiniz", expanded=False), [Opt("A", "a")], ControlState())
    result = await REG.for_control(CUSTOM).inspect_options(d, CUSTOM, open_list=False)
    assert result.status == "needs_open" and d.calls == []
    opened = await REG.for_control(CUSTOM).inspect_options(d, CUSTOM, open_list=True)
    assert opened.status == "ok" and d.calls == ["click", "click"]  # aç + kapat; seçenek tıklanmaz


@pytest.mark.parametrize(
    ("c", "reason"),
    [
        (control(ControlKind.SELECT, "select", multiple=True), "multi_select"),
        (control(ControlKind.COMBOBOX, "ul", "listbox", multiple=True), "multi_select"),
        (control(ControlKind.COMBOBOX, "input", "combobox"), "input_combobox"),
    ],
)
def test_unsupported_kinds_are_explicit(c: ObservedControl, reason: str) -> None:
    with pytest.raises(ControlUnsupported, match=reason):
        REG.for_control(c)


# ---- sözleşme -------------------------------------------------------------------

ACTIONS = ActionSet()
TARGET: dict[str, Any] = {"kind": "select", "labels": ["Şube"], "region": "Kefil"}
SCREEN = ScreenDef(
    screen_id="s",
    title="Ekran",
    regions=[],
    markers=[TargetSpec(kind=ControlKind.BUTTON, labels=["Yardım"])],
    absent_markers=[],
)


def draft(**step: Any) -> OperationDraft:
    d = OperationDraft.new(created_by="a", application_id="lab", operation_id="op", title="T", description="")
    d.add_element("sube", "Şube", TARGET, "observed")
    card = d.add_step("Şube seç")
    card.op = "ensure_choice"
    card.element_id = "sube"
    card.status = StepStatus.READY_FOR_REVIEW
    for key, value in step.items():
        setattr(card, key, value)
    d.screen = SCREEN
    return d


def compiled(d: OperationDraft, args: dict[str, str] | None = None) -> list[dict[str, Any]]:
    return compile_operation(d, args or {}, ACTIONS)[1:]


def test_old_choice_step_compiles_and_hashes_exactly_as_before() -> None:
    d = draft(choice_template="Konak")
    assert compiled(d) == [
        {"op": "ensure_choice", "target": TARGET, "choice": "Konak"},
        {
            "op": "assert_condition",
            "condition": {"type": "choice_equals", "target": TARGET, "choice": "Konak"},
        },
    ]
    definition = d.definition()
    assert definition_schema(definition) == "catalog-v2"
    assert not set(definition["steps"][0]) & {"choice_value", "choice_effect", "result_text"}
    d.parameters = [ParameterDef(name="x", title="X", max_length=5, source=ParamSourceKind.USER_INPUT)]
    assert "choices" not in d.definition()["parameters"][0]


def test_new_fields_mark_v5_and_compile_value_and_effect() -> None:
    d = draft(
        choice_template="Konak", choice_value="konak", choice_effect="unknown", result_text="Güncellendi"
    )
    assert definition_schema(d.definition()) == "catalog-v5"
    plan = compiled(d)
    assert plan[0]["expected_value"] == "konak" and plan[0]["effect"] == "unknown"
    assert plan[1]["condition"]["expected_value"] == "konak"
    assert plan[2]["condition"]["type"] == "text_present" and plan[2]["condition"]["anchor"] == TARGET


def test_static_list_rejects_unknown_answer_and_maps_value() -> None:
    d = draft(choice_template="{sube}", choice_effect="ui_local")
    d.parameters = [
        ParameterDef.model_validate(
            {
                "name": "sube",
                "title": "Şube",
                "max_length": 200,
                "source": "user_input",
                "choices": [{"label": "Konak", "value": "konak"}, {"label": "Kadıköy"}],
            }
        )
    ]
    with pytest.raises(ValueError, match="invalid_choice"):
        bind_arguments(d, {"sube": "Kon"})
    plan = compiled(d, {"sube": "konak"})
    assert plan[0]["choice"] == "Konak" and plan[0]["expected_value"] == "konak"


def test_dynamic_list_is_not_limited_at_design_time() -> None:
    d = draft(choice_template="{sube}", choice_effect="ui_local")
    d.parameters = [
        ParameterDef(name="sube", title="Şube", max_length=200, source=ParamSourceKind.USER_INPUT)
    ]
    assert compiled(d, {"sube": "Sonradan Eklenen"})[0]["choice"] == "Sonradan Eklenen"


def test_prior_output_binds_choice_and_rebases() -> None:
    d = draft(choice_template="{okunan}", choice_effect="ui_local")
    read = d.add_step("Oku")
    read.op, read.element_id, read.status = "read", "sube", StepStatus.READY_FOR_REVIEW
    d.steps = [read, d.steps[0]]
    d.parameters = [
        ParameterDef(
            name="okunan", title="Okunan", max_length=200, source=ParamSourceKind.PRIOR_OUTPUT, prior_step=0
        )
    ]
    plan = compile_operation(d, {}, ACTIONS)
    choice = plan[2]
    assert choice["choice_from"] == {"step": 1, "max_length": 200} and "choice" not in choice
    assert not [i for i in d.validation_issues(ACTIONS) if "prior_output" in i]
    parsed = TypeAdapter(Command).validate_python(choice)
    assert [r.step for r in output_refs(parsed)] == [1]
    assert bind_output(choice, "Konak")["choice"] == "Konak"
    assert rebase_output_refs(choice, 4)["choice_from"]["step"] == 5


def test_unknown_effect_cannot_skip_result_check() -> None:
    d = draft(choice_template="Konak", choice_effect="unknown", success_check="none")
    assert any("choice_unverified" in i for i in d.validation_issues(ACTIONS))
    assert d.steps[0].effect(ACTIONS) == "unknown"
    assert draft(choice_template="Konak").steps[0].effect(ACTIONS) == "ui_local"


def test_duplicate_static_choices_rejected() -> None:
    with pytest.raises(ValueError, match="yinelenen"):
        ParameterDef.model_validate(
            {
                "name": "a",
                "title": "A",
                "max_length": 9,
                "source": "user_input",
                "choices": [{"label": "X"}, {"label": "x"}],
            }
        )
