"""İki origin'i (birincil + ikincil) tek process'te, ortak LabState ile servis eder."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Iterator
from urllib.parse import urlsplit

import uvicorn

from agentask_lab.app import create_lab_app
from agentask_lab.state import LabState


class _LabServer(uvicorn.Server):
    """Sinyalleri tek tek sunucular değil serve() yakalar; Ctrl+C iki origin'i birlikte kapatır."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _host_port(origin: str) -> tuple[str, int]:
    parts = urlsplit(origin)
    if parts.hostname is None or parts.port is None:
        raise ValueError("lab origin'i açık port içermeli")
    return parts.hostname, parts.port


def build_servers(state: LabState, primary_origin: str, secondary_origin: str) -> list[uvicorn.Server]:
    app = create_lab_app(state, primary_origin, secondary_origin)
    servers: list[uvicorn.Server] = []
    for origin in (primary_origin, secondary_origin):
        host, port = _host_port(origin)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            log_config=None,
            timeout_graceful_shutdown=1,
            server_header=False,
        )
        servers.append(_LabServer(config))
    return servers


async def serve(state: LabState, primary_origin: str, secondary_origin: str) -> None:
    servers: list[uvicorn.Server] = build_servers(state, primary_origin, secondary_origin)
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        for server in servers:
            server.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)
    tasks = [asyncio.create_task(s.serve()) for s in servers]
    try:
        await asyncio.gather(*tasks)
    finally:
        for server in servers:
            server.should_exit = True
