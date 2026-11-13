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
from typing import Literal

from agentask.application.ports.controls import ControlDriver, ControlState
from agentask.domain.actions import ErrorClass
from agentask.domain.choices import CHOICE_ISSUE_TEXT, ChoiceOption, choice_key, pick_option
from agentask.domain.dates import format_date, parse_date
from agentask.domain.observation import ControlKind, ObservedControl


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


class InvalidDate(ChoiceNotAvailable):
    """Değer beyan edilen biçimde geçerli bir tarih değil; alana hiçbir şey yazılmadı."""


class SuggestionNotFound(ChoiceNotAvailable):
    """Öneri bulunamadı ve alan eski değerine döndürüldü (okunarak doğrulandı)."""


class TargetNotReady(AdapterError):
    error_class = ErrorClass.TARGET_NOT_READY
    retry_safe = True


class StaleTarget(AdapterError):
    error_class = ErrorClass.FRAME_CHANGED
    retry_safe = True


class TargetBlocked(StaleTarget):
    """Eylem anında hedef bir pencere/katmanın arkasında: hiçbir eylem yapılmadı. Hedef yeniden çözülür (eski
    element kullanılmaz); engel sürerse çözüm aşamasındaki sınırlı bekleme TARGET_BLOCKED ile durur."""

    error_class = ErrorClass.TARGET_BLOCKED


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
OnDispatch = Callable[[], Awaitable[None]]
OptionReader = Callable[[str], Awaitable[list[ChoiceOption]]]
_MAX_OPTION_WAITS = 10


@dataclass(frozen=True, slots=True)
class ChoiceInspection:
    """Seçenek gözlemi. needs_open: özel liste kapalı; okumak için açık kullanıcı eylemi gerekir."""

    status: Literal["ok", "needs_open"]
    options: tuple[ChoiceOption, ...] = ()
    current: str | None = None


def _pick(options: list[ChoiceOption], choice: str, expected_value: str | None) -> ChoiceOption:
    option, issue = pick_option(options, choice, expected_value)
    if option is None:
        assert issue is not None
        raise ChoiceNotAvailable(CHOICE_ISSUE_TEXT[issue])
    return option


async def _listed(driver: ControlDriver, cid: str, read: OptionReader, choice: str) -> list[ChoiceOption]:
    """Seçenekler gecikmeli yüklenebilir: istenen etiket görünene veya liste durana dek sınırlı bekler."""
    wanted = choice_key(choice)
    items = await read(cid)
    for _ in range(_MAX_OPTION_WAITS):
        if any(choice_key(o.label) == wanted for o in items):
            break
        newer = await driver.await_options_change(cid, items)
        if newer is None:
            break
        items = newer
    return items


def _same_choice(state: ControlState, option: ChoiceOption) -> bool:
    if state.selected_text is None or choice_key(state.selected_text) != choice_key(option.label):
        return False
    return option.value is None or state.selected_value is None or state.selected_value == option.value


def _verify_choice(after: ControlState, option: ChoiceOption) -> None:
    if after.selected_text is None or choice_key(after.selected_text) != choice_key(option.label):
        raise VerificationFailed("Seçim doğrulanamadı.")
    if option.value is not None and after.selected_value not in {None, option.value}:
        raise VerificationFailed("Görünen seçenek doğru ancak alandaki gerçek değer farklı.")


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
        self,
        driver: ControlDriver,
        control: ObservedControl,
        choice: str,
        *,
        expected_value: str | None = None,
        on_dispatch: OnDispatch | None = None,
        verify: bool = True,
    ) -> EnsureResult:
        """on_dispatch: gerçek seçim gönderilmeden hemen önce çağrılır (checkpoint için)."""
        raise ControlUnsupported(f"{self.name} seçim desteklemiyor")

    async def inspect_options(
        self, driver: ControlDriver, control: ObservedControl, open_list: bool
    ) -> ChoiceInspection:
        """Seçenekleri okur; seçim veya değer değişikliği YAPMAZ. Özel liste yalnız open_list ile açılır."""
        raise ControlUnsupported("not_a_choice_control")

    async def activate_tab(self, driver: ControlDriver, control: ObservedControl) -> EnsureResult:
        raise ControlUnsupported(f"{self.name} sekme etkinleştirmeyi desteklemiyor")

    async def ensure_checked(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        checked: bool,
        *,
        on_dispatch: OnDispatch | None = None,
    ) -> EnsureResult:
        raise ControlUnsupported(f"{self.name} işaretlemeyi desteklemiyor")

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
        return (
            control.kind is ControlKind.SELECT
            and control.tag == "select"
            and not control.sensitive
            and not control.multiple
        )

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        if control.kind is not ControlKind.SELECT:
            return None
        if control.sensitive:
            return "sensitive_target_requires_secret_ref"
        return "multi_select_not_supported" if control.multiple else None

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).selected_text

    async def ensure_choice(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        choice: str,
        *,
        expected_value: str | None = None,
        on_dispatch: OnDispatch | None = None,
        verify: bool = True,
    ) -> EnsureResult:
        cid = control.candidate_id
        before = await driver.state(cid)
        # Seçenekler her zaman güncel DOM'dan okunur; gözlemdeki (kısaltılmış) liste kullanılmaz.
        option = _pick(await _listed(driver, cid, driver.choice_options, choice), choice, expected_value)
        if _same_choice(before, option):
            return EnsureResult(changed=False, verified=True, observed=before.selected_text)
        if not before.enabled:
            raise TargetNotReady("Alan etkin değil.")
        if on_dispatch is not None:
            await on_dispatch()
        await driver.select_option(cid, option.label)
        if not verify:  # seçim ekranı değiştirir; sonucu hedef ekran doğrular
            return EnsureResult(changed=True, verified=False, observed=None)
        await driver.settle()
        after = await driver.state(cid)
        _verify_choice(after, option)
        return EnsureResult(changed=True, verified=True, observed=after.selected_text)

    async def inspect_options(
        self, driver: ControlDriver, control: ObservedControl, open_list: bool
    ) -> ChoiceInspection:
        cid = control.candidate_id
        items = await driver.choice_options(cid)
        if not [o for o in items if not o.placeholder]:  # seçenekler henüz yüklenmemiş olabilir
            items = await driver.await_options_change(cid, items) or items
        return ChoiceInspection("ok", tuple(items), (await driver.state(cid)).selected_text)


class CustomComboboxAdapter(ControlAdapter):
    """DOM'dan güvenilir çözümlenen özel seçim: role=combobox veya aria-haspopup=listbox düğmesi + listbox,
    ya da sayfada açık duran tekli role=listbox. Yazarak arama yapan kutu ve çoklu seçim yok."""

    name = "custom_combobox"

    def supports(self, control: ObservedControl) -> bool:
        return (
            control.kind is ControlKind.COMBOBOX
            and control.tag not in {"input", "textarea", ""}
            and not control.sensitive
            and not control.multiple
        )

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        if control.kind is not ControlKind.COMBOBOX:
            return None
        if control.tag in {"input", "textarea"}:
            return "input_combobox_not_supported"
        if control.sensitive:
            return "sensitive_target_requires_secret_ref"
        return "multi_select_not_supported" if control.multiple else None

    @staticmethod
    def _inline(control: ObservedControl) -> bool:
        return control.role == "listbox"

    @staticmethod
    async def _read_open(driver: ControlDriver, cid: str) -> list[ChoiceOption]:
        try:
            return await driver.listbox_options(cid)
        except TargetNotReady:
            raise ControlUnsupported("listbox_not_accessible") from None

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).selected_text

    async def ensure_choice(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        choice: str,
        *,
        expected_value: str | None = None,
        on_dispatch: OnDispatch | None = None,
        verify: bool = True,
    ) -> EnsureResult:
        cid = control.candidate_id
        inline = self._inline(control)
        before = await driver.state(cid)
        current = ChoiceOption(choice, expected_value)
        if _same_choice(before, current):
            return EnsureResult(changed=False, verified=True, observed=before.selected_text)
        opened = False
        if not inline and before.expanded is not True:
            await driver.click(cid)
            opened = True
        try:
            items = await _listed(driver, cid, lambda c: self._read_open(driver, c), choice)
            option = _pick(items, choice, expected_value)
            await driver.click_option(cid, option.label, trial=True)
        except (ChoiceNotAvailable, ControlUnsupported):
            if opened:  # açtığımız listeyi aynı tanımlı yolla kapat; başka bir şeye basma
                await driver.click(cid)
            raise
        if on_dispatch is not None:
            await on_dispatch()
        await driver.click_option(cid, option.label)
        if not verify:
            return EnsureResult(changed=True, verified=False, observed=None)
        await driver.settle()
        after = await driver.state(cid)
        _verify_choice(after, option)
        if after.expanded is True:
            raise VerificationFailed("Liste seçimden sonra kapanmadı.")
        return EnsureResult(changed=True, verified=True, observed=after.selected_text)

    async def inspect_options(
        self, driver: ControlDriver, control: ObservedControl, open_list: bool
    ) -> ChoiceInspection:
        cid = control.candidate_id
        before = await driver.state(cid)
        if self._inline(control) or before.expanded is True:
            return ChoiceInspection("ok", tuple(await self._read_open(driver, cid)), before.selected_text)
        if not open_list:
            return ChoiceInspection("needs_open", (), before.selected_text)
        await driver.click(cid)
        try:
            items = await self._read_open(driver, cid)
        finally:
            if (await driver.state(cid)).expanded is True:
                await driver.click(cid)  # yalnız açtığımız liste kapatılır; seçenek tıklanmaz
        after = await driver.state(cid)
        if after.selected_text != before.selected_text:
            raise VerificationFailed("Liste açılırken alandaki seçim değişti.")
        return ChoiceInspection("ok", tuple(items), before.selected_text)


class RadioGroupAdapter(CustomComboboxAdapter):
    """Tek hedef olarak modellenen seçenek grubu (fieldset/legend veya role=radiogroup)."""

    name = "radio_group"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.RADIO_GROUP and not control.sensitive

    def unsupported_reason(self, control: ObservedControl) -> str | None:
        return None

    @staticmethod
    def _inline(control: ObservedControl) -> bool:
        return True

    @staticmethod
    async def _read_open(driver: ControlDriver, cid: str) -> list[ChoiceOption]:
        return await driver.choice_options(cid)


class MultiSelectAdapter(ControlAdapter):
    """Tam küme. Tüm üyeler değişiklikten önce doğrulanır; yalnız fark uygulanır; sonuç küme olarak okunur."""

    name = "multi_select"

    def supports(self, control: ObservedControl) -> bool:
        return (
            control.kind in {ControlKind.SELECT, ControlKind.COMBOBOX}
            and control.multiple
            and not control.sensitive
        )

    async def inspect_options(
        self, driver: ControlDriver, control: ObservedControl, open_list: bool
    ) -> ChoiceInspection:
        items = await driver.choice_options(control.candidate_id)
        selected = ", ".join(o.label for o in items if o.selected) or None
        return ChoiceInspection("ok", tuple(items), selected)

    async def ensure_choices(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        wanted: list[str],
        *,
        on_dispatch: OnDispatch | None = None,
    ) -> EnsureResult:
        cid = control.candidate_id
        if not (await driver.state(cid)).enabled:
            raise TargetNotReady("Alan etkin değil.")
        options = await driver.choice_options(cid)
        chosen: list[ChoiceOption] = []
        for label in wanted:
            option, issue = pick_option(options, label, None)
            if option is None:
                assert issue is not None
                raise ChoiceNotAvailable(CHOICE_ISSUE_TEXT[issue])
            chosen.append(option)
        keys = {choice_key(o.label) for o in chosen}
        current = {choice_key(o.label): o for o in options if o.selected}
        adding = [o for o in chosen if choice_key(o.label) not in current]
        removing = [o for k, o in current.items() if k not in keys]
        if any(not o.enabled for o in removing):
            raise ChoiceNotAvailable(
                "Kaldırılması gereken bir seçenek devre dışı; hiçbir değişiklik yapılmadı."
            )
        if not adding and not removing:
            return EnsureResult(changed=False, verified=True, observed=None)
        if on_dispatch is not None:
            await on_dispatch()
        if control.kind is ControlKind.SELECT:
            await driver.select_options(cid, [o.label for o in chosen])
        else:
            for option in [*adding, *removing]:
                await driver.click_option(cid, option.label)
        await driver.settle()
        after = {choice_key(o.label) for o in await driver.choice_options(cid) if o.selected}
        if after != keys:
            raise VerificationFailed("Alandaki seçim kümesi istenen kümeyle aynı değil.")
        return EnsureResult(changed=True, verified=True, observed=None)


class DateAdapter(ControlAdapter):
    """Düz, maskeli veya type=date alanı. Geçersiz tarih yazılmaz; sonuç tarih olarak okunarak doğrulanır."""

    name = "date"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.TEXTBOX and control.tag == "input" and not control.sensitive

    async def ensure_date(
        self, driver: ControlDriver, control: ObservedControl, value: str, date_format: str
    ) -> EnsureResult:
        wanted = parse_date(value, date_format)
        if wanted is None:
            raise InvalidDate("Değer geçerli bir tarih değil; alana yazılmadı.")
        cid = control.candidate_id
        before = await driver.state(cid)
        if before.value and parse_date(before.value, date_format) == wanted:
            return EnsureResult(changed=False, verified=True, observed=None)
        if not before.enabled or before.read_only:
            raise TargetNotReady("Tarih alanı yazmaya kapalı; takvim açılır penceresi desteklenmiyor.")
        text = wanted.isoformat() if before.input_type == "date" else format_date(wanted, date_format)
        await driver.fill(cid, text)
        await driver.settle()
        after = await driver.state(cid)
        if not after.value or parse_date(after.value, date_format) != wanted:
            raise VerificationFailed("Uygulama yazılan tarihi kabul etmedi veya farklı bir tarihe çevirdi.")
        return EnsureResult(changed=True, verified=True, observed=None)


class CheckboxAdapter(ControlAdapter):
    name = "checkbox"

    def supports(self, control: ObservedControl) -> bool:
        return control.kind is ControlKind.CHECKBOX and not control.sensitive

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        state = await driver.state(control.candidate_id)
        return None if state.checked is None else ("işaretli" if state.checked else "işaretli değil")

    async def ensure_checked(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        checked: bool,
        *,
        on_dispatch: OnDispatch | None = None,
    ) -> EnsureResult:
        cid = control.candidate_id
        before = await driver.state(cid)
        if before.checked is None:
            raise ControlUnsupported("checkbox_state_unknown")
        if before.checked is checked:
            return EnsureResult(changed=False, verified=True, observed=str(checked))
        if not before.enabled:
            raise TargetNotReady("Onay kutusu etkin değil.")
        if on_dispatch is not None:
            await on_dispatch()
        await driver.set_checked(cid, checked)
        await driver.settle()
        after = await driver.state(cid)
        if after.checked is not checked:
            raise VerificationFailed("Onay kutusunun durumu istenen değere gelmedi.")
        return EnsureResult(changed=True, verified=True, observed=str(checked))


class AutocompleteAdapter(ControlAdapter):
    """Yazınca öneri listesi açan alan. Arama yazmak ekranı değiştirir; seçim yapılamazsa eski değer yazılır
    ve bu okunarak doğrulanır. Uygulamanın arka planda yaptığı sorguların etkisi bu kanıtın dışındadır."""

    name = "autocomplete"

    def supports(self, control: ObservedControl) -> bool:
        return (
            control.kind in {ControlKind.COMBOBOX, ControlKind.TEXTBOX}
            and control.tag == "input"
            and not control.sensitive
        )

    async def read(self, driver: ControlDriver, control: ObservedControl) -> str | None:
        return (await driver.state(control.candidate_id)).value

    async def _restore(self, driver: ControlDriver, cid: str, before: ControlState) -> bool:
        """Eski metin yeniden yazılır. Görünen metin VE alandaki gerçek değer önceki haliyle aynıysa
        döndürülmüş sayılır; yalnız metnin geri gelmesi seçimin geri geldiğini kanıtlamaz."""
        await driver.fill(cid, before.value or "")
        await driver.settle()
        after = await driver.state(cid)
        return (after.value or "") == (before.value or "") and after.selected_value == before.selected_value

    async def ensure_choice(
        self,
        driver: ControlDriver,
        control: ObservedControl,
        choice: str,
        *,
        expected_value: str | None = None,
        on_dispatch: OnDispatch | None = None,
        verify: bool = True,
        search_text: str | None = None,
    ) -> EnsureResult:
        cid = control.candidate_id
        before = await driver.state(cid)
        if (
            before.value
            and choice_key(before.value) == choice_key(choice)
            and (expected_value is None or before.selected_value in {None, expected_value})
        ):
            return EnsureResult(changed=False, verified=True, observed=before.value)
        if not before.enabled:
            raise TargetNotReady("Alan etkin değil.")
        if on_dispatch is not None:
            await on_dispatch()
        await driver.fill(cid, search_text or choice)
        try:
            items = await _listed(driver, cid, driver.listbox_options, choice)
        except TargetNotReady:
            items = []
        option, issue = pick_option(items, choice, expected_value)
        if option is None:
            assert issue is not None
            if await self._restore(driver, cid, before):
                raise SuggestionNotFound(f"{CHOICE_ISSUE_TEXT[issue]} Alan eski değerine döndürüldü.")
            raise VerificationFailed(
                "Öneri seçilemedi ve alan eski değerine döndürülemedi; ekranı kontrol edin."
            )
        await driver.click_option(cid, option.label)
        if not verify:
            return EnsureResult(changed=True, verified=False, observed=None)
        await driver.settle()
        after = await driver.state(cid)
        if not after.value or choice_key(after.value) != choice_key(option.label):
            raise VerificationFailed("Seçilen öneri alanda görülmedi.")
        if option.value is not None and after.selected_value not in {None, option.value}:
            raise VerificationFailed("Görünen öneri doğru ancak alandaki gerçek değer farklı.")
        return EnsureResult(changed=True, verified=True, observed=after.value)

    async def preview(self, driver: ControlDriver, control: ObservedControl, search: str) -> ChoiceInspection:
        """Tasarımda örnek arama: yazar, önerileri okur, eski değeri geri yazar ve doğrular. Seçim yapmaz."""
        cid = control.candidate_id
        before = await driver.state(cid)
        await driver.fill(cid, search)
        try:
            items = await driver.listbox_options(cid)
        except TargetNotReady:
            items = []
        if not await self._restore(driver, cid, before):
            raise VerificationFailed(
                "Örnek arama sonrası alan eski değerine döndürülemedi; ekranı kontrol edin."
            )
        return ChoiceInspection("ok", tuple(items), before.value)


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
            [
                TextboxAdapter(),
                NativeSelectAdapter(),
                CustomComboboxAdapter(),
                RadioGroupAdapter(),
                CheckboxAdapter(),
                TabAdapter(),
                TableAdapter(),
            ]
        )

    def for_multi(self, control: ObservedControl) -> MultiSelectAdapter:
        adapter = MultiSelectAdapter()
        if not adapter.supports(control):
            raise ControlUnsupported(
                "sensitive_target_requires_secret_ref" if control.sensitive else "not_multi_select"
            )
        return adapter

    def for_date(self, control: ObservedControl) -> DateAdapter:
        adapter = DateAdapter()
        if not adapter.supports(control):
            raise ControlUnsupported(
                "sensitive_target_requires_secret_ref" if control.sensitive else "date_requires_input"
            )
        return adapter

    def for_autocomplete(self, control: ObservedControl) -> AutocompleteAdapter:
        adapter = AutocompleteAdapter()
        if not adapter.supports(control):
            raise ControlUnsupported(
                "sensitive_target_requires_secret_ref" if control.sensitive else "autocomplete_requires_input"
            )
        return adapter

    def for_control(self, control: ObservedControl) -> ControlAdapter:
        supporting = [a for a in self._adapters if a.supports(control)]
        if len(supporting) == 1:
            return supporting[0]
        reasons = [r for a in self._adapters if (r := a.unsupported_reason(control))]
        raise ControlUnsupported(
            reasons[0] if reasons else f"unsupported_control:{control.kind.value}/{control.tag}"
        )
