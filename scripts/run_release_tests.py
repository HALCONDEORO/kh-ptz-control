#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Hardware-free release tests; full mode uses CI's Qt isolation partition."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UNFORKED = frozenset({
    "test_login_countdown_integration.py", "test_setup_wizard.py",
    "test_setup_wizard_rpi_pages.py", "test_sim_debug_panel.py",
    "test_digital_joystick.py", "test_main_window_smoke.py",
})
FOCUSED = (
    "test_startup_smoke.py", "test_app_context.py", "test_main_startup.py",
    "test_atomic_write*.py", "test_json_io*.py", "test_persistence*.py",
    "test_json_recovery*.py", "test_restore*.py", "test_backup*.py",
    "test_legacy_restore*.py",
)


def partition(root: Path, *, full: bool = False):
    files = sorted((root / "tests").rglob("test_*.py"))
    if not full:
        files = [p for p in files if any(p.match(pattern) for pattern in FOCUSED)]
    unforked = [p for p in files if p.name in UNFORKED or p.match("test_config_pages_*.py")]
    return [p for p in files if p not in unforked], unforked


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    groups = partition(ROOT, full=args.full)
    if not any(groups):
        raise SystemExit("No release tests selected")
    for index, paths in enumerate(groups):
        if paths:
            cmd = [sys.executable, "-m", "pytest"]
            if index == 0:
                cmd.append("--forked")
            cmd.extend(str(p.relative_to(ROOT)) for p in paths)
            subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
