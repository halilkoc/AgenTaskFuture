"""Docker Compose CLI sarmalayıcısı. shell kullanılmaz; argümanlar liste olarak verilir.

Veri silen komut (down -v, volume rm, rm) bu modülde YOKTUR. Durdurma 'stop' ile yapılır; volume korunur.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.local_mongo.settings import LocalMongoSettings

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "compose.local-mongo.yml"
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ComposeError(RuntimeError):
    pass


class ComposeProject:
    def __init__(
        self, settings: LocalMongoSettings, runner: Runner = subprocess.run, compose_file: Path = COMPOSE_FILE
    ) -> None:
        self._settings = settings
        self._run = runner
        self._file = compose_file

    def _env(self) -> dict[str, str]:
        # Compose değişkenleri yalnız bu alt süreçe verilir (PATH/HOME/DOCKER_* gibi CLI ortamı korunur).
        env = dict(os.environ)
        s = self._settings
        env.update(
            {
                "LOCAL_MONGO_IMAGE": s.image,
                "LOCAL_MONGO_PORT": str(s.port),
                "LOCAL_MONGO_VOLUME": s.volume,
                "LOCAL_MONGO_ROOT_USERNAME": s.root_username or "",
                "LOCAL_MONGO_ROOT_PASSWORD": s.root_password.get_secret_value() if s.root_password else "",
            }
        )
        return env

    def _compose(self, *args: str, check: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd = ["docker", "compose", "-p", self._settings.project, "-f", str(self._file), *args]
        try:
            result = self._run(cmd, env=self._env(), capture_output=True, text=True, check=False, **kwargs)
        except FileNotFoundError:
            raise ComposeError(
                "docker komutu bulunamadı (LOCAL_MONGO_AUTOSTART=true için Docker gerekir)."
            ) from None
        if check and result.returncode != 0:
            raise ComposeError(f"docker compose {args[0]} başarısız (çıkış {result.returncode}).")
        return result

    def is_running(self) -> bool:
        result = self._compose("ps", "--format", "json", "mongo", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return False
        lines = [
            json.loads(line) for line in result.stdout.strip().splitlines() if line.strip().startswith("{")
        ]
        return any(item.get("State") == "running" for item in lines)

    def up(self) -> None:
        self._compose("up", "-d", "mongo")

    def stop(self) -> None:
        self._compose("stop")

    def exec_to_file(self, args: list[str], target: Path) -> None:
        with open(target, "wb") as handle:
            cmd = [
                "docker",
                "compose",
                "-p",
                self._settings.project,
                "-f",
                str(self._file),
                "exec",
                "-T",
                "mongo",
                *args,
            ]
            result = self._run(cmd, env=self._env(), stdout=handle, check=False)
        if result.returncode != 0:
            raise ComposeError("yedekleme komutu başarısız.")

    def exec_from_file(self, args: list[str], source: Path) -> None:
        with open(source, "rb") as handle:
            cmd = [
                "docker",
                "compose",
                "-p",
                self._settings.project,
                "-f",
                str(self._file),
                "exec",
                "-T",
                "mongo",
                *args,
            ]
            result = self._run(cmd, env=self._env(), stdin=handle, check=False)
        if result.returncode != 0:
            raise ComposeError("geri yükleme komutu başarısız.")
