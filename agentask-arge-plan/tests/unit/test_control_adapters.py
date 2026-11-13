"""Adapter mantığı (sahte sürücü): gereksiz işlem yok, sonrası doğrulanır, desteklenmeyen açıkça döner."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from agentask.application.controls import (
    AdapterRegistry,
    ChoiceNotAvailable,
    ControlUnsupported,
    RecordOutcome,
    TableLimits,
    VerificationFailed,
)
from agentask.application.ports.controls import ControlState
from agentask.domain.choices import ChoiceOption
from agentask.domain.observation import ControlKind, ObservedControl


def control(
    kind: ControlKind,
    *,
    role: str = "",
    tag: str = "input",
    sensitive: bool = False,
    options: tuple[str, ...] = (),
    label: str = "Alan",
) -> ObservedControl:
    return ObservedControl(
        candidate_id="c-s1-0",
        frame_ref="f1",
        kind=kind,
        role=role or kind.value,
        accessible_name=label,
        label=label,
        visible=True,
        enabled=True,
        sensitive=sensitive,
        has_value=False,
        selected_text=None,
        options=options,
        contexts=(),
        frame_titles=(),
        tag=tag,
    )


@dataclass
class FakeDriver:
    state_value: ControlState = field(default_factory=ControlState)
    calls: list[str] = field(default_factory=list)
    fill_result: str | None = None  # None → yazılan değer okunur
    listbox: list[str] = field(default_factory=list)
    native: list[str] = field(default_factory=list)
    pages: list[list[str]] = field(default_factory=list)
    page_index: int = 0
    growth: list[list[str]] = field(default_factory=list)
    end_visible: bool = False

    async def state(self, cid: str) -> ControlState:
        self.calls.append("state")
        return self.state_value

    async def fill(self, cid: str, value: str) -> None:
        self.calls.append(f"fill:{value}")
        self.state_value = replace(
            self.state_value, value=self.fill_result if self.fill_result is not None else value
        )

    async def select_option(self, cid: str, label: str) -> None:
        self.calls.append(f"select:{label}")
        self.state_value = replace(self.state_value, selected_text=label)

    async def click(self, cid: str) -> None:
        self.calls.append("click")
        if self.state_value.selected is False:
            self.state_value = replace(self.state_value, selected=True, panel_visible=True)
        elif self.state_value.expanded is False:
            self.state_value = replace(self.state_value, expanded=True)

    async def choice_options(self, cid: str) -> list[ChoiceOption]:
        return [ChoiceOption(o, None) for o in self.native]

    async def listbox_options(self, cid: str) -> list[ChoiceOption]:
        self.calls.append("options")
        return [ChoiceOption(o, None) for o in self.listbox]

    async def await_options_change(self, cid: str, previous: list[ChoiceOption]) -> list[ChoiceOption] | None:
        return None

    async def settle(self) -> None:
        return None

    async def click_option(self, cid: str, label: str, trial: bool = False) -> None:
        if trial:
            return
        self.calls.append(f"option:{label}")
        self.state_value = replace(self.state_value, selected_text=label, expanded=False)

    async def table_keys(self, cid: str) -> list[str]:
        if self.pages:
            return self.pages[self.page_index]
        return self.growth[0] if self.growth else []

    async def table_next_page(self, cid: str, labels: list[str]) -> bool:
        self.calls.append("next")
        if self.page_index + 1 >= len(self.pages):
            return False
        self.page_index += 1
        return True

    async def table_load_more(self, cid: str) -> bool:
        self.calls.append("more")
        if len(self.growth) > 1:
            self.growth.pop(0)
            return True
        return False

    async def text_visible(self, cid: str, text: str) -> bool:
        return self.end_visible


async def same(c: ObservedControl) -> ObservedControl:
    return c


REG = AdapterRegistry.default()


async def test_ensure_value_no_change_makes_no_write() -> None:
    driver = FakeDriver(ControlState(value="007"))
    result = await REG.for_control(control(ControlKind.TEXTBOX)).ensure_value(
        driver, control(ControlKind.TEXTBOX), "007"
    )
    assert result.changed is False and result.verified is True
    assert driver.calls == ["state"]


async def test_ensure_value_writes_and_verifies_preserving_leading_zeros() -> None:
    driver = FakeDriver(ControlState(value="7"))
    result = await REG.for_control(control(ControlKind.TEXTBOX)).ensure_value(
        driver, control(ControlKind.TEXTBOX), "007"
    )
    assert result.changed and result.verified and result.observed == "007"
    assert driver.calls == ["state", "fill:007", "state"]


async def test_ensure_value_detects_mismatch_after_write() -> None:
    driver = FakeDriver(ControlState(value=""), fill_result="00")
    with pytest.raises(VerificationFailed):
        await REG.for_control(control(ControlKind.TEXTBOX)).ensure_value(
            driver, control(ControlKind.TEXTBOX), "007"
        )


def test_sensitive_textbox_is_unsupported() -> None:
    with pytest.raises(ControlUnsupported, match="sensitive"):
        REG.for_control(control(ControlKind.TEXTBOX, sensitive=True))


def test_input_based_combobox_is_unsupported() -> None:
    with pytest.raises(ControlUnsupported):
        REG.for_control(control(ControlKind.COMBOBOX, role="combobox", tag="input"))


async def test_native_select_chooses_by_normalized_label_once() -> None:
    c = control(ControlKind.SELECT, role="select", tag="select", options=("Seçiniz", "Kadıköy", "Konak"))
    driver = FakeDriver(ControlState(selected_text="Seçiniz"), native=["Seçiniz", "Kadıköy", "Konak"])
    adapter = REG.for_control(c)
    assert (await adapter.ensure_choice(driver, c, "KONAK")).changed
    assert driver.calls == ["state", "select:Konak", "state"]
    driver.calls.clear()
    assert not (await adapter.ensure_choice(driver, c, "konak")).changed
    assert driver.calls == ["state"]


async def test_native_select_missing_choice_is_known_failure_without_write() -> None:
    c = control(ControlKind.SELECT, role="select", tag="select", options=("Kadıköy", "Konak"))
    driver = FakeDriver(ControlState(selected_text="Kadıköy"), native=["Kadıköy", "Konak"])
    with pytest.raises(ChoiceNotAvailable):
        await REG.for_control(c).ensure_choice(driver, c, "Kon")
    assert not any(call.startswith("select") for call in driver.calls)


async def test_custom_combobox_opens_selects_and_verifies() -> None:
    c = control(ControlKind.COMBOBOX, role="combobox", tag="div")
    driver = FakeDriver(
        ControlState(selected_text="Seçiniz", expanded=False), listbox=["Bireysel Kart", "Ek Kart"]
    )
    result = await REG.for_control(c).ensure_choice(driver, c, "Ek Kart")
    assert result.changed and driver.calls == ["state", "click", "options", "option:Ek Kart", "state"]


async def test_custom_combobox_ambiguous_option_rejected() -> None:
    c = control(ControlKind.COMBOBOX, role="combobox", tag="div")
    driver = FakeDriver(
        ControlState(selected_text="Seçiniz", expanded=False), listbox=["Ek Kart", "Ek  kart"]
    )
    with pytest.raises(ChoiceNotAvailable):
        await REG.for_control(c).ensure_choice(driver, c, "Ek Kart")
    assert not any(call.startswith("option:") for call in driver.calls)


async def test_tab_activation_and_no_change() -> None:
    c = control(ControlKind.TAB, role="tab", tag="button")
    driver = FakeDriver(ControlState(selected=False, panel_visible=False))
    assert (await REG.for_control(c).activate_tab(driver, c)).changed
    driver.calls.clear()
    assert not (await REG.for_control(c).activate_tab(driver, c)).changed
    assert driver.calls == ["state"]


LIMITS = TableLimits(max_pages=3, max_rows=100, no_progress_limit=2)


async def test_find_record_paged() -> None:
    t = control(ControlKind.TABLE, role="table", tag="table")
    driver = FakeDriver(pages=[["B-1", "B-2"], ["B-3", "B-4"]])
    found = await REG.for_control(t).find_record(driver, t, "B-4", "paged", ["Sonraki"], None, LIMITS, same)
    assert found.outcome is RecordOutcome.FOUND and found.pages_visited == 2


async def test_find_record_limit_vs_end() -> None:
    t = control(ControlKind.TABLE, role="table", tag="table")
    end = await REG.for_control(t).find_record(
        FakeDriver(pages=[["B-1"], ["B-2"]]), t, "B-9", "paged", ["Sonraki"], None, LIMITS, same
    )
    assert end.outcome is RecordOutcome.NOT_FOUND_AT_END
    limit = await REG.for_control(t).find_record(
        FakeDriver(pages=[["a"], ["b"], ["c"], ["d"]]), t, "z", "paged", ["Sonraki"], None, LIMITS, same
    )
    assert limit.outcome is RecordOutcome.LIMIT_REACHED


async def test_find_record_duplicate_key() -> None:
    t = control(ControlKind.TABLE, role="table", tag="table")
    dup = await REG.for_control(t).find_record(
        FakeDriver(pages=[["B-1", "B-1"]]), t, "B-1", "none", [], None, LIMITS, same
    )
    assert dup.outcome is RecordOutcome.DUPLICATE_KEY


async def test_find_record_scroll_no_progress_vs_end_marker() -> None:
    t = control(ControlKind.TABLE, role="table", tag="table")
    stuck = FakeDriver(growth=[["a"]])
    result = await REG.for_control(t).find_record(stuck, t, "z", "scroll", [], None, LIMITS, same)
    assert result.outcome is RecordOutcome.NO_PROGRESS
    ended = FakeDriver(growth=[["a"]], end_visible=True)
    result = await REG.for_control(t).find_record(
        ended, t, "z", "scroll", [], "Tüm kayıtlar yüklendi", LIMITS, same
    )
    assert result.outcome is RecordOutcome.NOT_FOUND_AT_END
    grows = FakeDriver(growth=[["a"], ["a", "b"], ["a", "b", "z"]])
    result = await REG.for_control(t).find_record(grows, t, "z", "scroll", [], None, LIMITS, same)
    assert result.outcome is RecordOutcome.FOUND


async def test_unsupported_operation_for_kind() -> None:
    with pytest.raises(ControlUnsupported):
        await REG.for_control(control(ControlKind.TAB, role="tab", tag="button")).ensure_value(
            FakeDriver(), control(ControlKind.TAB, role="tab", tag="button"), "x"
        )
