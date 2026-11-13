"""E2E yardımcıları: ana uygulamayı gerçek HTTP sunucusu olarak arka plan thread'inde çalıştırır."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

import uvicorn

from tests.support_lab import free_port


class AppServer:
    def __init__(self, app: Any) -> None:
        self.port = free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None, log_level="warning")
        )
        self.loop: asyncio.AbstractEventLoop | None = None
        self.app = app

    def start(self) -> None:
        ready = threading.Event()

        def run() -> None:
            async def main() -> None:
                self.loop = asyncio.get_running_loop()
                task = asyncio.create_task(self.server.serve())
                while not self.server.started:
                    await asyncio.sleep(0.01)
                ready.set()
                await task

            asyncio.run(main())

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        assert ready.wait(10)

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        assert self.loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(15)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(15)
