"""Teşhis: belirli süre sonra test ve sunucu döngülerindeki bekleyen asyncio görevlerinin yığını yazılır."""
import asyncio, os, traceback
import pytest
import tests.e2e.support as support
OUT = os.environ["DIAG_OUT"]
DELAY = float(os.environ.get("DIAG_DELAY", "180"))
_servers = []
_init = support.AppServer.__init__
def init(self, app):
    _init(self, app); _servers.append(self)
support.AppServer.__init__ = init

def _dump(title, loop):
    lines = [f"=== {title} ==="]
    for task in asyncio.all_tasks(loop):
        lines.append(f"--- görev {task.get_name()} ---")
        for frame in task.get_stack(limit=40):
            for entry in traceback.format_stack(frame, limit=1):
                if "site-packages" not in entry or "playwright/async_api/_generated" in entry:
                    lines.append(entry.rstrip())
        coro = task.get_coro()
        lines.append(f"    eşyordam: {getattr(coro, '__qualname__', coro)}")
    with open(OUT, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

@pytest.fixture(autouse=True)
async def _task_dump():
    loop = asyncio.get_running_loop()
    def fire():
        _dump("test döngüsü", loop)
        for s in _servers:
            s.loop.call_soon_threadsafe(_dump, "uygulama sunucusu döngüsü", s.loop)
    handle = loop.call_later(DELAY, fire)
    yield
    handle.cancel()
