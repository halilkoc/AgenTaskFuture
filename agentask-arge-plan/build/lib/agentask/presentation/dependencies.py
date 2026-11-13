from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from agentask.application.errors import Forbidden
from agentask.application.ports.identity import IdentityRequest
from agentask.bootstrap import Container
from agentask.domain.identity import Capability, Principal


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_principal(request: Request, container: ContainerDep) -> Principal:
    identity_request = IdentityRequest(
        client_host=request.client.host if request.client else None,
        headers={key.lower(): value for key, value in request.headers.items()},
    )
    return await container.identity.authenticate(identity_request)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(capability: Capability) -> Callable[[Principal], Awaitable[Principal]]:
    async def _check(principal: PrincipalDep) -> Principal:
        if not principal.can(capability):
            raise Forbidden()
        return principal

    return _check
