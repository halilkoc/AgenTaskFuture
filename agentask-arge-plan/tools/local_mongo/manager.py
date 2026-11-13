"""Yönetilen yerel Mongo: bağlantının yerel servise karşılık geldiğini doğrular, hazır eder,
yedekler/geri yükler.

Uzak/başka servise ait bağlantıda hiçbir Docker komutu çalıştırılmaz. URI sessizce değiştirilmez. Port
başka bir
servis tarafından kullanılıyorsa o servise dokunulmaz, açık hata verilir. Veri silinmez.
"""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from agentask.config.settings import Settings
from tools.local_mongo.compose import ComposeProject, Runner
from tools.local_mongo.settings import LocalMongoSettings


class ManagedMongoError(RuntimeError):
    pass


def check_uri_matches(settings: Settings, tool: LocalMongoSettings) -> None:
    uri = settings.mongo_uri.get_secret_value()
    parts = urlsplit(uri)
    if parts.scheme != "mongodb":
        raise ManagedMongoError(
            "Otomatik yönetim yalnız yerel mongodb:// servisi içindir; MONGO_URI yerel değil."
        )
    hosts = parts.netloc.rsplit("@", 1)[-1].split(",")
    if len(hosts) != 1:
        raise ManagedMongoError(
            "Otomatik yönetim tek yerel sunucu içindir; MONGO_URI birden fazla sunucu içeriyor."
        )
    host, _, port = hosts[0].partition(":")
    if host not in {"127.0.0.1", "localhost"}:
        raise ManagedMongoError("MONGO_URI yerel servisi göstermiyor; uzak/başka servis otomatik yönetilmez.")
    if int(port or 27017) != tool.port:
        raise ManagedMongoError(
            f"MONGO_URI portu LOCAL_MONGO_PORT ({tool.port}) ile uyuşmuyor; URI değiştirilmedi."
        )
    user = unquote(parts.username) if parts.username else None
    if (tool.root_username is None) != (user is None) or (user is not None and user != tool.root_username):
        raise ManagedMongoError(
            "MONGO_URI kimlik bilgisi yerel servis ayarıyla uyuşmuyor (kullanıcı/kimlik doğrulama)."
        )


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ping(settings: Settings, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            client: MongoClient[dict[str, object]]
            with MongoClient(settings.mongo_uri.get_secret_value(), serverSelectionTimeoutMS=1500) as client:
                client.admin.command("ping")
                return True
        except PyMongoError:
            time.sleep(0.5)
    return False


def ensure_running(
    settings: Settings, tool: LocalMongoSettings, runner: Runner | None = None
) -> ComposeProject:
    check_uri_matches(settings, tool)
    project = ComposeProject(tool, runner=runner) if runner is not None else ComposeProject(tool)
    if not project.is_running():
        if _port_open(tool.port):
            raise ManagedMongoError(
                f"127.0.0.1:{tool.port} başka bir servis tarafından kullanılıyor; o servise "
                "dokunulmadı. LOCAL_MONGO_PORT ve MONGO_URI'yi boş bir porta ayarlayın."
            )
        project.up()  # mevcut container/volume varsa yeniden kullanılır; veri sıfırlanmaz
    if not ping(settings, tool.start_timeout_seconds):
        raise ManagedMongoError("Yerel MongoDB süre içinde yanıt vermedi (ping).")
    return project


def backup(settings: Settings, project: ComposeProject, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{settings.mongo_database}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.archive.gz"
    project.exec_to_file(["mongodump", "--archive", "--gzip", f"--db={settings.mongo_database}"], target)
    return target


def restore(settings: Settings, project: ComposeProject, archive: Path, target_db: str) -> None:
    """Yalnız AYRI bir veritabanına geri yükler (ana katalog ezilmez)."""
    if target_db == settings.mongo_database:
        raise ManagedMongoError(
            "Geri yükleme ana katalog veritabanına yapılamaz; ayrı bir test veritabanı verin."
        )
    project.exec_from_file(
        [
            "mongorestore",
            "--archive",
            "--gzip",
            f"--nsFrom={settings.mongo_database}.*",
            f"--nsTo={target_db}.*",
        ],
        archive,
    )
