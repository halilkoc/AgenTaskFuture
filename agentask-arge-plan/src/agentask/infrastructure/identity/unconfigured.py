from __future__ import annotations

from agentask.application.errors import DependencyUnavailable
from agentask.application.ports.identity import IdentityRequest
from agentask.domain.identity import Principal


class UnconfiguredIdentity:
    """AUTH_MODE=unconfigured: hiçbir isteği kabul etmez. Gerçek ortama hazır kimlik değildir."""

    source = "unconfigured"

    async def authenticate(self, request: IdentityRequest) -> Principal:
        raise DependencyUnavailable("Kimlik sağlayıcısı yapılandırılmadı.")
