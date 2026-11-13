"""Onaylı aksiyon özeti ve uygulama bağı (K1): değişen aksiyon onay, yayın ve çalıştırmada reddedilir."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from agentask.application.errors import PlanInvalid
from agentask.application.services.designer import DesignerService
from agentask.config import ConfigurationError
from agentask.domain.actions import ActionSet
from agentask.domain.catalog import OperationDraft, compile_operation, definition_schema
from agentask.domain.commands import Command, PlanRejected, validate_plan
from agentask.infrastructure.approved_actions.file import load_action_set
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.wizard import CUSTOMER_SCREEN

BASE: dict[str, Any] = {
    "action_id": "kurum.kaydet",
    "title": "Kaydet",
    "application_id": "lab",
    "target": {"kind": "button", "labels": ["Kaydet"]},
    "effect": "non_mutating",
    "retry_safe": False,
    "params": [],
    "outcome": {"evidence": {"kind": "status_text"}, "success": {"mode": "contains", "text": "Tamam"}},
}


def action_set(**change: Any) -> ActionSet:
    return ActionSet.model_validate({"actions": {"kurum.kaydet": {**BASE, **change}}})


FP = action_set().fingerprint("kurum.kaydet")


@pytest.mark.parametrize(
    "change",
    [
        {"target": {"kind": "button", "labels": ["Gönder"]}},
        {"retry_safe": True},
        {"outcome": {"evidence": {"kind": "status_text"}, "success": {"mode": "contains", "text": "Başka"}}},
        {"application_id": "baska"},
        {"params": [{"name": "a", "title": "A", "max_length": 5}]},
    ],
)
def test_behaviour_change_changes_fingerprint(change: dict[str, Any]) -> None:
    assert action_set(**change).fingerprint("kurum.kaydet") != FP


def test_title_is_not_behaviour_but_blockers_are() -> None:
    assert action_set(title="Yeni ad").fingerprint("kurum.kaydet") == FP
    blocked = ActionSet.model_validate(
        {
            "actions": {"kurum.kaydet": BASE},
            "blockers": [
                {
                    "blocker_id": "uyari.tamam",
                    "dialog_name": "Uyarı",
                    "text": {"mode": "contains", "text": "x"},
                    "button_label": "Tamam",
                }
            ],
        }
    )
    assert blocked.fingerprint("kurum.kaydet") != FP


def test_problem_codes() -> None:
    actions = action_set()
    assert actions.problem("kurum.kaydet", FP, "lab") is None
    assert actions.problem("yok.boyle", FP, "lab") == "unknown_action"
    assert actions.problem("kurum.kaydet", FP, "baska") == "action_wrong_application"
    assert actions.problem("kurum.kaydet", None, "lab") == "action_unpinned"
    assert actions.problem("kurum.kaydet", "0" * 64, "lab") == "action_changed"
    legacy = ActionSet.model_validate({"actions": {"kurum.kaydet": {**BASE, "application_id": None}}})
    assert legacy.problem("kurum.kaydet", None, "lab") is None  # deney seti eski yayınları çalışır


def draft_with_action(tmp_path: Path, actions: ActionSet) -> tuple[DesignerService, OperationDraft]:
    repo = LocalFileDraftRepository(tmp_path / "d")
    service = DesignerService(repo, None, None, None, actions, 1.0)  # type: ignore[arg-type]
    draft = service.create_draft("a", application_id="lab", operation_id="op", title="T", description="")
    draft, step = service.add_step("a", draft.draft_id, draft.revision, "kaydet")
    draft = service.configure_step(
        "a",
        draft.draft_id,
        draft.revision,
        step.step_id,
        op="invoke_approved_action",
        action_id="kurum.kaydet",
    )
    draft.screen = CUSTOMER_SCREEN
    return service, draft


def test_configure_pins_and_compile_rejects_changed_action(tmp_path: Path) -> None:
    actions = action_set()
    _, draft = draft_with_action(tmp_path, actions)
    assert draft.steps[0].action_hash == FP
    assert definition_schema(draft.definition()) == "catalog-v6"
    plan = compile_operation(draft, {}, actions)
    assert plan[1]["action_hash"] == FP and plan[1]["application_id"] == "lab"
    changed = action_set(retry_safe=True)
    with pytest.raises(ValueError, match="action_changed"):
        compile_operation(draft, {}, changed)
    assert any("action_changed" in i for i in draft.validation_issues(changed))


def test_action_of_other_application_cannot_be_selected(tmp_path: Path) -> None:
    repo = LocalFileDraftRepository(tmp_path / "d")
    service = DesignerService(repo, None, None, None, action_set(application_id="baska"), 1.0)  # type: ignore[arg-type]
    draft = service.create_draft("a", application_id="lab", operation_id="op", title="T", description="")
    draft, step = service.add_step("a", draft.draft_id, draft.revision, "kaydet")
    with pytest.raises(PlanInvalid) as caught:
        service.configure_step(
            "a",
            draft.draft_id,
            draft.revision,
            step.step_id,
            op="invoke_approved_action",
            action_id="kurum.kaydet",
        )
    assert caught.value.details["reason"] == "action_wrong_application"


def test_old_unpinned_definition_keeps_hash_and_schema(tmp_path: Path) -> None:
    actions = action_set(application_id=None)
    _, draft = draft_with_action(tmp_path, actions)
    draft.steps[0].action_hash = None
    assert "action_hash" not in draft.definition()["steps"][0]
    assert definition_schema(draft.definition()) != "catalog-v6"
    assert "action_hash" not in compile_operation(draft, {}, actions)[1]


def test_validate_plan_rejects_changed_hash() -> None:
    command = TypeAdapter(Command).validate_python(
        {"op": "invoke_approved_action", "action_id": "kurum.kaydet", "action_hash": "a" * 64}
    )
    with pytest.raises(PlanRejected, match="action_changed"):
        validate_plan([command], action_set(), max_steps=5)


def test_file_requires_application_binding(tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps({"actions": {"kurum.kaydet": {**BASE, "application_id": None}}}), encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="application_id"):
        load_action_set(path)
    path.write_text(json.dumps({"actions": {"kurum.kaydet": BASE}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="AUTOMATION"):
        load_action_set(path, frozenset({"baska"}))
    assert load_action_set(path, frozenset({"lab"})).fingerprint("kurum.kaydet") == FP
