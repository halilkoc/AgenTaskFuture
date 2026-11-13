"""IdentityPort: gerçek SSO/JWT doğrulaması kurum entegrasyonuna açık bırakılır."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agentask.domain.identity import Principal


@dataclass(frozen=True, slots=True)
class IdentityRequest:
    """Framework'ten bağımsız kimlik girdisi. headers anahtarları küçük harftir."""

    client_host: str | None
    headers: Mapping[str, str] = field(default_factory=dict)


class IdentityPort(Protocol):
    @property
    def source(self) -> str: ...

    async def authenticate(self, request: IdentityRequest) -> Principal:
        """Principal döner; Unauthenticated / Forbidden / DependencyUnavailable fırlatabilir."""
        ...
