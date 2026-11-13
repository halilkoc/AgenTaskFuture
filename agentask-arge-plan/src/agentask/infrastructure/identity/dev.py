"""Yalnızca yerel Ar-Ge için impersonation adapteri.

Sınırlar: composition root yalnızca APP_ENV=development + DEV_AUTH_ENABLED=true + loopback APP_HOST
ile oluşturur (Settings doğrular). Adapter ayrıca her istekte istemcinin loopback olduğunu denetler.
Kimlik X-Dev-User / X-Dev-Roles başlıklarından okunur; doğrulama yapılmaz, bu yüzden gerçek ortamda
kullanılamaz.
"""

from __future__ import annotations

import re

from agentask.application.errors import Forbidden, Unauthenticated
from agentask.application.ports.identity import IdentityRequest
from agentask.config.settings import is_loopback_host
from agentask.domain.identity import Principal, Role

DEV_USER_HEADER = "x-dev-user"
DEV_ROLES_HEADER = "x-dev-roles"
DEFAULT_DEV_USER = "dev.user"
_USER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class DevIdentity:
    source = "dev"

    async def authenticate(self, request: IdentityRequest) -> Principal:
        if request.client_host is None or not is_loopback_host(request.client_host):
            raise Forbidden("Geliştirici kimliği yalnızca yerel bağlantıdan kullanılabilir.")
        user_id = request.headers.get(DEV_USER_HEADER, DEFAULT_DEV_USER).strip().lower()
        if not _USER_ID.fullmatch(user_id):
            raise Unauthenticated("Geliştirici kullanıcı adı geçersiz.")
        raw_roles = request.headers.get(DEV_ROLES_HEADER)
        roles = frozenset(Role) if raw_roles is None else _parse_roles(raw_roles)
        return Principal(user_id=user_id, display_name=user_id, roles=roles, identity_source=self.source)


def _parse_roles(raw: str) -> frozenset[Role]:
    roles: set[Role] = set()
    for item in raw.split(","):
        name = item.strip().lower()
        if not name:
            continue
        try:
            roles.add(Role(name))
        except ValueError:
            raise Unauthenticated("Bilinmeyen geliştirici rolü.") from None
    return frozenset(roles)
