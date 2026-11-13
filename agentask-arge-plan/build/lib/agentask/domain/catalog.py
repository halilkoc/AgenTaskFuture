"""Katalog taslağı (operation draft): adım kartları, elemanlar, parametre kaynakları, provenance, içerik
hash'i ve derleyici. Kalıcı tanımda selector/id/frame sırası/koordinat/URL yoktur; hedefler anlamsal
TargetSpec'tir."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import string
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentask.domain.actions import ActionSet
from agentask.domain.release import ApprovalRecord
from agentask.domain.targeting import TargetSpec

_SLUG = r"^[a-z][a-z0-9_]{0,60}$"
_SENSITIVE_WORDS = re.compile(r"(parola|şifre|sifre|password|pin|otp|cvv|cvc|güvenlik kodu)", re.IGNORECASE)
_REDACT_AFTER = re.compile(r"(?i)\b(parola\w*|şifre\w*|sifre\w*|password|pin|otp|cvv|cvc)\s+(\S+)")
_LONG_NUMBER = re.compile(r"\b\d{10,}\b")


def redact_intent(text: str) -> str:
    """Özgün niyetten hassas değerleri ayıklar (parola/pin sonrası kelime, 10+ haneli numaralar)."""
    text = _REDACT_AFTER.sub(lambda m: f"{m.group(1)} [gizli]", text)
    return _LONG_NUMBER.sub("[gizli]", text).strip()


def _now() -> datetime:
    return datetime.now(UTC)


class Provenance(StrEnum):
    OBSERVED = "observed"
    RULE_GENERATED = "rule_generated"
    MODEL_SUGGESTED = "model_suggested"
    HUMAN_VERIFIED = "human_verified"


class ParamSourceKind(StrEnum):
    USER_INPUT = "user_input"
    PRIOR_OUTPUT = "prior_output"
    APPROVED_CONSTANT = "approved_constant"
    SECRET_REF = "secret_ref"  # noqa: S105 - kaynak türü adı, secret değil


class ParameterDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=_SLUG)
    title: str = Field(min_length=1, max_length=100)
    max_length: int = Field(ge=1, le=500)
    required: bool = True
    source: ParamSourceKind
    constant: str | None = Field(default=None, max_length=500)
    secret_ref: str | None = Field(default=None, pattern=r"^[a-z]+:[A-Za-z0-9_./-]{1,120}$")
    prior_step: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        if (self.source is ParamSourceKind.APPROVED_CONSTANT) != (self.constant is not None):
            raise ValueError("approved_constant yalnız ve zorunlu olarak sabit değer taşır")
        if self.constant is not None and (_SENSITIVE_WORDS.search(self.name + " " + self.title)):
            raise ValueError("hassas görünen parametre sabit değer olamaz; secret_ref kullanın")
        if (self.source is ParamSourceKind.SECRET_REF) != (self.secret_ref is not None):
            raise ValueError("secret_ref yalnız ve zorunlu olarak referans adı taşır (değer değil)")
        if (self.source is ParamSourceKind.PRIOR_OUTPUT) != (self.prior_step is not None):
            raise ValueError("prior_output kaynak adım numarası gerektirir")
        return self


class ElementDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    element_id: str = Field(pattern=_SLUG)
    meaning: str = Field(min_length=1, max_length=200)
    target: TargetSpec
    provenance: Provenance


class StepStatus(StrEnum):
    INTENT_ENTERED = "intent_entered"
    TARGET_PROPOSED = "target_proposed"
    TARGET_SELECTED = "target_selected"
    MEANING_AND_TARGET_CONFIRMED = "meaning_and_target_confirmed"
    TRIAL_REQUESTED = "trial_requested"
    OBSERVED = "observed"
    OUTCOME_CONFIRMED = "outcome_confirmed"
    READY_FOR_REVIEW = "ready_for_review"


STEP_FLOW: dict[StepStatus, set[StepStatus]] = {
    StepStatus.INTENT_ENTERED: {StepStatus.TARGET_PROPOSED, StepStatus.TARGET_SELECTED},
    StepStatus.TARGET_PROPOSED: {StepStatus.TARGET_SELECTED, StepStatus.TARGET_PROPOSED},
    StepStatus.TARGET_SELECTED: {StepStatus.MEANING_AND_TARGET_CONFIRMED, StepStatus.TARGET_SELECTED},
    StepStatus.MEANING_AND_TARGET_CONFIRMED: {StepStatus.TRIAL_REQUESTED},
    StepStatus.TRIAL_REQUESTED: {StepStatus.OBSERVED},
    StepStatus.OBSERVED: {StepStatus.OUTCOME_CONFIRMED, StepStatus.TRIAL_REQUESTED},
    StepStatus.OUTCOME_CONFIRMED: {StepStatus.READY_FOR_REVIEW},
    StepStatus.READY_FOR_REVIEW: set(),
}


class IllegalStepTransition(ValueError):
    pass


class StepNotFound(KeyError):
    pass


class Confirmation(BaseModel):
    """Ayrı ayrı açık onaylar; tek 'Evet' hepsini birden onaylamaz."""

    model_config = ConfigDict(extra="forbid")
    meaning: bool
    target: bool
    effect: bool
    params: bool
    by: str
    at: datetime = Field(default_factory=_now)

    @property
    def complete(self) -> bool:
        return self.meaning and self.target and self.effect and self.params


class TrialEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    run_status: str
    verified: bool
    detail: str | None = None
    at: datetime = Field(default_factory=_now)


Op = Literal["ensure_value", "ensure_choice", "activate_tab", "find_record", "read", "invoke_approved_action"]


class StepCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    intent_text: str = Field(max_length=500)
    standard_text: str | None = Field(default=None, max_length=500)
    op: Op | None = None
    element_id: str | None = None
    value_template: str | None = Field(default=None, max_length=500)
    choice_template: str | None = Field(default=None, max_length=200)
    key_template: str | None = Field(default=None, max_length=200)
    navigation: Literal["none", "paged", "scroll"] = "none"
    action_id: str | None = None
    action_params: dict[str, str] = Field(default_factory=dict)
    success_check: Literal["auto", "none"] = "auto"
    status: StepStatus = StepStatus.INTENT_ENTERED
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    confirmation: Confirmation | None = None
    trial: TrialEvidence | None = None

    def move(self, status: StepStatus) -> None:
        if status not in STEP_FLOW[self.status]:
            raise IllegalStepTransition(f"{self.status} → {status}")
        if status is StepStatus.MEANING_AND_TARGET_CONFIRMED and not (
            self.confirmation and self.confirmation.complete
        ):
            raise IllegalStepTransition("anlam, hedef, etki ve parametre ayrı ayrı onaylanmalı")
        self.status = status

    def reset(self) -> None:
        """Tanım değişince onay ve deneme geçersizdir."""
        self.status = StepStatus.INTENT_ENTERED
        self.confirmation = None
        self.trial = None

    def effect(self, actions: ActionSet) -> str:
        if self.op == "invoke_approved_action":
            action = actions.actions.get(self.action_id or "")
            return action.effect if action else "unknown"
        if self.op in {"ensure_value", "ensure_choice", "activate_tab"}:
            return "ui_local"
        return "none"

    def definition(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
            include={
                "op",
                "element_id",
                "value_template",
                "choice_template",
                "key_template",
                "navigation",
                "action_id",
                "action_params",
                "success_check",
                "standard_text",
            },
        )

    def templates(self) -> list[str]:
        return [
            t
            for t in (
                self.value_template,
                self.choice_template,
                self.key_template,
                *self.action_params.values(),
            )
            if t
        ]


class FreshTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    passed: bool
    content_hash: str
    at: datetime = Field(default_factory=_now)


class OperationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    draft_id: str
    revision: int = 0
    application_id: str = Field(pattern=_SLUG)
    operation_id: str = Field(pattern=_SLUG)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    intent_phrases: list[str] = Field(default_factory=list, max_length=20)
    parameters: list[ParameterDef] = Field(default_factory=list)
    elements: dict[str, ElementDef] = Field(default_factory=dict)
    steps: list[StepCard] = Field(default_factory=list)
    created_by: str
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    fresh_test: FreshTest | None = None
    approval: ApprovalRecord | None = None  # sunucu tarafı, hash'e bağlı onay kaydı

    @classmethod
    def new(
        cls, *, created_by: str, application_id: str, operation_id: str, title: str, description: str
    ) -> Self:
        return cls(
            draft_id=f"draft-{secrets.token_urlsafe(8)}",
            created_by=created_by,
            application_id=application_id,
            operation_id=operation_id,
            title=title,
            description=description,
        )

    def add_element(
        self, element_id: str, meaning: str, target: dict[str, Any] | TargetSpec, provenance: str
    ) -> ElementDef:
        element = ElementDef(
            element_id=element_id,
            meaning=meaning,
            target=target if isinstance(target, TargetSpec) else TargetSpec.model_validate(target),
            provenance=Provenance(provenance),
        )
        self.elements[element_id] = element
        return element

    def add_step(self, intent_text: str) -> StepCard:
        step = StepCard(
            step_id=f"s{len(self.steps) + 1}-{secrets.token_hex(2)}", intent_text=redact_intent(intent_text)
        )
        self.steps.append(step)
        return step

    def step(self, step_id: str) -> StepCard:
        found = next((s for s in self.steps if s.step_id == step_id), None)
        if found is None:
            raise StepNotFound(step_id)
        return found

    def definition(self) -> dict[str, Any]:
        """Yayımlanacak tanımsal içerik (hash'in kapsadığı alanlar)."""
        return {
            "application_id": self.application_id,
            "operation_id": self.operation_id,
            "title": self.title,
            "description": self.description,
            "intent_phrases": self.intent_phrases,
            "parameters": [p.model_dump(mode="json") for p in self.parameters],
            "elements": {
                k: v.model_dump(mode="json", exclude={"provenance"}) for k, v in sorted(self.elements.items())
            },
            "steps": [s.definition() for s in self.steps],
        }

    @classmethod
    def from_definition(cls, definition: dict[str, Any], *, created_by: str) -> Self:
        """Yayımlanmış tanımdan çalıştırılabilir (derlenebilir) işlem modeli kurar."""
        draft = cls.new(
            created_by=created_by,
            application_id=definition["application_id"],
            operation_id=definition["operation_id"],
            title=definition["title"],
            description=definition.get("description", ""),
        )
        draft.intent_phrases = list(definition.get("intent_phrases", []))
        draft.parameters = [ParameterDef.model_validate(p) for p in definition["parameters"]]
        for element_id, element in definition["elements"].items():
            draft.add_element(element_id, element["meaning"], element["target"], "human_verified")
        draft.steps = [
            StepCard.model_validate(
                {"step_id": f"p{i}", "intent_text": "", **s, "status": StepStatus.READY_FOR_REVIEW}
            )
            for i, s in enumerate(definition["steps"])
        ]
        return draft

    def content_hash(self) -> str:
        canonical = self.definition()
        blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def record_fresh_test(self, run_id: str, passed: bool) -> None:
        self.fresh_test = FreshTest(run_id=run_id, passed=passed, content_hash=self.content_hash())

    def validation_issues(self, actions: ActionSet | None = None) -> list[str]:
        issues: list[str] = []
        declared = {p.name for p in self.parameters}
        if not self.steps:
            issues.append("no_steps")
        for i, step in enumerate(self.steps, start=1):
            if step.status is not StepStatus.READY_FOR_REVIEW:
                issues.append(f"step_{i}_not_ready")
            if step.op is None:
                issues.append(f"step_{i}_no_command")
            if step.op not in {None, "invoke_approved_action"} and step.element_id not in self.elements:
                issues.append(f"step_{i}_unknown_element:{step.element_id}")
            if (
                step.op == "invoke_approved_action"
                and actions is not None
                and step.action_id not in actions.actions
            ):
                issues.append(f"step_{i}_unknown_action:{step.action_id}")
            for template in step.templates():
                for _, name, _, _ in string.Formatter().parse(template):
                    if name and name not in declared:
                        issues.append(f"step_{i}_undeclared_param:{name}")
        if self.fresh_test is None:
            issues.append("fresh_session_test_missing")
        elif self.fresh_test.content_hash != self.content_hash():
            issues.append("fresh_session_test_stale")
        elif not self.fresh_test.passed:
            issues.append("fresh_session_test_failed")
        return issues

    @property
    def is_ready_for_review(self) -> bool:
        return not self.validation_issues()


def _render(template: str, values: dict[str, str]) -> str:
    return template.format_map({n: values[n] for _, n, _, _ in string.Formatter().parse(template) if n})


def compile_operation(
    draft: OperationDraft, args: dict[str, str], actions: ActionSet, steps: list[StepCard] | None = None
) -> list[dict[str, Any]]:
    """Taslağı P3 komut planına derler. Argümanlar tip/uzunluk/kaynak kurallarına göre doğrulanır."""
    declared = {p.name: p for p in draft.parameters}
    values: dict[str, str] = {}
    for name in args:
        if name not in declared:
            raise ValueError(f"unexpected_argument:{name}")
    for name, param in declared.items():
        if param.source is ParamSourceKind.APPROVED_CONSTANT:
            values[name] = param.constant or ""
            continue
        if param.source is ParamSourceKind.SECRET_REF:
            raise ValueError(f"secret_ref_not_supported:{name}")
        if name not in args:
            if param.required:
                raise ValueError(f"missing_argument:{name}")
            continue
        if len(args[name]) > param.max_length:
            raise ValueError(f"argument_too_long:{name}")
        values[name] = args[name]
    commands: list[dict[str, Any]] = []
    for step in steps if steps is not None else draft.steps:
        if step.op is None:
            raise ValueError(f"step_without_command:{step.step_id}")
        if step.op == "invoke_approved_action":
            if step.action_id not in actions.actions:
                raise ValueError(f"unknown_action:{step.action_id}")
            commands.append(
                {
                    "op": step.op,
                    "action_id": step.action_id,
                    "params": {k: _render(v, values) for k, v in step.action_params.items()},
                }
            )
            continue
        element = draft.elements.get(step.element_id or "")
        if element is None:
            raise ValueError(f"unknown_element:{step.element_id}")
        target = element.target.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        target.setdefault("kind", element.target.kind.value)
        if step.op == "ensure_value":
            value = _render(step.value_template or "", values)
            commands.append({"op": "ensure_value", "target": target, "value": value})
            if step.success_check == "auto":
                commands.append(
                    {
                        "op": "assert_condition",
                        "condition": {"type": "value_equals", "target": target, "value": value},
                    }
                )
        elif step.op == "ensure_choice":
            choice = _render(step.choice_template or "", values)
            commands.append({"op": "ensure_choice", "target": target, "choice": choice})
            if step.success_check == "auto":
                commands.append(
                    {
                        "op": "assert_condition",
                        "condition": {"type": "choice_equals", "target": target, "choice": choice},
                    }
                )
        elif step.op == "activate_tab":
            commands.append({"op": "activate_tab", "target": target})
            if step.success_check == "auto":
                commands.append(
                    {"op": "assert_condition", "condition": {"type": "tab_active", "target": target}}
                )
        elif step.op == "find_record":
            commands.append(
                {
                    "op": "find_record",
                    "table": target,
                    "key": _render(step.key_template or "", values),
                    "navigation": step.navigation,
                }
            )
        else:
            commands.append({"op": "read", "target": target})
    return commands
