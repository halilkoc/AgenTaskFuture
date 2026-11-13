"""Bootstrap: `agentask [--env-file PATH]`. Tek worker zorunludur (bellek içi session kilidi)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from agentask.config import ConfigurationError, load_settings
from agentask.infrastructure.logging import configure_logging
from agentask.presentation.app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentask")
    parser.add_argument("--env-file", type=Path, default=None, help="Varsayılan: çalışma dizinindeki .env")
    parser.add_argument("--check-config", action="store_true", help="Yalnızca ayarları doğrula ve çık")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.check_config:
        print("Yapılandırma geçerli.")
        return 0
    configure_logging(settings.log_level, settings.log_format)
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
        log_config=None,
        server_header=False,
        proxy_headers=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
