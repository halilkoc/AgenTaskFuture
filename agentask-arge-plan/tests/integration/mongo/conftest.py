from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Iterator

import pytest

from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from tests.support_mongo import ephemeral_mongod


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with ephemeral_mongod() as uri:
        if uri is None:
            pytest.skip("BLOCKED: mongod bulunamadı; gerçek MongoDB entegrasyon testi çalıştırılamadı")
        yield uri


@pytest.fixture
async def store(mongo_uri: str) -> AsyncIterator[MongoCatalogStore]:
    instance = MongoCatalogStore(mongo_uri, f"agentask_test_{secrets.token_hex(4)}", 3000)
    await instance.ensure_schema()
    yield instance
    await instance.close()
