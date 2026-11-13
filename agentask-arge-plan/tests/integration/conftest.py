from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.support_lab import LabServer, start_lab


@pytest.fixture(scope="session")
def lab() -> Iterator[LabServer]:
    server = start_lab()
    yield server
    server.stop()
