from __future__ import annotations

import pytest

from agentask.application.errors import Forbidden, Unauthenticated
from agentask.application.ports.identity import IdentityRequest
from agentask.domain.identity import Capability, Role
from agentask.infrastructure.identity.dev import DevIdentity


async def test_dev_identity_rejects_non_loopback_client() -> None:
    with pytest.raises(Forbidden):
        await DevIdentity().authenticate(IdentityRequest(client_host="10.1.2.3"))


async def test_dev_identity_rejects_missing_client() -> None:
    with pytest.raises(Forbidden):
        await DevIdentity().authenticate(IdentityRequest(client_host=None))


async def test_dev_identity_reads_user_and_roles() -> None:
    principal = await DevIdentity().authenticate(
        IdentityRequest(client_host="127.0.0.1", headers={"x-dev-user": "Ayse", "x-dev-roles": "operator"})
    )
    assert principal.user_id == "ayse"
    assert principal.roles == frozenset({Role.OPERATOR})
    assert principal.can(Capability.USE_ASSISTANT)
    assert not principal.can(Capability.DESIGN_CATALOG)
    assert not principal.can(Capability.PUBLISH_CATALOG)


@pytest.mark.parametrize("headers", [{"x-dev-roles": "admin"}, {"x-dev-user": "../etc"}])
async def test_dev_identity_rejects_invalid_input(headers: dict[str, str]) -> None:
    with pytest.raises(Unauthenticated):
        await DevIdentity().authenticate(IdentityRequest(client_host="::1", headers=headers))


async def test_empty_role_list_grants_nothing() -> None:
    principal = await DevIdentity().authenticate(
        IdentityRequest(client_host="127.0.0.1", headers={"x-dev-roles": ""})
    )
    assert principal.capabilities == frozenset()
