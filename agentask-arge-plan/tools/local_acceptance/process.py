"""Süre sınırlı alt süreç. Süre dolarsa yalnız bu çağrının başlattığı süreç grubu sonlandırılır."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from pathlib import Path

TIMEOUT = "zaman_asimi"


def run_limited(
    command: list[str], cwd: Path, env: Mapping[str, str] | None, log: Path, timeout_s: float
) -> int | str:
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # kendi süreç grubu: geçici mongod ve tarayıcılar da onunla biter
        )
        try:
            return proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return TIMEOUT
