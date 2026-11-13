"""Geliştirme başlatıcısı: LOCAL_MONGO_AUTOSTART=true ise yerel Mongo'yu hazır eder, sonra normal
uygulamayı başlatır.

false iken Docker yönetim modülleri import edilmez, Docker çağrılmaz; uygulama yapılandırılmış MONGO_URI
ile çalışır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentask.config import load_settings


def _resolve_env_file(env_file: Path | None) -> Path | None:
    if env_file is not None:
        return env_file
    default = Path(".env")
    return default if default.is_file() else None


def prepare(env_file: Path | None, runner: Any = None) -> Any:
    """Yönetilen proje (true) veya None (false). Uygulamayı başlatmaz."""
    env = _resolve_env_file(env_file)
    settings = load_settings(env)
    if not settings.local_mongo_autostart:
        return None
    from tools.local_mongo.manager import ensure_running  # yalnız açık modda yüklenir
    from tools.local_mongo.settings import load_tool_settings

    return ensure_running(settings, load_tool_settings(env), runner=runner)


def main(argv: list[str]) -> int:
    env_file = Path(argv[argv.index("--env-file") + 1]) if "--env-file" in argv else None
    from agentask.config import ConfigurationError

    try:
        prepare(env_file)
    except ConfigurationError as exc:
        print(str(exc))
        return 2
    except Exception as exc:  # araç hataları (Docker yok, port çakışması, URI uyumsuz) açıkça bildirilir
        print(f"Yerel MongoDB hazırlanamadı: {exc}")
        return 3
    from agentask.__main__ import main as app_main

    return app_main(argv)
