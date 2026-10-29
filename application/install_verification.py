#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Post-provision verification shown on the wizard's final screen."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from runtime.path_resolver import RuntimePathResolver


@dataclass(frozen=True)
class InstallVerdict:
    """Result of the independent post-provision verification."""
    ok: bool
    checks: List[Tuple[str, bool]]
    advisories: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            text = "The room is installed and verified."
            if self.advisories:
                text += "\nAdvisories:\n" + "\n".join(
                    f"• {item}" for item in self.advisories
                )
            return text
        failed = [label for label, passed in self.checks if not passed]
        return "Setup finished but verification failed: " + ", ".join(failed)


def _read_advisories(path: Path = Path("/run/hallptz/rpi-advisories.json")) -> List[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        values = raw.get("advisories", [])
        return [str(value) for value in values if str(value).strip()]
    except Exception:
        return []


def _launcher_checks() -> List[Tuple[str, bool]]:
    """Verify the launcher that this install actually has (#885).

    Which files must exist depends on who owns the GUI, and asserting the wrong
    set is not a cosmetic mismatch — it is the difference between the wizard's
    final screen saying "installed and verified" and "verification failed" on a
    healthy appliance.

    Under ``--gui-mode user`` scripts/repair_rpi_runtime.sh deliberately skips
    the whole display-ready chain ("the session owns its own display"), so
    /run/hallptz/display-ready is never written. Demanding it there made the Done
    page report failure on *every* session-owned install. Verify that mode's
    real launcher instead: the user unit, its session helper, and the autostart
    entry that actually starts it at login. hallptz-control.service is deliberately
    absent from that list — it is disabled in this mode by design.
    """
    from runtime.install_state import gui_is_session_owned

    try:
        session_owned = gui_is_session_owned()
    except Exception:  # noqa: BLE001 — never fail verification over this
        session_owned = False

    if session_owned:
        # The autostart entry is what actually starts the unit at login, and
        # this process is the desktop user, so its own home is exactly the
        # right place to look.
        autostart = Path.home() / ".config" / "autostart" / "hallptz-gui.desktop"
        return [
            ("Session GUI unit", Path("/etc/systemd/user/hallptz-gui.service").exists()),
            ("Session GUI launcher", Path("/usr/local/libexec/hallptz-gui-session").exists()),
            ("Session GUI autostart", autostart.exists()),
        ]
    return [
        ("Desktop display handoff", Path("/run/hallptz/display-ready").exists()),
        ("HALLPTZ service unit", Path("/etc/systemd/system/hallptz-control.service").exists()),
        ("Display-ready path unit", Path("/etc/systemd/system/hallptz-display-ready.path").exists()),
    ]


def verify_provisioned(
    resolver: Optional[RuntimePathResolver] = None,
) -> InstallVerdict:
    """Confirm core files and, on a product Pi, the display/startup integration."""
    r = resolver or RuntimePathResolver()
    checks = [
        ("Provisioned marker", r.provisioned_marker_file.exists()),
        ("Configuration file", (r.config_dir / "config.yaml").exists()),
    ]

    # Unit tests and source/dev environments use overridden temporary paths. The
    # extra checks are product-only because their canonical files live in /etc and
    # /run and are created by the integrated Raspberry Pi provisioning wrapper.
    if r.config_dir == Path("/etc/hallptz"):
        checks.append(
            ("Raspberry Pi integration marker", (r.config_dir / ".rpi-integrated").exists())
        )
        checks.extend(_launcher_checks())

    return InstallVerdict(
        ok=all(passed for _, passed in checks),
        checks=checks,
        advisories=_read_advisories(),
    )
