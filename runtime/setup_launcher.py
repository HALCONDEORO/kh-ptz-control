#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Launch the graphical first-run/repair setup wizard.

On product Raspberry Pi installs the wizard also opens once for older provisioned
rooms that do not yet have the integrated display/autostart marker. That gives
upgrades a guided migration path instead of silently keeping the years-old
controller startup.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from runtime.path_resolver import RuntimePathResolver


def setup_wizard_needed(
    resolver: Optional[RuntimePathResolver] = None,
    *,
    force: bool = False,
) -> bool:
    """Return True when first-run, repair, or Pi integration migration is needed."""
    if force:
        return True
    resolver = resolver or RuntimePathResolver()
    if not resolver.provisioned_marker_file.exists():
        return True

    # Existing tests/dev installs use an overridden config directory and do not
    # install systemd/display integration. Restrict this migration gate to the
    # canonical product path so their historical provisioned guard stays intact.
    if resolver.config_dir == Path("/etc/khptz"):
        marker = getattr(
            resolver,
            "rpi_integration_marker_file",
            resolver.config_dir / ".rpi-integrated",
        )
        return not Path(marker).exists()
    return False


def run_setup_wizard(
    wizard_factory: Optional[Callable[[], object]] = None,
    *,
    answers: object = None,
    require_admin_auth: bool = False,
) -> int:
    """Open the wizard and block until it closes; return a process exit code.

    0 = wizard completed (accepted), 1 = cancelled or closed. ``answers``
    pre-fills the pages (Repair/migration mode). ``require_admin_auth`` inserts
    the admin sign-in page before protected changes are allowed.
    """
    import sys

    from PyQt5.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    if wizard_factory is None:
        from ui.setup_wizard.wizard import SetupWizard
        wizard_factory = lambda: SetupWizard(  # noqa: E731
            answers=answers, require_admin_auth=require_admin_auth
        )

    wizard = wizard_factory()
    result = wizard.exec_()
    return 0 if result == QDialog.Accepted else 1
