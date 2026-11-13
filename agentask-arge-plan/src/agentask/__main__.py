"""Bootstrap: `agentask [--env-file PATH]`. Tek worker zorunludur (bellek içi session kilidi)."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import uvicorn

from agentask.config import ConfigurationError, load_settings
from agentask.diagnostics import run_doctor
from agentask.domain.passwords import MIN_PASSWORD_LENGTH, hash_password
from agentask.infrastructure.logging import configure_logging
from agentask.presentation.app import create_app


def _hash_admin_password() -> int:
    """Parola komut satırından alınmaz (geçmişe/süreç listesine düşmesin); yalnız hash yazdırılır."""
    password = getpass.getpass("Parola: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Parola en az {MIN_PASSWORD_LENGTH} karakter olmalı.", file=sys.stderr)
        return 2
    if password != getpass.getpass("Parola (tekrar): "):
        print("Parolalar aynı değil.", file=sys.stderr)
        return 2
    print(hash_password(password))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentask")
    parser.add_argument("--env-file", type=Path, default=None, help="Varsayılan: çalışma dizinindeki .env")
    parser.add_argument("--check-config", action="store_true", help="Yalnızca ayarları doğrula ve çık")
    parser.add_argument("--doctor", action="store_true", help="Kurulum ve bağlantı ön kontrolü")
    parser.add_argument(
        "--hash-admin-password",
        action="store_true",
        help="Geçici admin parolası için hash üret (ayar okumaz)",
    )
    args = parser.parse_args(argv)
    if args.hash_admin_password:
        return _hash_admin_password()
    try:
        settings = load_settings(args.env_file)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.check_config:
        print("Yapılandırma geçerli.")
        return 0
    if args.doctor:
        return run_doctor(settings)
    configure_logging(settings.log_level, settings.log_format)
    try:
        app = create_app(settings)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
        log_config=None,
        access_log=False,  # istek logu sorgu dizgisi içermeyen uygulama ara katmanındadır
        server_header=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
