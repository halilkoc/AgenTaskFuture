"""Kullanım: python -m tools.local_mongo {dev|up|stop|status|backup|restore} [--env-file PATH] ...

dev     : LOCAL_MONGO_AUTOSTART'a göre Mongo'yu hazır eder ve uygulamayı başlatır (agentask ile aynı
argümanlar)
up      : yalnız yerel Mongo'yu hazır eder (veri korunur)
stop    : yerel Mongo'yu durdurur (volume ve veri SİLİNMEZ)
status  : container durumu
backup  : LOCAL_MONGO_BACKUP_DIR altına mongodump arşivi
restore ARŞİV HEDEF_DB : arşivi AYRI bir veritabanına geri yükler
"""

from __future__ import annotations

import sys
from pathlib import Path


def _env(argv: list[str]) -> Path | None:
    if "--env-file" in argv:
        return Path(argv[argv.index("--env-file") + 1])
    return Path(".env") if Path(".env").is_file() else None


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    if command == "dev":
        from tools.local_mongo.launcher import main as launcher_main

        return launcher_main(rest)
    from agentask.config import ConfigurationError
    from tools.local_mongo.compose import ComposeError
    from tools.local_mongo.manager import ManagedMongoError
    from tools.local_mongo.settings import ToolConfigurationError

    try:
        return _run(command, rest)
    except (ConfigurationError, ToolConfigurationError, ManagedMongoError, ComposeError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 3


def _run(command: str, rest: list[str]) -> int:
    from agentask.config import load_settings
    from tools.local_mongo.compose import ComposeProject
    from tools.local_mongo.manager import backup, ensure_running, restore
    from tools.local_mongo.settings import load_tool_settings

    env = _env(rest)
    settings, tool = load_settings(env), load_tool_settings(env)
    if settings.app_env.value != "development":
        print("Yerel Mongo aracı yalnız APP_ENV=development ile kullanılabilir.")
        return 2
    project = ComposeProject(tool)
    if command == "up":
        ensure_running(settings, tool)
        print("Yerel MongoDB hazır.")
    elif command == "stop":
        project.stop()
        print("Yerel MongoDB durduruldu (veri korunur).")
    elif command == "status":
        print("çalışıyor" if project.is_running() else "çalışmıyor")
    elif command == "backup":
        print(f"Yedek: {backup(settings, project, tool.backup_dir)}")
    elif command == "restore":
        positional = [a for a in rest if not a.startswith("--") and a != str(env)]
        restore(settings, project, Path(positional[0]), positional[1])
        print(f"Geri yüklendi: {positional[1]}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
