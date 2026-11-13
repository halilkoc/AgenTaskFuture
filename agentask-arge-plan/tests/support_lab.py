"""Test yardımcıları: deney uygulamasını arka plan thread'inde gerçek HTTP sunucusu olarak çalıştırır."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import uvicorn

from agentask_lab.server import build_servers
from agentask_lab.state import LabState


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@dataclass
class LabServer:
    primary: str
    secondary: str
    state: LabState
    _servers: list[uvicorn.Server] = field(default_factory=list)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        ready = threading.Event()

        def _run() -> None:
            async def _main() -> None:
                self._servers = build_servers(self.state, self.primary, self.secondary)
                serving = [asyncio.create_task(s.serve()) for s in self._servers]
                while not all(s.started for s in self._servers):
                    await asyncio.sleep(0.01)
                ready.set()
                await asyncio.gather(*serving)

            asyncio.run(_main())

        self._thread = threading.Thread(target=_run, name="lab-server", daemon=True)
        self._thread.start()
        if not ready.wait(10):
            raise RuntimeError("Deney uygulaması başlatılamadı")

    def stop(self) -> None:
        for server in self._servers:
            server.should_exit = True
        if self._thread is not None:
            self._thread.join(10)

    def control(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return httpx.request(method, f"{self.primary}{path}", timeout=10, **kwargs)

    def set_scenario(self, **values: Any) -> None:
        response = self.control("PUT", "/__lab/scenario", json=values)
        response.raise_for_status()

    def reset(self) -> None:
        self.control("POST", "/__lab/reset").raise_for_status()


def start_lab() -> LabServer:
    lab = LabServer(
        primary=f"http://127.0.0.1:{free_port()}",
        secondary=f"http://127.0.0.1:{free_port()}",
        state=LabState(),
    )
    lab.start()
    return lab


def wait_until(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("koşul zaman aşımında sağlanmadı")


class HitCounterServer:
    """İzinli olmayan bir origin'i temsil eder; gelen her isteği sayar."""

    def __init__(self) -> None:
        import http.server

        hits: list[str] = []
        self.hits = hits

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<p>izinsiz</p>")

            def log_message(self, *args: Any) -> None:
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.origin = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
