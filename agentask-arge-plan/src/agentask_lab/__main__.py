"""`agentask-lab [--env-file PATH]`: deney uygulamasını LAB_* origin'lerinde başlatır."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agentask.config import ConfigurationError, load_settings
from agentask.infrastructure.logging import configure_logging
from agentask_lab.server import serve
from agentask_lab.state import LabState


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentask-lab", description="Yerel deney uygulaması (gerçek Pega değil)"
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if settings.lab_primary_origin is None or settings.lab_secondary_origin is None:
        print("LAB_PRIMARY_ORIGIN ve LAB_SECONDARY_ORIGIN ayarlanmalı.", file=sys.stderr)
        return 2
    print(f"Deney uygulaması: {settings.lab_primary_origin} (ikincil: {settings.lab_secondary_origin})")
    print(f"Kontrol paneli: {settings.lab_primary_origin}/__lab")
    if args.check_config:
        return 0
    configure_logging(settings.log_level, settings.log_format)
    asyncio.run(serve(LabState(), settings.lab_primary_origin, settings.lab_secondary_origin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
