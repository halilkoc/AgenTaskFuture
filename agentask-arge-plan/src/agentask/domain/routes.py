"""R4: çok ekranlı işlemlerde onaylı ekran geçişleri ve kayıt bağlamı koşulları (catalog-v3).

Geçiş tanımı önceden yazılmış ve insan onaylı katalog verisidir: kaynak ekran, izinli tetikleyici, beklenen
hedef
ekran ve tamamlanma koşulu. Çalışma anında model veya kod yeni rota/ekran/geçiş seçmez.

- Tetikleyici ile iş etkisi ayrıdır: `control` tetikleyici yalnız ekran değiştiren onaylı bir
düğme/sekmedir (iş
  etkisi yok); `approved_action` tetikleyicide adımın onaylı aksiyonu iş etkisini taşır, geçiş ise ayrıca
  doğrulanır. Hedef ekranın görünmesi iş sonucunun kanıtı sayılmaz.
- Tamamlanma: hedef ekran (ortak ekran çekirdeğiyle) tanınmalı ve bağlam koşulları (ör. Vaka No = {vaka_no})
  sağlanmalıdır. Aynı ekran türündeki başka kayıt kabul edilmez.
- Kalıcı locator yoktur: hedefler TargetSpec'tir.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentask.domain import templating
from agentask.domain.observation import ControlKind
from agentask.domain.targeting import TargetSpec

_SLUG = r"^[a-z][a-z0-9_]{0,60}$"
TRANSITION_TIMEOUT_MIN_MS = 500
TRANSITION_TIMEOUT_MAX_MS = 60_000


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextCheck(_Model):
    """Kayıt bağlamı: alanın değeri (şablon) beklenene eşit olmalı. Ör. salt okunur 'Vaka No' = {vaka_no}."""

    target: TargetSpec
    value_template: str = Field(min_length=1, max_length=200)

    @field_validator("value_template")
    @classmethod
    def _safe(cls, value: str) -> str:
        if not templating.is_valid(value):
            raise ValueError("değer şablonu yalnız {parametre} yer tutucuları içerebilir")
        return value

    @model_validator(mode="after")
    def _readable(self) -> Self:
        if self.target.kind not in {ControlKind.TEXTBOX, ControlKind.SELECT, ControlKind.COMBOBOX}:
            raise ValueError("bağlam koşulu metin alanı veya liste değerine dayanmalı")
        return self

    def rendered(self, values: dict[str, str]) -> dict[str, object]:
        target = self.target.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
        target.setdefault("kind", self.target.kind.value)
        return {
            "type": "value_equals",
            "target": target,
            "value": templating.render(self.value_template, values),
        }


class ControlTrigger(_Model):
    """Yalnız ekran değiştiren onaylı kontrol (iş etkisi yok). Genel 'herhangi bir şeye tıkla' değildir."""

    kind: Literal["control"]
    target: TargetSpec

    @model_validator(mode="after")
    def _kind(self) -> Self:
        if self.target.kind not in {ControlKind.BUTTON, ControlKind.TAB, ControlKind.LINK}:
            raise ValueError("geçiş tetikleyicisi düğme, sekme veya bağlantı olmalı")
        return self


class ActionTrigger(_Model):
    """Adımın onaylı aksiyonu (ör. kaydet) hem iş etkisi yaratır hem ekranı değiştirir."""

    kind: Literal["approved_action"]


class ChoiceTrigger(_Model):
    """Adımın seçimi ekranı değiştirir. Seçim bir kez yapılır; sonuç hedef ekranla doğrulanır."""

    kind: Literal["choice"]


class ReturnTrigger(_Model):
    """Beklenen yeni pencereden ana pencereye dönüş; kaynak ekran yeniden doğrulanır."""

    kind: Literal["window_return"]
    close: bool = True  # False: pencereyi uygulama kendisi kapatır


Trigger = Annotated[
    ControlTrigger | ActionTrigger | ChoiceTrigger | ReturnTrigger, Field(discriminator="kind")
]


class TransitionDef(_Model):
    transition_id: str = Field(pattern=_SLUG)
    from_screen: str = Field(pattern=_SLUG)
    to_screen: str = Field(pattern=_SLUG)
    trigger: Trigger
    timeout_ms: int = Field(default=10_000, ge=TRANSITION_TIMEOUT_MIN_MS, le=TRANSITION_TIMEOUT_MAX_MS)
    completion: list[ContextCheck] = Field(default_factory=list, max_length=5)
    window: Literal["new"] | None = None  # tetikleyici tek, tanımlı bir yeni pencere açar
    window_origin: str | None = Field(default=None, pattern=r"^https?://[^/\s]+$", max_length=200)

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if self.from_screen == self.to_screen:
            raise ValueError("geçişin kaynak ve hedef ekranı farklı olmalı")
        if self.window and not isinstance(self.trigger, ControlTrigger):
            raise ValueError("yeni pencereyi yalnız düğme veya bağlantı açabilir")
        if self.window_origin and not self.window:
            raise ValueError("pencere adresi yalnız yeni pencere geçişinde verilir")
        return self

    def definition(self) -> dict[str, object]:
        """Kanonik içerik: pencere alanları yalnız doluysa yazılır (eski revizyon hash'leri değişmez)."""
        unset = {k for k in ("window", "window_origin") if getattr(self, k) is None}
        return self.model_dump(mode="json", exclude=unset)

    def placeholders(self) -> set[str]:
        return set().union(*(templating.placeholders(c.value_template) for c in self.completion))
