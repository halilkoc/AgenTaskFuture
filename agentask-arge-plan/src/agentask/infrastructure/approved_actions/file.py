"""APPROVED_ACTION_SET=file: kurumun onayladığı aksiyonlar tipli JSON dosyasından okunur."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from agentask.config.errors import ConfigurationError
from agentask.domain.actions import ActionSet


def load_action_set(path: Path, applications: frozenset[str] | None = None) -> ActionSet:
    try:
        actions = ActionSet.model_validate_json(path.read_bytes())
    except OSError:
        raise ConfigurationError(["APPROVED_ACTIONS_FILE okunamadı."]) from None
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors(include_input=False)})[:10]
        raise ConfigurationError([f"APPROVED_ACTIONS_FILE geçersiz: {', '.join(fields)}"]) from None
    wrong = [key for key, action in actions.actions.items() if key != action.action_id]
    if wrong:
        raise ConfigurationError(["APPROVED_ACTIONS_FILE: anahtar ile action_id aynı olmalı."])
    unbound = [a.action_id for a in actions.actions.values() if a.application_id is None]
    if unbound:
        raise ConfigurationError(["APPROVED_ACTIONS_FILE: her aksiyon application_id taşımalı."])
    if applications is not None and any(
        a.application_id not in applications for a in actions.actions.values()
    ):
        raise ConfigurationError(
            ["APPROVED_ACTIONS_FILE: application_id, AUTOMATION_APPLICATIONS_JSON içinde olmalı."]
        )
    return actions
