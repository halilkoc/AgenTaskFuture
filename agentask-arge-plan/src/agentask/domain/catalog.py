"""Katalog taslağı (operation draft): adım kartları, elemanlar, parametre kaynakları, provenance, içerik
hash'i ve derleyici. Kalıcı tanımda selector/id/frame sırası/koordinat/URL yoktur; hedefler anlamsal
TargetSpec'tir."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentask.domain import templating
from agentask.domain.actions import ActionSet, KnownBlocker
from agentask.domain.artifacts import ALLOWED_CONTENT_TYPES, ARTIFACT_ID_PATTERN
from agentask.domain.choices import choice_key
from agentask.domain.commands import rebase_output_refs
from agentask.domain.dates import DateFormat, parse_date
from agentask.domain.release import ApprovalRecord
from agentask.domain.routes import ChoiceTrigger, ContextCheck, ControlTrigger, ReturnTrigger, TransitionDef
from agentask.domain.screens import ScreenDef, static_issues
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


class ChoiceItem(BaseModel):
    """Seçim parametresinin tasarım anında gözlenen tek seçeneği. value yalnız kararlıysa saklanır."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    label: str = Field(min_length=1, max_length=200)
    value: str | None = Field(default=None, min_length=1, max_length=200)


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
    # E: kaynak adım bileşen çağrısıysa (call_operation), bileşenin hangi çıktısı (okuma adımı element_id).
    prior_output: str | None = Field(default=None, pattern=_SLUG)
    # catalog-v5: geçerli seçenekler. None → liste kayda/ekrana göre değişebilir (çalışırken doğrulanır).
    choices: list[ChoiceItem] | None = Field(default=None, min_length=1, max_length=200)
    multiple: bool = False  # satır başına bir üye: "tam olarak bu küme"
    file: bool = False  # değer yalnız yetkili depodaki dosyanın kimliği olabilir

    def definition(self) -> dict[str, Any]:
        """Kanonik içerik: isteğe bağlı alanlar doluysa yazılır (eski revizyon hash'leri değişmez)."""
        unset = {
            k
            for k, keep in (
                ("choices", self.choices is not None),
                ("multiple", self.multiple),
                ("file", self.file),
            )
            if not keep
        }
        return self.model_dump(mode="json", exclude=unset or None)

    def members(self, raw: str) -> list[str]:
        return [line.strip() for line in raw.split("\n") if line.strip()]

    def choice_item(self, label: str) -> ChoiceItem | None:
        key = choice_key(label)
        return next((c for c in self.choices or [] if choice_key(c.label) == key), None)

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        if (self.multiple or self.file) and self.source is not ParamSourceKind.USER_INPUT:
            raise ValueError("çoklu seçim ve dosya parametresi yalnız kullanıcıdan alınır")
        if self.multiple and self.file:
            raise ValueError("dosya parametresi çoklu olamaz")
        if self.choices is not None:
            if self.source is not ParamSourceKind.USER_INPUT:
                raise ValueError("seçenek listesi yalnız kullanıcıdan alınan parametrede kullanılır")
            keys = [choice_key(c.label) for c in self.choices]
            if len(set(keys)) != len(keys):
                raise ValueError("seçenek listesinde yinelenen etiket var")
        if (self.source is ParamSourceKind.APPROVED_CONSTANT) != (self.constant is not None):
            raise ValueError("approved_constant yalnız ve zorunlu olarak sabit değer taşır")
        if self.constant is not None and (_SENSITIVE_WORDS.search(self.name + " " + self.title)):
            raise ValueError("hassas görünen parametre sabit değer olamaz; secret_ref kullanın")
        if (self.source is ParamSourceKind.SECRET_REF) != (self.secret_ref is not None):
            raise ValueError("secret_ref yalnız ve zorunlu olarak referans adı taşır (değer değil)")
        if (self.source is ParamSourceKind.PRIOR_OUTPUT) != (self.prior_step is not None):
            raise ValueError("prior_output kaynak adım numarası gerektirir")
        if self.prior_output is not None and self.source is not ParamSourceKind.PRIOR_OUTPUT:
            raise ValueError("bileşen çıktısı yalnız prior_output kaynağında kullanılır")
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


Op = Literal[
    "ensure_value",
    "ensure_choice",
    "ensure_checked",
    "ensure_choices",
    "ensure_date",
    "upload_file",
    "activate_tab",
    "find_record",
    "read",
    "invoke_approved_action",
    "follow_transition",  # R4: yalnız ekran değiştiren onaylı kontrol (iş etkisi yok)
    "call_operation",  # E: yayımlanmış bir işlemi (bileşen) revizyonuna pinli çağırır
]

MAX_COMPONENT_DEPTH = 3


class CallSpec(BaseModel):
    """E (catalog-v4): yeniden kullanılabilir bileşen çağrısı. Bileşen = yayımlanmış işlem; çağrı belirli bir
    değişmez revizyona (ve içerik hash'ine) pinlidir, yeni revizyon yayımlanınca kendiliğinden değişmez.

    inputs/outputs/start_screen/end_screen pinlenen revizyondan alınmış özetlerdir; statik doğrulama (rota,
    girdi, çıktı) içindir; derlemede gerçek bileşenle yeniden karşılaştırılır (uyuşmazlık → derleme reddi)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str = Field(pattern=_SLUG)
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=8, max_length=128)
    arguments: dict[str, str] = Field(default_factory=dict)  # bileşen parametresi → çağıranın şablonu
    inputs: list[str] = Field(default_factory=list)  # bileşenin kullanıcıdan istediği parametreler
    outputs: list[str] = Field(default_factory=list)  # bileşenin okuma adımları (element_id)
    start_screen: str = Field(pattern=_SLUG)
    end_screen: str = Field(pattern=_SLUG)

    @field_validator("arguments")
    @classmethod
    def _safe(cls, value: dict[str, str]) -> dict[str, str]:
        for template in value.values():
            if len(template) > 500 or not templating.is_valid(template):
                raise ValueError("bileşen argümanı yalnız {parametre} yer tutucuları içerebilir")
        return value

    @classmethod
    def of(cls, component: OperationDraft, revision: int, arguments: dict[str, str]) -> CallSpec:
        if component.screen is None or not component.steps:
            raise ValueError("component_not_runnable")
        last = component.steps[-1]
        end = component.route_end()
        return cls(
            operation_id=component.operation_id,
            revision=revision,
            content_hash=component.content_hash(),
            arguments=dict(arguments),
            inputs=component_inputs(component),
            outputs=component_outputs(component),
            start_screen=component.screen.screen_id,
            end_screen=end or last.screen_id or component.screen.screen_id,
        )


def component_inputs(op: OperationDraft) -> list[str]:
    return [p.name for p in op.parameters if p.source is ParamSourceKind.USER_INPUT]


def component_outputs(op: OperationDraft) -> list[str]:
    return [s.element_id for s in op.steps if s.op == "read" and s.element_id]


def _call_issues(i: int, step: StepCard, own_operation: str, expected: str) -> list[str]:
    call = step.call
    if step.op != "call_operation" or call is None:
        return [f"step_{i}_call_missing"]
    issues: list[str] = []
    if call.operation_id == own_operation:
        issues.append(f"step_{i}_call_cycle")
    if call.start_screen != expected:
        issues.append(f"step_{i}_call_screen_mismatch:{expected}:{call.start_screen}")
    for name in call.inputs:
        if name not in call.arguments:
            issues.append(f"step_{i}_call_input_missing:{name}")
    for name in sorted(set(call.arguments) - set(call.inputs)):
        issues.append(f"step_{i}_call_input_unknown:{name}")
    return issues


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
    action_hash: str | None = Field(default=None, min_length=16, max_length=128)  # catalog-v6
    # catalog-v6: Kayıt bul gezintisi ve bulunan satırda çalışma.
    checked: bool | None = None  # op=ensure_checked
    choice_set: list[str] | None = Field(
        default=None, min_length=1, max_length=50
    )  # op=ensure_choices, sabit küme
    date_format: DateFormat | None = None  # op=ensure_date
    file_types: list[str] | None = Field(default=None, min_length=1, max_length=4)  # op=upload_file
    autocomplete: bool = False
    search_text: str | None = Field(default=None, min_length=1, max_length=200)
    next_labels: list[str] | None = Field(default=None, max_length=5)
    end_text: str | None = Field(default=None, min_length=1, max_length=200)
    in_found_row: bool = False
    success_check: Literal["auto", "none"] = "auto"
    # catalog-v5 (seçim adımı): sabit seçeneğin kararlı değeri, analistin etki beyanı, beklenen durum mesajı.
    choice_value: str | None = Field(default=None, min_length=1, max_length=200)
    choice_effect: Literal["ui_local", "unknown"] | None = None
    result_text: str | None = Field(default=None, min_length=1, max_length=300)
    # R4: adımın beklenen ekranı (boşsa başlangıç ekranı) ve tetiklediği onaylı geçiş (ekran değiştirir).
    screen_id: str | None = Field(default=None, pattern=_SLUG)
    transition_id: str | None = Field(default=None, pattern=_SLUG)
    call: CallSpec | None = None  # E: op=call_operation
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
        if self.op == "upload_file":
            return "unknown"
        if (
            self.op in {"ensure_choice", "ensure_checked", "ensure_choices"}
            and self.choice_effect == "unknown"
        ):
            return "unknown"  # sistem iş etkisini bilemez; ne yalnız ekran ne de veri değişikliği varsayılır
        if self.op in {
            "ensure_value",
            "ensure_choice",
            "ensure_checked",
            "ensure_choices",
            "ensure_date",
            "activate_tab",
        }:
            return "ui_local"
        if self.op == "call_operation":
            return "component"  # bileşenin içeriğine bağlı; veri değiştirebilir kabul edilir
        return "none"

    @property
    def changes_screen(self) -> bool:
        """Ekran değiştiren adım (iş etkisinden bağımsız)."""
        return self.transition_id is not None

    def definition(self) -> dict[str, Any]:
        # Tek ekranlı adımda R4 alanları kanonik içeriğe girmez: catalog-v2 hash'leri değişmez.
        extra: dict[str, Any] = {
            k: v
            for k, v in (
                ("screen_id", self.screen_id),
                ("transition_id", self.transition_id),
                ("choice_value", self.choice_value),
                ("choice_effect", self.choice_effect),
                ("result_text", self.result_text),
                ("action_hash", self.action_hash),
                ("next_labels", self.next_labels),
                ("end_text", self.end_text),
                ("in_found_row", self.in_found_row),
                ("autocomplete", self.autocomplete),
                ("search_text", self.search_text),
                ("choice_set", self.choice_set),
                ("date_format", self.date_format),
                ("file_types", self.file_types),
            )
            if v
        }
        if self.checked is not None:
            extra["checked"] = self.checked
        if self.call is not None:  # catalog-v4; diğer adımların kanonik içeriği değişmez
            extra["call"] = self.call.model_dump(mode="json")
        return extra | self.model_dump(
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
                *(self.call.arguments.values() if self.call else ()),
            )
            if t
        ]


class FreshTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    passed: bool
    content_hash: str
    at: datetime = Field(default_factory=_now)


class MigrationSource(BaseModel):
    """Geçiş taslağının kaynağı: ekran tanımı olmayan eski yayımlanmış revizyon (yerinde değiştirilmez)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    release_id: str
    operation_id: str
    revision: int
    content_hash: str


def requires_migration(definition: dict[str, Any]) -> bool:
    """Ekran tanımı (screen_ref) olmayan yayımlanmış işlem tanımı eski (catalog-v1) sayılır."""
    return not isinstance(definition.get("screen_ref"), dict)


_V3_KEYS = ("screens_ref", "transitions", "start_context")
_V5_STEP_KEYS = {"choice_value", "choice_effect", "result_text"}
_V6_STEP_KEYS = {
    "action_hash",
    "next_labels",
    "end_text",
    "in_found_row",
    "checked",
    "autocomplete",
    "search_text",
    "choice_set",
    "date_format",
    "file_types",
}
_KNOWN_KEYS = {
    "application_id",
    "operation_id",
    "title",
    "description",
    "intent_phrases",
    "parameters",
    "elements",
    "steps",
    "screen_ref",
    *_V3_KEYS,
    "optional_dialogs",
}


def definition_schema(definition: dict[str, Any]) -> str:
    """Tanımın kendi içeriğinden şema sürümü: v1 (ekransız), v2 (tek ekran, R3), v3 (çok ekran, R4).
    Tanınmayan anahtar içeren tanım 'unknown' döner ve okunmaz (ileri sürüm sessizce yorumlanmaz)."""
    if set(definition) - _KNOWN_KEYS:
        return "unknown"
    if requires_migration(definition):
        return "catalog-v1"
    if (
        "optional_dialogs" in definition
        or any(set(s) & _V6_STEP_KEYS for s in definition.get("steps", []))
        or any(
            "window" in t or t["trigger"]["kind"] == "window_return"
            for t in definition.get("transitions", [])
        )
    ):
        return "catalog-v6"
    if any(set(s) & _V5_STEP_KEYS for s in definition.get("steps", [])) or any(
        "choices" in p for p in definition.get("parameters", [])
    ):
        return "catalog-v5"
    if any("call" in s for s in definition.get("steps", [])):
        return "catalog-v4"
    steps_v3 = any("screen_id" in s or "transition_id" in s for s in definition.get("steps", []))
    return "catalog-v3" if steps_v3 or any(k in definition for k in _V3_KEYS) else "catalog-v2"


def screen_refs(definition: dict[str, Any]) -> set[tuple[str, str]]:
    """Tanımın referans verdiği bütün ekran revizyonları (screen_id, içerik hash'i)."""
    refs = [definition.get("screen_ref"), *definition.get("screens_ref", [])]
    return {(r["screen_id"], r["content_hash"]) for r in refs if isinstance(r, dict)}


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
    screen: ScreenDef | None = None  # R3: işlemin (başlangıç) ekranı; hash'e screen_ref ile girer
    migrated_from: MigrationSource | None = None
    # R4 (catalog-v3): diğer ekranlar, onaylı geçişler ve başlangıç kayıt bağlamı.
    extra_screens: list[ScreenDef] = Field(default_factory=list, max_length=9)
    transitions: list[TransitionDef] = Field(default_factory=list, max_length=10)
    start_context: list[ContextCheck] = Field(default_factory=list, max_length=5)
    optional_dialogs: list[KnownBlocker] = Field(default_factory=list, max_length=10)

    @property
    def is_multi_screen(self) -> bool:
        return bool(
            self.extra_screens or self.transitions or self.start_context or any(s.call for s in self.steps)
        )

    def all_screens(self) -> dict[str, ScreenDef]:
        return {s.screen_id: s for s in ([self.screen] if self.screen else []) + list(self.extra_screens)}

    def transition(self, transition_id: str | None) -> TransitionDef | None:
        return next((t for t in self.transitions if t.transition_id == transition_id), None)

    def route(self) -> dict[str, str | None]:
        """Her adımın beklenen ekranı: açık screen_id, yoksa rota üzerindeki o anki ekran (başlangıçtan
        itibaren, her geçiş adımından sonra hedef ekran)."""
        current = self.screen.screen_id if self.screen else None
        out: dict[str, str | None] = {}
        for step in self.steps:
            out[step.step_id] = step.screen_id or current
            transition = self.transition(step.transition_id)
            current = (
                step.call.end_screen
                if step.call is not None
                else transition.to_screen
                if transition
                else out[step.step_id]
            )
        return out

    def route_end(self) -> str | None:
        """Son adımdan sonra etkin olan ekran (bileşen olarak çağrıldığında çağıranın devam ekranı)."""
        current = self.screen.screen_id if self.screen else None
        for step in self.steps:
            current = step.screen_id or current
            transition = self.transition(step.transition_id)
            current = step.call.end_screen if step.call else transition.to_screen if transition else current
        return current

    def step_screen_id(self, step: StepCard) -> str | None:
        return self.route().get(
            step.step_id, step.screen_id or (self.screen.screen_id if self.screen else None)
        )

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
            "parameters": [p.definition() for p in self.parameters],
            "elements": {
                k: v.model_dump(mode="json", exclude={"provenance"}) for k, v in sorted(self.elements.items())
            },
            "steps": [s.definition() for s in self.steps],
            **({"screen_ref": self.screen.ref()} if self.screen is not None else {}),
            **({"screens_ref": [s.ref() for s in self.extra_screens]} if self.extra_screens else {}),
            **({"transitions": [t.definition() for t in self.transitions]} if self.transitions else {}),
            **(
                {"start_context": [c.model_dump(mode="json") for c in self.start_context]}
                if self.start_context
                else {}
            ),
            **(
                {"optional_dialogs": [d.model_dump(mode="json") for d in self.optional_dialogs]}
                if self.optional_dialogs
                else {}
            ),
        }

    @classmethod
    def from_definition(
        cls,
        definition: dict[str, Any],
        *,
        created_by: str,
        screen: ScreenDef | None = None,
        extra_screens: list[ScreenDef] | None = None,
    ) -> Self:
        """Yayımlanmış tanımdan çalıştırılabilir (derlenebilir) işlem modeli kurar. Tanım ekran revizyonlarına
        bağlıysa o ekranlar (hash'leri eşleşerek) verilmelidir; eski tanımda ekran yoktur."""
        wanted = [(r.get("screen_id"), r.get("content_hash")) for r in definition.get("screens_ref", [])]
        given = [(s.screen_id, s.content_hash()) for s in extra_screens or []]
        if wanted != given:
            raise ValueError("screen_revision_mismatch")
        ref = definition.get("screen_ref")
        if ref is not None and (
            screen is None
            or ref.get("screen_id") != screen.screen_id
            or ref.get("content_hash") != screen.content_hash()
        ):
            raise ValueError("screen_revision_mismatch")
        if ref is None and screen is not None:
            raise ValueError("screen_not_referenced")
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
        draft.screen = screen
        draft.extra_screens = list(extra_screens or [])
        draft.transitions = [TransitionDef.model_validate(x) for x in definition.get("transitions", [])]
        draft.start_context = [ContextCheck.model_validate(x) for x in definition.get("start_context", [])]
        draft.optional_dialogs = [
            KnownBlocker.model_validate(x) for x in definition.get("optional_dialogs", [])
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
            if (
                step.op not in {None, "invoke_approved_action", "follow_transition", "call_operation"}
                and step.element_id not in self.elements
            ):
                issues.append(f"step_{i}_unknown_element:{step.element_id}")
            if step.op == "invoke_approved_action" and actions is not None:
                problem = actions.problem(step.action_id, step.action_hash, self.application_id)
                if problem is not None:
                    issues.append(f"step_{i}_{problem}:{step.action_id}")
            if step.op == "ensure_choice":
                issues += _choice_issues(i, step)
            if step.op == "ensure_checked":
                issues += _checked_issues(i, step)
            if step.op == "ensure_choices":
                issues += _choices_issues(i, step, self)
            if step.op == "ensure_date":
                issues += _date_issues(i, step)
            if step.op == "upload_file":
                issues += _upload_issues(i, step, self)
            if step.in_found_row and not any(x.op == "find_record" for x in self.steps[: i - 1]):
                issues.append(f"step_{i}_row_without_record")
            for template in step.templates():
                if not templating.is_valid(template):
                    issues.append(f"step_{i}_invalid_template")
                    continue
                for name in sorted(templating.placeholders(template)):
                    if name not in declared:
                        issues.append(f"step_{i}_undeclared_param:{name}")
        issues += self._prior_output_issues()
        if self.is_multi_screen:
            issues += self._route_issues(declared, actions)
        else:
            issues += static_issues(
                self.screen,
                {k: v.target for k, v in self.elements.items()},
                [s.element_id for s in self.steps if s.element_id],
            )
        if self.fresh_test is None:
            issues.append("fresh_session_test_missing")
        elif self.fresh_test.content_hash != self.content_hash():
            issues.append("fresh_session_test_stale")
        elif not self.fresh_test.passed:
            issues.append("fresh_session_test_failed")
        return issues

    def _prior_output_issues(self) -> list[str]:
        """Önceki adım çıktısı: kaynak, daha önceki bir 'read' adımı olmalı; çıktı yalnız sonraki bir
        'ensure_value' adımının değer şablonunda tek başına ({ad}) kullanılabilir."""
        issues: list[str] = []
        prior = {p.name: p for p in self.parameters if p.source is ParamSourceKind.PRIOR_OUTPUT}
        for name, param in prior.items():
            at = param.prior_step if param.prior_step is not None else len(self.steps)
            source = self.steps[at] if at < len(self.steps) else None
            if source is not None and source.op == "call_operation":
                if source.call is None or param.prior_output not in source.call.outputs:
                    issues.append(f"param_{name}_component_output_unknown")
            elif source is None or source.op != "read" or param.prior_output is not None:
                issues.append(f"param_{name}_prior_step_not_read")
        for i, step in enumerate(self.steps):
            for template in step.templates():
                for name in sorted(templating.placeholders(template) & set(prior)):
                    param = prior[name]
                    own = (
                        template
                        if step.op in {"invoke_approved_action", "call_operation"}
                        else _direct_template(step)
                    )
                    if (
                        template != own
                        or template != f"{{{name}}}"
                        or param.prior_step is None
                        or param.prior_step >= i
                    ):
                        issues.append(f"step_{i + 1}_prior_output_misuse:{name}")
        return issues

    def _route_issues(self, declared: set[str], actions: ActionSet | None) -> list[str]:
        """R4 statik rota: adımlar ekranları sırayla izler; geçişin kaynağı o anki ekrandır, adımdan sonra
        hedef
        ekran etkin olur. Her ekranın işaretleri o ekrandaki hedeflerden ibaret olamaz."""
        if self.screen is None:
            return ["screen_missing"]
        issues: list[str] = []
        screens = self.all_screens()
        if len(screens) != 1 + len(self.extra_screens):
            issues.append("duplicate_screen_id")
        ids = [t.transition_id for t in self.transitions]
        if len(set(ids)) != len(ids):
            issues.append("duplicate_transition_id")
        for t in self.transitions:
            for end in (t.from_screen, t.to_screen):
                if end not in screens:
                    issues.append(f"transition_unknown_screen:{t.transition_id}:{end}")
            for name in sorted(t.placeholders()):
                if name not in declared:
                    issues.append(f"transition_undeclared_param:{t.transition_id}:{name}")
        for check in self.start_context:
            for name in sorted(templating.placeholders(check.value_template)):
                if name not in declared:
                    issues.append(f"start_context_undeclared_param:{name}")
        current = self.screen.screen_id
        used_on: dict[str, list[str]] = {s: [] for s in screens}
        used_transitions: list[str] = []
        window_open = False
        for i, step in enumerate(self.steps, start=1):
            expected = step.screen_id or current
            if expected not in screens:
                issues.append(f"step_{i}_unknown_screen:{expected}")
                continue
            if expected != current:
                issues.append(f"step_{i}_screen_out_of_route:{expected}")
            if step.element_id:
                used_on[expected].append(step.element_id)
            if step.op == "call_operation" or step.call is not None:
                issues += _call_issues(i, step, self.operation_id, expected)
                if step.call is not None:
                    current = step.call.end_screen
                continue
            transition = self.transition(step.transition_id)
            if step.op == "follow_transition" and transition is None:
                issues.append(f"step_{i}_transition_missing")
            if step.transition_id is None:
                continue
            if transition is None:
                issues.append(f"step_{i}_unknown_transition:{step.transition_id}")
                continue
            used_transitions.append(transition.transition_id)
            if transition.from_screen != expected:
                issues.append(f"step_{i}_transition_source_mismatch:{transition.transition_id}")
            is_control = isinstance(transition.trigger, ControlTrigger | ReturnTrigger)
            is_choice = isinstance(transition.trigger, ChoiceTrigger)
            if transition.window == "new":
                if window_open:
                    issues.append(f"step_{i}_nested_window")
                window_open = True
            elif isinstance(transition.trigger, ReturnTrigger):
                if not window_open:
                    issues.append(f"step_{i}_return_without_window")
                window_open = False
            wanted_op = (
                "follow_transition"
                if is_control
                else "ensure_choice"
                if is_choice
                else "invoke_approved_action"
            )
            if step.op != wanted_op:
                issues.append(f"step_{i}_transition_trigger_mismatch")
            if (
                not is_control
                and not is_choice
                and actions is not None
                and (action := actions.actions.get(step.action_id or "")) is not None
                and action.reconcile is None
                and action.effect == "mutating"
            ):
                issues.append(f"step_{i}_transition_action_unreconcilable")
            current = transition.to_screen
        if window_open:
            issues.append("new_window_without_return")
        for t in self.transitions:
            count = used_transitions.count(t.transition_id)
            if count != 1:
                issues.append(f"transition_used_{count}_times:{t.transition_id}")
        for screen_id, screen in screens.items():
            for issue in static_issues(
                screen,
                {e: self.elements[e].target for e in used_on[screen_id] if e in self.elements},
                used_on[screen_id],
            ):
                issues.append(f"{issue}@{screen_id}")
        return issues

    @property
    def is_ready_for_review(self) -> bool:
        return not self.validation_issues()


def _render(template: str, values: dict[str, str]) -> str:
    return templating.render(template, values)


def _direct_template(step: StepCard) -> str | None:
    """Çalışma anı değerinin tek başına kullanılabildiği şablon alanı."""
    return {
        "ensure_value": step.value_template,
        "ensure_date": step.value_template,
        "ensure_choice": step.choice_template,
        "find_record": step.key_template,
    }.get(step.op or "")


def _choice_issues(i: int, step: StepCard) -> list[str]:
    issues: list[str] = []
    if not step.choice_template:
        issues.append(f"step_{i}_choice_missing")
    if step.choice_value is not None and templating.placeholders(step.choice_template or ""):
        issues.append(f"step_{i}_choice_value_not_fixed")
    if (step.choice_effect == "unknown" or step.autocomplete) and step.success_check == "none":
        issues.append(f"step_{i}_choice_unverified")
    if step.autocomplete and step.transition_id is not None:
        issues.append(f"step_{i}_autocomplete_transition")
    return issues


def _param_of(template: str | None, draft: OperationDraft) -> ParameterDef | None:
    names = templating.placeholders(template or "")
    return next((p for p in draft.parameters if p.name in names), None)


def _choices_issues(i: int, step: StepCard, draft: OperationDraft) -> list[str]:
    issues: list[str] = []
    param = _param_of(step.choice_template, draft)
    if step.choice_set is None and (param is None or not param.multiple):
        issues.append(f"step_{i}_choice_set_missing")
    if step.choice_set is not None and step.choice_template:
        issues.append(f"step_{i}_choice_set_conflict")
    if step.choice_set and len({choice_key(c) for c in step.choice_set}) != len(step.choice_set):
        issues.append(f"step_{i}_duplicate_choice")
    if step.choice_effect is None:
        issues.append(f"step_{i}_effect_missing")
    if step.choice_effect == "unknown" and step.success_check == "none":
        issues.append(f"step_{i}_choice_unverified")
    return issues


def _date_issues(i: int, step: StepCard) -> list[str]:
    template = step.value_template or ""
    if step.date_format is None:
        return [f"step_{i}_date_format_missing"]
    if not template:
        return [f"step_{i}_date_missing"]
    if not templating.placeholders(template) and parse_date(template, step.date_format) is None:
        return [f"step_{i}_date_invalid"]
    return []


def _upload_issues(i: int, step: StepCard, draft: OperationDraft) -> list[str]:
    issues: list[str] = []
    param = _param_of(step.value_template, draft)
    if param is None or not param.file or step.value_template != f"{{{param.name}}}":
        issues.append(f"step_{i}_file_parameter_required")
    if not step.result_text:
        issues.append(f"step_{i}_file_result_required")
    if step.file_types and not set(step.file_types) <= ALLOWED_CONTENT_TYPES:
        issues.append(f"step_{i}_file_type_not_allowed")
    return issues


def _spec_target(spec: TargetSpec) -> dict[str, Any]:
    target = spec.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    target.setdefault("kind", spec.kind.value)
    return target


def _choices_commands(step: StepCard, spec: TargetSpec, values: dict[str, str]) -> list[dict[str, Any]]:
    target = _spec_target(spec)
    raw = _render(step.choice_template or "", values)
    members = step.choice_set or [line.strip() for line in raw.split("\n") if line.strip()]
    command = {
        "op": "ensure_choices",
        "target": target,
        "choices": members,
        "effect": step.choice_effect or "unknown",
    }
    out: list[dict[str, Any]] = [command]
    if step.success_check == "auto":
        out.append(
            {
                "op": "assert_condition",
                "condition": {"type": "choices_equal", "target": target, "choices": members},
            }
        )
    return out + _result_text_check(step, target)


def _checked_issues(i: int, step: StepCard) -> list[str]:
    issues: list[str] = []
    if step.checked is None:
        issues.append(f"step_{i}_checked_missing")
    if step.choice_effect is None:
        issues.append(f"step_{i}_effect_missing")
    if step.choice_effect == "unknown" and step.success_check == "none":
        issues.append(f"step_{i}_choice_unverified")
    return issues


def _checked_commands(step: StepCard, spec: TargetSpec) -> list[dict[str, Any]]:
    target = spec.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    target.setdefault("kind", spec.kind.value)
    command: dict[str, Any] = {
        "op": "ensure_checked",
        "target": target,
        "checked": step.checked,
        "effect": step.choice_effect or "unknown",
    }
    out = [command]
    if step.success_check == "auto":
        condition = {"type": "checked_equals", "target": target, "checked": step.checked}
        out.append({"op": "assert_condition", "condition": condition})
    out += _result_text_check(step, target)
    return out


def _result_text_check(step: StepCard, target: dict[str, Any]) -> list[dict[str, Any]]:
    if not step.result_text:
        return []
    return [
        {
            "op": "assert_condition",
            "condition": {
                "type": "text_present",
                "evidence": {"kind": "status_text"},
                "match": {"mode": "contains", "text": step.result_text},
                "anchor": target,
            },
        }
    ]


def _choice_commands(
    draft: OperationDraft,
    step: StepCard,
    spec: TargetSpec,
    values: dict[str, str],
    ref: dict[str, Any] | None,
    transition: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Seçim adımı → ensure_choice + sonuç koşulları. Yeni alanlar yalnız doluysa yazılır."""
    target = spec.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    target.setdefault("kind", spec.kind.value)
    template = step.choice_template or ""
    wanted: dict[str, Any]
    if ref is not None:
        wanted = {"choice_from": ref}
    else:
        wanted = {"choice": _render(template, values)}
        expected = step.choice_value
        names = templating.placeholders(template)
        if expected is None and len(names) == 1 and template == f"{{{next(iter(names))}}}":
            param = next((p for p in draft.parameters if p.name in names), None)
            item = param.choice_item(wanted["choice"]) if param is not None else None
            expected = item.value if item is not None else None
        if expected is not None:
            wanted["expected_value"] = expected
    command: dict[str, Any] = {"op": "ensure_choice", "target": target, **wanted}
    if step.choice_effect == "unknown" or step.autocomplete:
        command["effect"] = "unknown"  # öneri araması yazmak da ekranı değiştirir
    if step.autocomplete:
        command["autocomplete"] = True
        wanted_condition = {"autocomplete": True}
        if step.search_text:
            command["search_text"] = step.search_text
    else:
        wanted_condition = {}
    if transition is not None:
        # Alan eski ekranda kalır: sonuç hedef ekran ve kayıt bağlamıyla doğrulanır.
        return [{**command, "transition": transition}]
    out = [command]
    if step.success_check == "auto":
        out.append(
            {
                "op": "assert_condition",
                "condition": {"type": "choice_equals", "target": target, **wanted, **wanted_condition},
            }
        )
    out += _result_text_check(step, target)
    return out


def bind_arguments(
    draft: OperationDraft, args: dict[str, str], late: frozenset[str] = frozenset()
) -> dict[str, str]:
    """Argümanları parametre tanımlarına göre doğrular ve şablon değerlerini döndürür. late: bileşen
    girdisi olup değeri çalışma anında çağıranın okuma adımından gelen parametreler."""
    declared = {p.name: p for p in draft.parameters}
    values: dict[str, str] = {}
    for name in args:
        if name not in declared:
            raise ValueError(f"unexpected_argument:{name}")
    for name, param in declared.items():
        if name in late:
            continue
        if param.source is ParamSourceKind.APPROVED_CONSTANT:
            values[name] = param.constant or ""
            continue
        if param.source is ParamSourceKind.SECRET_REF:
            raise ValueError(f"secret_ref_not_supported:{name}")
        if param.source is ParamSourceKind.PRIOR_OUTPUT:
            if name in args:  # değer kullanıcıdan/modelden gelmez; yalnız çalışma anındaki okumadan gelir
                raise ValueError(f"unexpected_argument:{name}")
            continue
        if name not in args:
            if param.required:
                raise ValueError(f"missing_argument:{name}")
            continue
        if len(args[name]) > param.max_length:
            raise ValueError(f"argument_too_long:{name}")
        values[name] = args[name]
        if param.file:
            if not re.fullmatch(ARTIFACT_ID_PATTERN, args[name]):
                raise ValueError(f"invalid_file_reference:{name}")
            continue
        if param.multiple:
            members = param.members(args[name])
            if not members or len({choice_key(m) for m in members}) != len(members):
                raise ValueError(f"invalid_choice:{name}")
            if param.choices is not None:
                items = [param.choice_item(m) for m in members]
                if any(item is None for item in items):
                    raise ValueError(f"invalid_choice:{name}")
                members = [item.label for item in items if item is not None]
            values[name] = "\n".join(members)
            continue
        if param.choices is not None:
            item = param.choice_item(args[name])
            if item is None:
                raise ValueError(f"invalid_choice:{name}")
            values[name] = item.label
    return values


ComponentLookup = Callable[[str, int], "OperationDraft | None"]


def compile_operation(
    draft: OperationDraft,
    args: dict[str, str],
    actions: ActionSet,
    steps: list[StepCard] | None = None,
    screen_check: Literal["require", "if_present"] = "require",
    components: ComponentLookup | None = None,
) -> list[dict[str, Any]]:
    """Bkz. _compile. components: pinli bileşen revizyonlarını (operation_id, revision) verir."""
    commands, _ = _compile(draft, args, actions, steps, screen_check, components, (), {})
    return commands


def _compile(
    draft: OperationDraft,
    args: dict[str, str],
    actions: ActionSet,
    steps: list[StepCard] | None,
    screen_check: Literal["require", "if_present"],
    components: ComponentLookup | None,
    stack: tuple[tuple[str, int], ...],
    late: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[int, str | None], int]]:
    """Taslağı P3 komut planına derler. Argümanlar tip/uzunluk/kaynak kurallarına göre doğrulanır.

    Plan ekran doğrulamasıyla (assert_screen) başlar; yürütücü sonraki her sayfa adımından önce ekranı
    yeniden doğrular. Ekran tanımı yoksa 'require' modunda derleme reddedilir (kontrol sessizce atlanmaz).
    'if_present' yalnız tasarımcıdaki tek adım denemesi içindir (ekran henüz tanımlanmamış olabilir)."""
    values = bind_arguments(draft, args, frozenset(late))
    commands: list[dict[str, Any]] = []
    sequence = steps if steps is not None else draft.steps
    screens = draft.all_screens()
    if draft.screen is not None:
        first = (draft.step_screen_id(sequence[0]) if sequence else None) or draft.screen.screen_id
        if first not in screens:
            raise ValueError(f"unknown_screen:{first}")
        start: dict[str, Any] = {"op": "assert_screen", "screen": screens[first].model_dump(mode="json")}
        if first == draft.screen.screen_id and draft.start_context:
            start["context"] = [c.rendered(values) for c in draft.start_context]
        commands.append(start)
        if draft.optional_dialogs:
            commands.append(
                {
                    "op": "register_optional_dialogs",
                    "dialogs": [d.model_dump(mode="json") for d in draft.optional_dialogs],
                }
            )
    elif screen_check == "require":
        raise ValueError("migration_required")

    def transition_spec(step: StepCard) -> dict[str, Any]:
        t = draft.transition(step.transition_id)
        if t is None or t.to_screen not in screens:
            raise ValueError(f"unknown_transition:{step.transition_id}")
        spec: dict[str, Any] = {
            "transition_id": t.transition_id,
            "to_screen": screens[t.to_screen].model_dump(mode="json"),
            "timeout_ms": t.timeout_ms,
        }
        if t.completion:
            spec["context"] = [c.rendered(values) for c in t.completion]
        if t.window:
            spec["window"] = t.window
        if t.window_origin:
            spec["window_origin"] = t.window_origin
        return spec

    prior = {p.name: p for p in draft.parameters if p.source is ParamSourceKind.PRIOR_OUTPUT}
    order = {s.step_id: i for i, s in enumerate(draft.steps)}
    # (taslak adım sırası, bileşen çıktısı) → plandaki okuma komutunun sırası
    read_at: dict[tuple[int, str | None], int] = {}

    def ref_for(name: str) -> dict[str, Any]:
        """Değeri çalışma anında okunan parametrenin plan içi başvurusu (bu planın adım numaralarıyla)."""
        if name in late:
            limit = next(p.max_length for p in draft.parameters if p.name == name)
            return {"step": late[name]["step"], "max_length": min(late[name]["max_length"], limit)}
        param = prior[name]
        key = (param.prior_step if param.prior_step is not None else -1, param.prior_output)
        if key not in read_at:
            raise ValueError(f"prior_output_unavailable:{name}")
        return {"step": read_at[key], "max_length": min(param.max_length, 500)}

    runtime = set(prior) | set(late)

    def exact_runtime(template: str) -> str | None:
        """Şablon tek başına çalışma anı parametresiyse adı; karışık kullanım reddedilir."""
        names = templating.placeholders(template) & runtime
        if not names:
            return None
        name = next(iter(names))
        if len(names) > 1 or template != f"{{{name}}}":
            raise ValueError(f"prior_output_misuse:{name}")
        return name

    def output_ref(step: StepCard) -> dict[str, Any] | None:
        if step.op in {"invoke_approved_action", "call_operation"}:
            return None  # parametre başına ayrı bağlanır
        used = {n for t in step.templates() for n in templating.placeholders(t)} & runtime
        if not used:
            return None
        name = next(iter(used))
        if len(used) > 1 or _direct_template(step) != f"{{{name}}}":
            raise ValueError(f"prior_output_misuse:{name}")
        return ref_for(name)

    def inline_call(step: StepCard) -> None:
        call = step.call
        if call is None:
            raise ValueError(f"call_missing:{step.step_id}")
        key = (call.operation_id, call.revision)
        if call.operation_id == draft.operation_id or key in stack:
            raise ValueError(f"component_cycle:{call.operation_id}")
        if len(stack) + 1 > MAX_COMPONENT_DEPTH:
            raise ValueError(f"component_too_deep:{call.operation_id}")
        component = components(*key) if components is not None else None
        if component is None:
            raise ValueError(f"component_missing:{call.operation_id}@{call.revision}")
        if component.content_hash() != call.content_hash:
            raise ValueError(f"component_hash_mismatch:{call.operation_id}@{call.revision}")
        if component_inputs(component) != call.inputs or component_outputs(component) != call.outputs:
            raise ValueError(f"component_contract_mismatch:{call.operation_id}@{call.revision}")
        missing = [n for n in call.inputs if n not in call.arguments]
        if missing:
            raise ValueError(f"component_input_missing:{missing[0]}")
        base = len(commands)
        sub_args: dict[str, str] = {}
        sub_late: dict[str, dict[str, Any]] = {}
        for arg, template in call.arguments.items():
            name = exact_runtime(template)
            if name is None:
                sub_args[arg] = _render(template, values)
            else:
                ref = ref_for(name)
                # Alt plan birleştirilirken base kadar kaydırılır; negatif değer üst plana işaret eder.
                sub_late[arg] = {"step": ref["step"] - base, "max_length": ref["max_length"]}
        sub, sub_reads = _compile(
            component, sub_args, actions, None, "require", components, (*stack, key), sub_late
        )
        commands.extend(rebase_output_refs(c, base) for c in sub)
        index = order.get(step.step_id, -1)
        for (sub_step, _), at in sub_reads.items():
            element = component.steps[sub_step].element_id
            if element is not None:
                read_at[(index, element)] = base + at

    def emit(step: StepCard) -> None:
        if step.op is None:
            raise ValueError(f"step_without_command:{step.step_id}")
        if step.op == "call_operation":
            inline_call(step)
            return
        ref = output_ref(step)
        if step.op in {"ensure_choices", "ensure_date", "upload_file"}:
            element = draft.elements.get(step.element_id or "")
            if element is None:
                raise ValueError(f"unknown_element:{step.element_id}")
            target = _spec_target(element.target)
            if step.op == "ensure_choices":
                commands.extend(_choices_commands(step, element.target, values))
            elif step.op == "ensure_date":
                source = (
                    {"value_from": ref}
                    if ref is not None
                    else {"value": _render(step.value_template or "", values)}
                )
                commands.append(
                    {"op": "ensure_date", "target": target, "date_format": step.date_format, **source}
                )
            else:
                upload: dict[str, Any] = {
                    "op": "upload_file",
                    "target": target,
                    "artifact_id": _render(step.value_template or "", values),
                    "effect": "unknown",
                }
                if step.file_types:
                    upload["allowed_types"] = step.file_types
                commands.append(upload)
                commands.extend(_result_text_check(step, target))
            return
        if step.op == "ensure_checked":
            element = draft.elements.get(step.element_id or "")
            if element is None or step.checked is None:
                raise ValueError(f"unknown_element:{step.element_id}")
            commands.extend(_checked_commands(step, element.target))
            return
        if step.op == "ensure_choice":
            element = draft.elements.get(step.element_id or "")
            if element is None:
                raise ValueError(f"unknown_element:{step.element_id}")
            transition = transition_spec(step) if step.transition_id is not None else None
            commands.extend(_choice_commands(draft, step, element.target, values, ref, transition))
            return
        if ref is not None and step.op != "find_record":
            element = draft.elements.get(step.element_id or "")
            if element is None:
                raise ValueError(f"unknown_element:{step.element_id}")
            target = element.target.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            target.setdefault("kind", element.target.kind.value)
            commands.append({"op": "ensure_value", "target": target, "value_from": ref})
            if step.success_check == "auto":
                commands.append(
                    {
                        "op": "assert_condition",
                        "condition": {"type": "value_equals", "target": target, "value_from": ref},
                    }
                )
            return
        if step.op == "read" and step.step_id in order:
            read_at[(order[step.step_id], None)] = len(commands)
        if step.op == "follow_transition":
            t = draft.transition(step.transition_id)
            if t is not None and isinstance(t.trigger, ReturnTrigger):
                commands.append({"op": "return_window", "close": t.trigger.close, **transition_spec(step)})
                return
            if t is None or not isinstance(t.trigger, ControlTrigger):
                raise ValueError(f"unknown_transition:{step.transition_id}")
            trigger = t.trigger.target.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            trigger.setdefault("kind", t.trigger.target.kind.value)
            commands.append({"op": "follow_transition", "trigger": trigger, **transition_spec(step)})
            return
        if step.op == "invoke_approved_action":
            problem = actions.problem(step.action_id, step.action_hash, draft.application_id)
            if problem is not None:
                raise ValueError(f"{problem}:{step.action_id}")
            fixed: dict[str, str] = {}
            from_output: dict[str, dict[str, Any]] = {}
            for param_name, template in step.action_params.items():
                runtime_name = exact_runtime(template)
                if runtime_name is None:
                    fixed[param_name] = _render(template, values)
                else:
                    from_output[param_name] = ref_for(runtime_name)
            command: dict[str, Any] = {"op": step.op, "action_id": step.action_id, "params": fixed}
            if from_output:
                command["params_from"] = from_output
            if step.action_hash is not None:
                command["action_hash"] = step.action_hash
                command["application_id"] = draft.application_id
            if step.transition_id is not None:
                command["transition"] = transition_spec(step)
            commands.append(command)
            return
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
        elif step.op == "activate_tab":
            commands.append({"op": "activate_tab", "target": target})
            if step.success_check == "auto":
                commands.append(
                    {"op": "assert_condition", "condition": {"type": "tab_active", "target": target}}
                )
        elif step.op == "find_record":
            record: dict[str, Any] = {"op": "find_record", "table": target, "navigation": step.navigation}
            if ref is not None:
                record["key_from"] = ref
            else:
                record["key"] = _render(step.key_template or "", values)
            if step.next_labels:
                record["next_labels"] = step.next_labels
            if step.end_text:
                record["end_text"] = step.end_text
            commands.append(record)
        else:
            commands.append({"op": "read", "target": target})

    for step in sequence:
        begin = len(commands)
        emit(step)
        if step.in_found_row:
            for index in range(begin, len(commands)):
                commands[index] = {**commands[index], "in_found_row": True}
    return commands, read_at
