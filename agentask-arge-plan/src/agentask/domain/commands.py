"""Sınırlı komut dili: read, ensure_value, ensure_choice, activate_tab, find_record, invoke_approved_action,
assert_condition, assert_screen (R3: ekran ve bölge doğrulaması; etkisizdir, yalnız gözlem okur).
Her komut tipli ve extra=forbid; selector, kod, URL veya serbest tıklama komutu yoktur."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentask.domain.actions import ActionSet, EvidenceSpec, KnownBlocker, TextMatch
from agentask.domain.artifacts import ARTIFACT_ID_PATTERN
from agentask.domain.choices import choice_key
from agentask.domain.dates import DateFormat
from agentask.domain.observation import ControlKind
from agentask.domain.screens import ScreenDef
from agentask.domain.targeting import TargetSpec


class _Cmd(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_kind(spec: TargetSpec, *kinds: ControlKind) -> None:
    if spec.kind not in kinds:
        raise ValueError(f"hedef türü {', '.join(k.value for k in kinds)} olmalı")


class OutputRef(_Cmd):
    """Önceki bir okuma komutunun çıktısına başvuru (plan içi sıra numarası). Değer derleme anında bilinmez;
    yürütücü, kaynak okuma adımı BAŞARIYLA bitmişse onun gerçek çıktısını yerleştirir. Okuma yoksa,
    başarısızsa, boşsa, hassas alandan geldiyse veya sınırı aşıyorsa adım sürücü eylemi yapmadan durur."""

    step: int = Field(ge=0)
    max_length: int = Field(ge=1, le=500)


class ReadCommand(_Cmd):
    op: Literal["read"]
    target: TargetSpec
    in_found_row: bool = False  # hedef, önceki Kayıt bul adımının bulduğu satırda aranır


def _value_or_ref(value: str, ref: OutputRef | None) -> None:
    if ref is not None and value:
        raise ValueError("value_from kullanılırken sabit değer verilmez")


def _choice_or_ref(choice: str, ref: OutputRef | None) -> None:
    if ref is not None and choice:
        raise ValueError("choice_from kullanılırken sabit seçenek verilmez")
    if ref is None and not choice:
        raise ValueError("seçenek boş olamaz")


class EnsureValueCommand(_Cmd):
    op: Literal["ensure_value"]
    target: TargetSpec
    in_found_row: bool = False
    value: str = Field(default="", max_length=500)
    value_from: OutputRef | None = None

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.TEXTBOX)
        _value_or_ref(self.value, self.value_from)
        return self


class EnsureChoiceCommand(_Cmd):
    """Listeden seçim. choice görünen etikettir; expected_value varsa uygulamanın alttaki değeri de aynı
    seçeneği göstermelidir. effect='unknown': seçim kayıt/ekran değişikliği tetikleyebilir; gönderilince
    otomatik tekrarlanmaz, belirsiz sonuç yalnız okumayla uzlaştırılır."""

    op: Literal["ensure_choice"]
    target: TargetSpec
    in_found_row: bool = False
    choice: str = Field(default="", max_length=200)
    choice_from: OutputRef | None = None
    expected_value: str | None = Field(default=None, min_length=1, max_length=200)
    effect: Literal["ui_local", "unknown"] = "ui_local"
    transition: TransitionSpec | None = None  # seçim ekranı değiştirir (bir kez; hedef ekranla doğrulanır)
    autocomplete: bool = False  # yazınca öneri açan alan: arama ekranda değişiklik yapar, hiç tekrarlanmaz
    search_text: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        if self.autocomplete and self.transition is not None:
            raise ValueError("autocomplete_transition_unsupported")
        kinds = (ControlKind.SELECT, ControlKind.COMBOBOX, ControlKind.RADIO_GROUP)
        _require_kind(self.target, *(kinds + ((ControlKind.TEXTBOX,) if self.autocomplete else ())))
        _choice_or_ref(self.choice, self.choice_from)
        return self


class EnsureCheckedCommand(_Cmd):
    """Onay kutusu istenen durumda olsun. Etkisi bilinmiyorsa tek gönderim; sonuç okunarak doğrulanır."""

    op: Literal["ensure_checked"]
    target: TargetSpec
    checked: bool
    effect: Literal["ui_local", "unknown"] = "unknown"
    in_found_row: bool = False

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.CHECKBOX)
        return self


class EnsureChoicesCommand(_Cmd):
    """Çoklu seçim: alan tam olarak bu kümeyi taşısın. Üyelerin tümü değişiklikten önce doğrulanır; kısmi veya
    belirsiz sonuç başarı değildir ve otomatik yeniden uygulanmaz."""

    op: Literal["ensure_choices"]
    target: TargetSpec
    choices: list[str] = Field(min_length=1, max_length=50)
    effect: Literal["ui_local", "unknown"] = "unknown"
    in_found_row: bool = False

    @model_validator(mode="after")
    def _rules(self) -> Self:
        _require_kind(self.target, ControlKind.SELECT, ControlKind.COMBOBOX)
        if len({choice_key(c) for c in self.choices}) != len(self.choices):
            raise ValueError("duplicate_choice")
        return self


class EnsureDateCommand(_Cmd):
    """Metin/maskeli/type=date alanı. Takvim açılır penceresi desteklenmez (kurum DOM'u gerekir)."""

    op: Literal["ensure_date"]
    target: TargetSpec
    in_found_row: bool = False
    value: str = Field(default="", max_length=40)
    value_from: OutputRef | None = None
    date_format: DateFormat

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.TEXTBOX)
        _value_or_ref(self.value, self.value_from)
        return self


class UploadFileCommand(_Cmd):
    """Kaynak yalnız yetkili depodur (artifact_id); serbest dosya yolu yok. Belirsiz sonuçta tekrar yok."""

    op: Literal["upload_file"]
    target: TargetSpec
    artifact_id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    allowed_types: list[str] | None = Field(default=None, min_length=1, max_length=4)
    effect: Literal["unknown"] = "unknown"
    in_found_row: bool = False

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.target, ControlKind.FILE)
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
    key: str = Field(default="", max_length=200)
    key_from: OutputRef | None = None
    navigation: Literal["none", "paged", "scroll"] = "none"
    next_labels: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=lambda: ["Sonraki"], max_length=5
    )
    end_text: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.table, ControlKind.TABLE)
        _choice_or_ref(self.key, self.key_from)
        return self


class ValueEquals(_Cmd):
    type: Literal["value_equals"]
    target: TargetSpec
    value: str = Field(default="", max_length=500)
    value_from: OutputRef | None = None  # yalnız assert_condition içinde (bağlam koşullarında değil)

    @model_validator(mode="after")
    def _ref(self) -> Self:
        _value_or_ref(self.value, self.value_from)
        return self


class TransitionSpec(_Cmd):
    """R4: onaylı geçişin hedefi. Tetikleyici bir kez gönderilir; hedef ekran timeout_ms içinde tanınmalı ve
    bağlam koşulları sağlanmalıdır. Hedefin görünmesi iş sonucunun kanıtı değildir."""

    transition_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,60}$")
    to_screen: ScreenDef
    timeout_ms: int = Field(ge=500, le=60_000)
    context: list[ValueEquals] = Field(default_factory=list, max_length=5)
    window: Literal["same", "new"] = "same"
    window_origin: str | None = Field(default=None, max_length=200)


EnsureChoiceCommand.model_rebuild()


class ReturnWindowCommand(TransitionSpec):
    """Beklenen pencereden ana pencereye dönüş. Kaynak ekran tanınmadan sonraki adım başlamaz."""

    op: Literal["return_window"]
    close: bool = True


class RegisterOptionalDialogsCommand(_Cmd):
    """İsteğe bağlı pencereler: çıkarsa ad+metin eşleşmesiyle tanımlı düğmeye basılır, çıkmazsa beklenmez."""

    op: Literal["register_optional_dialogs"]
    dialogs: list[KnownBlocker] = Field(min_length=1, max_length=10)


class InvokeApprovedActionCommand(_Cmd):
    op: Literal["invoke_approved_action"]
    action_id: str = Field(pattern=r"^[a-z0-9_.]{3,80}$")
    params: dict[str, str] = Field(default_factory=dict)
    params_from: dict[str, OutputRef] = Field(default_factory=dict)  # çalışma anında okunan değerler
    transition: TransitionSpec | None = None  # aksiyon hem iş etkisi yaratır hem ekranı değiştirir
    action_hash: str | None = Field(default=None, min_length=16, max_length=128)  # onaylanan davranış özeti
    application_id: str | None = Field(default=None, max_length=61)


class FollowTransitionCommand(TransitionSpec):
    """Yalnız ekran değiştiren onaylı kontrol (düğme/sekme). İş etkisi yoktur; yine de bir kez tetiklenir."""

    op: Literal["follow_transition"]
    trigger: TargetSpec
    in_found_row: bool = False

    @model_validator(mode="after")
    def _kind(self) -> Self:
        _require_kind(self.trigger, ControlKind.BUTTON, ControlKind.TAB, ControlKind.LINK)
        return self


class ChoiceEquals(_Cmd):
    type: Literal["choice_equals"]
    target: TargetSpec
    choice: str = Field(default="", max_length=200)
    choice_from: OutputRef | None = None  # yalnız assert_condition içinde
    expected_value: str | None = Field(default=None, min_length=1, max_length=200)
    autocomplete: bool = False

    @model_validator(mode="after")
    def _ref(self) -> Self:
        _choice_or_ref(self.choice, self.choice_from)
        return self


class ChoicesEqual(_Cmd):
    type: Literal["choices_equal"]
    target: TargetSpec
    choices: list[str] = Field(min_length=1, max_length=50)


class CheckedEquals(_Cmd):
    type: Literal["checked_equals"]
    target: TargetSpec
    checked: bool


class TabActive(_Cmd):
    type: Literal["tab_active"]
    target: TargetSpec


class TextPresent(_Cmd):
    type: Literal["text_present"]
    evidence: EvidenceSpec
    match: TextMatch
    anchor: TargetSpec | None = None  # kanıt bu kontrolün form/bölge/frame'inde okunur


Condition = Annotated[
    ValueEquals | ChoiceEquals | ChoicesEqual | CheckedEquals | TabActive | TextPresent,
    Field(discriminator="type"),
]


class AssertConditionCommand(_Cmd):
    op: Literal["assert_condition"]
    condition: Condition
    in_found_row: bool = False


class AssertScreenCommand(_Cmd):
    """Ekran tanınmadan (tekil işaretler + yasak işaret yokluğu + bölge kanıtı) hiçbir sayfa eylemi
    yapılmaz. Yürütücü bu ekranı sonraki her sayfa adımından önce güncel gözlemle yeniden doğrular."""

    op: Literal["assert_screen"]
    screen: ScreenDef
    # R4: kayıt bağlamı (ör. Vaka No = istenen vaka); aynı ekran türündeki başka kayıt kabul edilmez.
    context: list[ValueEquals] = Field(default_factory=list, max_length=5)


class EvaluateConditionCommand(_Cmd):
    """Birleştirme fazı: koşulu değerlendirir ve sonucu kaydeder; asla başarısız olmaz (guard için)."""

    op: Literal["evaluate_condition"]
    condition: Condition


Command = Annotated[
    ReadCommand
    | EnsureValueCommand
    | EnsureChoiceCommand
    | ReturnWindowCommand
    | RegisterOptionalDialogsCommand
    | EnsureCheckedCommand
    | EnsureChoicesCommand
    | EnsureDateCommand
    | UploadFileCommand
    | ActivateTabCommand
    | FindRecordCommand
    | InvokeApprovedActionCommand
    | FollowTransitionCommand
    | AssertConditionCommand
    | AssertScreenCommand
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
        for ref in output_refs(step):
            if ref.step >= index or not isinstance(steps[ref.step], ReadCommand):
                raise PlanRejected("invalid_output_ref", index)
        contexts = [*getattr(step, "context", [])]
        if (
            isinstance(step, InvokeApprovedActionCommand | EnsureChoiceCommand)
            and step.transition is not None
        ):
            contexts += step.transition.context
        if any(c.value_from is not None for c in contexts):
            raise PlanRejected("output_ref_not_allowed", index)
        if isinstance(step, InvokeApprovedActionCommand):
            action = actions.actions.get(step.action_id)
            if action is None:
                raise PlanRejected("unknown_action", index)
            if step.action_hash is not None and step.action_hash != actions.fingerprint(step.action_id):
                raise PlanRejected("action_changed", index)
            declared = {p.name: p for p in action.params}
            if set(step.params) | set(step.params_from) != set(declared) or set(step.params) & set(
                step.params_from
            ):
                raise PlanRejected("params_mismatch", index)
            for name, value in step.params.items():
                if len(value) > declared[name].max_length or not value.strip():
                    raise PlanRejected("param_too_long" if value.strip() else "param_empty", index)


def output_refs(command: Command) -> list[OutputRef]:
    """Komutun başvurduğu önceki okuma çıktıları (ensure_value/ensure_choice ve bunların doğrulamaları)."""
    if isinstance(command, EnsureValueCommand | EnsureDateCommand) and command.value_from is not None:
        return [command.value_from]
    if isinstance(command, EnsureChoiceCommand) and command.choice_from is not None:
        return [command.choice_from]
    if isinstance(command, InvokeApprovedActionCommand):
        return list(command.params_from.values())
    if isinstance(command, FindRecordCommand) and command.key_from is not None:
        return [command.key_from]
    if isinstance(command, AssertConditionCommand):
        condition = command.condition
        if isinstance(condition, ValueEquals) and condition.value_from is not None:
            return [condition.value_from]
        if isinstance(condition, ChoiceEquals) and condition.choice_from is not None:
            return [condition.choice_from]
    return []


def rebase_output_refs(raw: dict[str, Any], offset: int) -> dict[str, Any]:
    """Birleştirmede düzleştirilen alt plandaki çıktı başvurularını üst plan sırasına kaydırır."""
    if offset == 0:
        return raw
    out = dict(raw)
    if isinstance(out.get("params_from"), dict):
        out["params_from"] = {k: {**v, "step": v["step"] + offset} for k, v in out["params_from"].items()}
    for key in ("value_from", "choice_from", "key_from"):
        if isinstance(out.get(key), dict):
            out[key] = {**out[key], "step": out[key]["step"] + offset}
        condition = out.get("condition")
        if isinstance(condition, dict) and isinstance(condition.get(key), dict):
            ref = condition[key]
            out["condition"] = {**condition, key: {**ref, "step": ref["step"] + offset}}
    return out


def bind_params(raw: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    """Onaylı aksiyonun çıktıdan gelen parametrelerini gerçek değerlerle yerleştirir."""
    out = dict(raw)
    out.pop("params_from", None)
    out["params"] = {**out.get("params", {}), **values}
    return out


def bind_output(raw: dict[str, Any], value: str) -> dict[str, Any]:
    """Çıktı başvurusunu gerçek değerle değiştirir (başvuru kaldırılır)."""
    out = dict(raw)
    for key, target in (("value_from", "value"), ("choice_from", "choice"), ("key_from", "key")):
        if key in out:
            out.pop(key)
            out[target] = value
        elif isinstance(out.get("condition"), dict) and key in out["condition"]:
            condition = dict(out["condition"])
            condition.pop(key)
            condition[target] = value
            out["condition"] = condition
    return out
