"""Ortak kontrol adapterleri. Süreçten bağımsızdır; yalnız P2 adayı (ObservedControl) ve ControlDriver
kullanır.

Her adapter: desteklediği kontrolü açıkça belirler (supports), işlem öncesi mevcut durumu okur, durum zaten
isteneni sağlıyorsa hiçbir şey yapmaz, işlem sonrası durumu yeniden okuyup doğrular. Desteklenmeyen kontrol ve
işlem ControlUnsupported döner. Seçenek eşleşmesi normalize edilmiş tam eşitliktir; birden fazla eşleşme
reddedilir.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from agentask.application.ports.controls import ControlDriver
from agentask.domain.actions import ErrorClass
from agentask.domain.observation import ControlKind, ObservedControl
from agentask.domain.targeting import normalize_name


class AdapterError(Exception):
    error_class: ErrorClass = ErrorClass.VERIFICATION_FAILED
    retry_safe = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ControlUnsupported(AdapterError):
    error_class = ErrorClass.CONTROL_UNSUPPORTED


class VerificationFailed(AdapterError):
    error_class = ErrorClass.VERIFICATION_FAILED
    retry_safe = True


class ChoiceNotAvailable(AdapterError):
    error_class = ErrorClass.BUSINESS_VALIDATION


class TargetNotReady(AdapterError):
    error_class = ErrorClass.TARGET_NOT_READY
    retry_safe = True


class StaleTarget(AdapterError):
    error_class = ErrorClass.FRAME_CHANGED
    retry_safe = True


@dataclass(frozen=True, slots=True)
class EnsureResult:
    changed: bool
    verified: bool
    observed: str | None


class RecordOutcome(StrEnum):
    FOUND = "found"
    NOT_FOUND_AT_END = "not_found_at_end"
    LIMIT_REACHED = "limit_reached"
    NO_PROGRESS = "no_progress"
    DUPLICATE_KEY = "duplicate_key"


@dataclass(frozen=True, slots=True)
class RecordSearch:
    outcome: RecordOutcome
    pages_visited: int
    rows_seen: int


@dataclass(frozen=True, slots=True)
class TableLimits:
    max_pages: int
    max_rows: int
    no_progress_limit: int


Relocate = Callable[[ObservedControl], Awaitable[ObservedControl]]


def _match_option(options: list[str] | tuple[str, ...], choice: str) -> str:
    wanted = normalize_name(choice)
    found = [o for o in options if normalize_name(o) == wanted]
    if len(found) != 1:
        raise ChoiceNotAvailable(
            "Seçenek bulunamadı." if not found else "Seçenek birden fazla kez geçiyor; seçim yapılmadı."
        )
    return found[0]


class ControlAdapter:
    name = "base"

    def supports(self, control: ObservedControl) -> bool:
        raise NotImplementedError

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        return None

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        raise ControlUnsupported(f"{self.name} okuma desteklemiyor")

    async def ensure_value(self, driver: ControlDriver, control: ObservedControl, value: str) -> EnsureResult:
        raise ControlUnsupported(f"{self.name} değer yazmayı desteklemiyor")

    async def ensure_choice(
        self, driver: ControlDriver, control: ObservedControl, choice: str
    ) -> EnsureResult:
        raise ControlUnsupported(f"{self.name} seçim desteklemiyor")

    async def activate_tab(self, driver: ControlDriver, control: ObservedControl) -> EnsureResult:
        raise ControlUnsupported(f"{self.name} sekme etkinleştirmeyi desteklemiyor")

    async def find_record(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        key: str,
        navigation: str,
        next_labels: list[str],
        end_text: str | None,
        limits: TableLimits,
        relocate: Relocate,
    ) -> RecordSearch:
        raise ControlUnsupported(f"{self.name} kayıt aramayı desteklemiyor")


class TextboxAdapter(ControlAdapter):
    name = "textbox"

    def supports(self, control: ObservedControl) -> bool:
        return (
            control.kind is ControlKind.TEXTBOX
            and control.tag in {"input", "textarea"}
            and not control.sensitive
        )

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        if control.kind is ControlKind.TEXTBOX and control.sensitive:
            return "sensitive_target_requires_secret_ref"
        return None

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).value

    async def ensure_value(self, driver: ControlDriver, control: ObservedControl, value: str) -> EnsureResult:
        before = await driver.state(control.candidate_id)
        if before.value == value:
            return EnsureResult(changed=False, verified=True, observed=before.value)
        if not before.enabled:
            raise TargetNotReady("Alan etkin değil.")
        await driver.fill(control.candidate_id, value)
        after = await driver.state(control.candidate_id)
        if after.value != value:
            raise VerificationFailed("Yazılan değer alanda doğrulanamadı.")
        return EnsureResult(changed=True, verified=True, observed=after.value)


class NativeSelectAdapter(ControlAdapter):
    name = "native_select"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.SELECT and control.tag == "select" and not control.sensitive

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        return (
            "sensitive_target_requires_secret_ref"
            if control.kind is ControlKind.SELECT and control.sensitive
            else None
        )

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).selected_text

    async def ensure_choice(
        self, driver: ControlDriver, control: ObservedControl, choice: str
    ) -> EnsureResult:
        before = await driver.state(control.candidate_id)
        label = _match_option(control.options, choice)
        if before.selected_text is not None and normalize_name(before.selected_text) == normalize_name(label):
            return EnsureResult(changed=False, verified=True, observed=before.selected_text)
        await driver.select_option(control.candidate_id, label)
        after = await driver.state(control.candidate_id)
        if after.selected_text is None or normalize_name(after.selected_text) != normalize_name(label):
            raise VerificationFailed("Seçim doğrulanamadı.")
        return EnsureResult(changed=True, verified=True, observed=after.selected_text)


class CustomComboboxAdapter(ControlAdapter):
    """role=combobox + listbox açılır liste (input tabanlı/yazarak arama yapan combobox desteklenmez)."""

    name = "custom_combobox"

    def supports(self, control: ObservedControl) -> bool:
        return (
            control.kind is ControlKind.COMBOBOX
            and control.tag not in {"input", "textarea", ""}
            and not control.sensitive
        )

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        if control.kind is ControlKind.COMBOBOX and control.tag in {"input", "textarea"}:
            return "input_combobox_not_supported"
        return None

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).selected_text

    async def ensure_choice(
        self, driver: ControlDriver, control: ObservedControl, choice: str
    ) -> EnsureResult:
        before = await driver.state(control.candidate_id)
        if before.selected_text is not None and normalize_name(before.selected_text) == normalize_name(
            choice
        ):
            return EnsureResult(changed=False, verified=True, observed=before.selected_text)
        if before.expanded is not True:
            await driver.click(control.candidate_id)
        options = await driver.listbox_options(control.candidate_id)
        try:
            label = _match_option(options, choice)
        except ChoiceNotAvailable:
            # Açtığımız listeyi aynı tanımlı yolla kapat; başka bir şeye basma.
            await driver.click(control.candidate_id)
            raise
        await driver.click_option(control.candidate_id, label)
        after = await driver.state(control.candidate_id)
        if after.selected_text is None or normalize_name(after.selected_text) != normalize_name(label):
            raise VerificationFailed("Seçim doğrulanamadı.")
        if after.expanded is True:
            raise VerificationFailed("Liste seçimden sonra kapanmadı.")
        return EnsureResult(changed=True, verified=True, observed=after.selected_text)


class TabAdapter(ControlAdapter):
    name = "tab"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.TAB

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return "active" if (await driver.state(control.candidate_id)).selected else "inactive"

    async def activate_tab(self, driver: ControlDriver, control: ObservedControl) -> EnsureResult:
        before = await driver.state(control.candidate_id)
        if before.selected is True:
            return EnsureResult(changed=False, verified=True, observed="active")
        await driver.click(control.candidate_id)
        after = await driver.state(control.candidate_id)
        if after.selected is not True or after.panel_visible is False:
            raise VerificationFailed("Sekme etkinleşmedi veya paneli görünmüyor.")
        return EnsureResult(changed=True, verified=True, observed="active")


class TableAdapter(ControlAdapter):
    """İş anahtarıyla kayıt arama. DOM satır sırası iş kimliği değildir; anahtar tam metin eşleşmesidir."""

    name = "table"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.TABLE

    async def find_record(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        key: str,
        navigation: str,
        next_labels: list[str],
        end_text: str | None,
        limits: TableLimits,
        relocate: Relocate,
    ) -> RecordSearch:
        wanted = key.strip()
        pages, stalled, seen = 1, 0, 0
        current = control
        while True:
            keys = [k.strip() for k in await driver.table_keys(current.candidate_id)]
            seen = len(keys) if navigation == "scroll" else seen + len(keys)
            hits = keys.count(wanted)
            if hits > 1:
                return RecordSearch(RecordOutcome.DUPLICATE_KEY, pages, seen)
            if hits == 1:
                return RecordSearch(RecordOutcome.FOUND, pages, seen)
            if navigation == "none":
                return RecordSearch(RecordOutcome.NOT_FOUND_AT_END, pages, seen)
            if seen >= limits.max_rows:
                return RecordSearch(RecordOutcome.LIMIT_REACHED, pages, seen)
            if navigation == "paged":
                if pages >= limits.max_pages:
                    return RecordSearch(RecordOutcome.LIMIT_REACHED, pages, seen)
                if not await driver.table_next_page(current.candidate_id, next_labels):
                    return RecordSearch(RecordOutcome.NOT_FOUND_AT_END, pages, seen)
                pages += 1
                current = await relocate(current)
                continue
            # scroll
            if end_text is not None and await driver.text_visible(current.candidate_id, end_text):
                return RecordSearch(RecordOutcome.NOT_FOUND_AT_END, pages, seen)
            if await driver.table_load_more(current.candidate_id):
                stalled = 0
            else:
                stalled += 1
                if stalled >= limits.no_progress_limit:
                    if end_text is not None and await driver.text_visible(current.candidate_id, end_text):
                        return RecordSearch(RecordOutcome.NOT_FOUND_AT_END, pages, seen)
                    return RecordSearch(RecordOutcome.NO_PROGRESS, pages, seen)


class AdapterRegistry:
    def __init__(self, adapters: list[ControlAdapter]) -> None:
        self._adapters = adapters

    @classmethod
    def default(cls) -> AdapterRegistry:
        return cls(
            [TextboxAdapter(), NativeSelectAdapter(), CustomComboboxAdapter(), TabAdapter(), TableAdapter()]
        )

    def for_control(self, control: ObservedControl) -> ControlAdapter:
        supporting = [a for a in self._adapters if a.supports(control)]
        if len(supporting) == 1:
            return supporting[0]
        reasons = [r for a in self._adapters if (r := a.unsupported_reason(control))]
        raise ControlUnsupported(
            reasons[0] if reasons else f"unsupported_control:{control.kind.value}/{control.tag}"
        )
