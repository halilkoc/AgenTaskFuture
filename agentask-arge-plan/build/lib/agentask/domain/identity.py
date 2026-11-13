"""Kimlik domain modeli. Framework bağımlılığı yoktur."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OPERATOR = "operator"
    DESIGNER = "designer"
    PUBLISHER = "publisher"


class Capability(StrEnum):
    USE_ASSISTANT = "use_assistant"
    DESIGN_CATALOG = "design_catalog"
    PUBLISH_CATALOG = "publish_catalog"


ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.OPERATOR: frozenset({Capability.USE_ASSISTANT}),
    Role.DESIGNER: frozenset({Capability.DESIGN_CATALOG}),
    Role.PUBLISHER: frozenset({Capability.PUBLISH_CATALOG}),
}


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    display_name: str
    roles: frozenset[Role]
    identity_source: str

    @property
    def capabilities(self) -> frozenset[Capability]:
        result: set[Capability] = set()
        for role in self.roles:
            result |= ROLE_CAPABILITIES[role]
        return frozenset(result)

    def can(self, capability: Capability) -> bool:
        return capability in self.capabilities
