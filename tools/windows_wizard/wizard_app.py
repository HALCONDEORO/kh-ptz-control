# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import WIZARD_NAME, WIZARD_VERSION
from .paths import ensure_state_dirs


def _configure_logging(state_dir: Path) -> Path:
    log_path = state_dir / "logs" / "wizard.log"
    logger = logging.getLogger("windows_wizard")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return log_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hallptz-windows-wizard",
        description="HALLPTZ technician provisioning wizard skeleton",
    )
    parser.add_argument("--state-dir", type=Path, default=None, help="Override local wizard state directory")
    parser.add_argument("--version", action="store_true", help="Print wizard version")
    parser.add_argument("--smoke", action="store_true", help="Run a no-hardware startup smoke check")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"{WIZARD_NAME} {WIZARD_VERSION}")
        return 0

    state_dir = ensure_state_dirs(args.state_dir)
    log_path = _configure_logging(state_dir)
    logger = logging.getLogger("windows_wizard")
    logger.info("Wizard started: version=%s state_dir=%s", WIZARD_VERSION, state_dir)

    if args.smoke:
        print(f"{WIZARD_NAME} smoke OK")
        print(f"state_dir={state_dir}")
        print(f"log={log_path}")
        return 0

    print(f"{WIZARD_NAME} {WIZARD_VERSION}")
    print("Skeleton ready. SSH/install/update flows are intentionally not implemented yet.")
    print(f"Local state: {state_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

