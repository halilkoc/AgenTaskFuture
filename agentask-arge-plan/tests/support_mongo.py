"""Geçici yerel mongod (scratch dbpath, rastgele port). mongod yoksa testler BLOCKED nedeniyle atlanır."""

from __future__ import annotations

import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@contextmanager
def ephemeral_mongod() -> Iterator[str | None]:
    binary = shutil.which("mongod")
    if binary is None:
        yield None
        return
    dbpath = tempfile.mkdtemp(prefix="agentask-mongo-")
    port = _free_port()
    proc = subprocess.Popen(  # noqa: S603 - sabit argümanlarla yerel test süreci
        [
            binary,
            "--dbpath",
            dbpath,
            "--port",
            str(port),
            "--bind_ip",
            "127.0.0.1",
            "--quiet",
            "--nounixsocket",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError("mongod başlatılamadı")
        yield f"mongodb://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(dbpath, ignore_errors=True)
