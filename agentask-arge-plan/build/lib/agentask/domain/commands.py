"""Sınırlı komut dili: read, ensure_value, ensure_choice, activate_tab, find_record, invoke_approved_action,
assert_condition. Her komut tipli ve extra=forbid; selector, kod, URL veya serbest tıklama komutu yoktur."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentask.domain.actions import ActionSet, EvidenceSpec, TextMatch
from agentask.domain.observation import ControlKind
from agentask.domain.targeting import TargetSpec


class _Cmd(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_kind(spec: TargetSpec, *kinds: ControlKind) -> None:
    if spec.kind not in kinds:
        raise ValueError(f"hedef türü {', '.join(k.value for k in kinds)} olmalı")


class ReadCommand(_Cmd):
    op: Literal["read"]
    target: TargetSpec


class EnsureValueCommand(_Cmd):
    op: Literal["ensure_value"]
    target: TargetSpec
    value: str = Field(max_length=500)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.TEXTBOX)
        return self


class EnsureChoiceCommand(_Cmd):
    op: Literal["ensure_choice"]
    target: TargetSpec
    choice: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.SELECT, ControlKind.COMBOBOX)
        return self


class ActivateTabCommand(_Cmd):
    op: Literal["activate_tab"]
    target: TargetSpec

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.TAB)
        return self


class FindRecordCommand(_Cmd):
    op: Literal["find_record"]
    table: TargetSpec
    key: str = Field(min_length=1, max_length=200)
    navigation: Literal["none", "paged", "scroll"] = "none"
    next_labels: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=lambda: ["Sonraki"], max_length=5
    )
    end_text: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.table, ControlKind.TABLE)
        return self


class InvokeApprovedActionCommand(_Cmd):
    op: Literal["invoke_approved_action"]
    action_id: str = Field(pattern=r"^[a-z0-9_.]{3,80}$")
    params: dict[str, str] = Field(default_factory=dict)


class ValueEquals(_Cmd):
    type: Literal["value_equals"]
    target: TargetSpec
    value: str = Field(max_length=500)


class ChoiceEquals(_Cmd):
    type: Literal["choice_equals"]
    target: TargetSpec
    choice: str = Field(min_length=1, max_length=200)


class TabActive(_Cmd):
    type: Literal["tab_active"]
    target: TargetSpec


class TextPresent(_Cmd):
    type: Literal["text_present"]
    evidence: EvidenceSpec
    match: TextMatch


Condition = Annotated[ValueEquals | ChoiceEquals | TabActive | TextPresent, Field(discriminator="type")]


class AssertConditionCommand(_Cmd):
    op: Literal["assert_condition"]
    condition: Condition


class EvaluateConditionCommand(_Cmd):
    """Birleştirme fazı: koşulu değerlendirir ve sonucu kaydeder; asla başarısız olmaz (guard için)."""

    op: Literal["evaluate_condition"]
    condition: Condition


Command = Annotated[
    ReadCommand
    | EnsureValueCommand
    | EnsureChoiceCommand
    | ActivateTabCommand
    | FindRecordCommand
    | InvokeApprovedActionCommand
    | AssertConditionCommand
    | EvaluateConditionCommand,
    Field(discriminator="op"),
]


class PlanRejected(ValueError):
    def __init__(self, reason: str, step: int | None = None) -> None:
        self.reason = reason
        self.step = step
        super().__init__(reason if step is None else f"{reason} (adım {step + 1})")


def validate_plan(
    steps: list[Command], actions: ActionSet, max_steps: int, allow_composition: bool = False
) -> None:
    """Sunucu tarafı plan doğrulaması: adım bütçesi ve onaylı aksiyon/parametre uyumu."""
    if not allow_composition and any(isinstance(s, EvaluateConditionCommand) for s in steps):
        raise PlanRejected("composition_disabled")
    if not steps:
        raise PlanRejected("empty_plan")
    if len(steps) > max_steps:
        raise PlanRejected("too_many_steps")
    for index, step in enumerate(steps):
        if isinstance(step, InvokeApprovedActionCommand):
            action = actions.actions.get(step.action_id)
            if action is None:
                raise PlanRejected("unknown_action", index)
            declared = {p.name: p for p in action.params}
            if set(step.params) != set(declared):
                raise PlanRejected("params_mismatch", index)
            for name, value in step.params.items():
                if len(value) > declared[name].max_length or not value.strip():
                    raise PlanRejected("param_too_long" if value.strip() else "param_empty", index)
