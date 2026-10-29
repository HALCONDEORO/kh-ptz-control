#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Raspberry Pi setup advisories shared by the wizard and installer checks."""
from __future__ import annotations

import locale
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

# Fixed location of the X server's UNIX domain sockets (X11 spec, not a tempdir).
_X11_SOCKET_DIR = "/tmp/.X11-unix"  # nosec B108


@dataclass(frozen=True)
class RpiSetupAdvisory:
    key: str
    label: str
    ok: bool
    blocking: bool
    detail: str
    remediation: str = ""

    @property
    def warn_only(self) -> bool:
        return not self.ok and not self.blocking


def check_utf8(encoding: Optional[str] = None) -> RpiSetupAdvisory:
    current = encoding or locale.getpreferredencoding(False) or "unknown"
    if "UTF-8" in current.upper().replace("_", "-"):
        return RpiSetupAdvisory(
            "utf8", "Terminal encoding", True, False, f"{current} — UTF-8"
        )
    return RpiSetupAdvisory(
        "utf8",
        "Terminal encoding",
        False,
        False,
        f"{current} may crash diagnostics when they print Unicode characters",
        "Setup will force C.UTF-8 for HALLPTZ; use a UTF-8 desktop locale as well.",
    )


def check_display(
    display: Optional[str] = None,
    *,
    x11_socket_exists: Optional[bool] = None,
) -> RpiSetupAdvisory:
    value = display if display is not None else os.environ.get("DISPLAY", "")
    if x11_socket_exists is None:
        display_number = "0"
        match = re.match(r"^:(\d+)", value or "")
        if match:
            display_number = match.group(1)
        # Existence check only: nothing is read from or written to the path.
        socket_path = Path(_X11_SOCKET_DIR) / f"X{display_number}"
        x11_socket_exists = socket_path.exists()
    if value and x11_socket_exists:
        return RpiSetupAdvisory(
            "display",
            "Desktop display",
            True,
            False,
            f"DISPLAY={value}; X11 socket is available",
        )
    return RpiSetupAdvisory(
        "display",
        "Desktop display",
        False,
        False,
        f"DISPLAY={value or '<unset>'}; X11 socket was not confirmed",
        "Keep the Pi desktop session open. Setup will install scoped display access.",
    )


def check_xhost(available: Optional[bool] = None) -> RpiSetupAdvisory:
    found = shutil.which("xhost") is not None if available is None else available
    if found:
        return RpiSetupAdvisory(
            "xhost", "Display authorization", True, False, "xhost is available"
        )
    return RpiSetupAdvisory(
        "xhost",
        "Display authorization",
        False,
        False,
        "xhost is missing; the service cannot be granted scoped access to the desktop",
        "Setup installs x11-xserver-utils automatically.",
    )


def check_raspberry_pi_os(
    os_release: Optional[Mapping[str, str]] = None,
) -> RpiSetupAdvisory:
    values = dict(_read_os_release() if os_release is None else os_release)
    pretty = values.get("PRETTY_NAME", "Unknown Linux")
    combined = " ".join(values.values()).lower()
    if "raspberry pi os" in combined and (
        "bullseye" in combined or values.get("VERSION_ID") == "11"
    ):
        return RpiSetupAdvisory("os", "Operating system", True, False, pretty)
    return RpiSetupAdvisory(
        "os",
        "Operating system",
        False,
        False,
        f"{pretty} is not the validated Raspberry Pi OS Bullseye baseline",
        "Continue only for testing; production validation targets Raspberry Pi OS Bullseye.",
    )


def _active_startup_text(path: Path, text: str) -> str:
    """Return only active startup content, ignoring our reversible quarantine."""
    if ".disabled-by-hallptz-" in path.name:
        return ""
    active_lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith("#") or stripped.startswith(";"):
            continue
        active_lines.append(raw_line)
    return "\n".join(active_lines)


def check_legacy_autostart(
    home: Optional[Path] = None,
    *,
    entries: Optional[Iterable[str]] = None,
) -> RpiSetupAdvisory:
    patterns = re.compile(
        r"dublin[ _-]?isl|hallptz_controls|ptz[ _-]?(control|controller)|camera[ _-]?controller",
        re.IGNORECASE,
    )
    candidates: List[str] = []
    if entries is not None:
        candidates = [str(item) for item in entries]
    else:
        root = home or Path.home()
        locations = [
            root / ".config" / "autostart",
            root / ".config" / "lxsession",
            root / ".config" / "openbox",
            root / ".config" / "labwc",
            root / ".config" / "systemd" / "user",
            Path("/etc/xdg/autostart"),
            Path("/etc/xdg/lxsession"),
            Path("/etc/xdg/openbox"),
            Path("/etc/xdg/labwc"),
            Path("/etc/systemd/system"),
        ]
        files = [Path("/etc/rc.local"), Path("/etc/wayfire.ini")]
        for location in locations:
            if not location.exists():
                continue
            for path in location.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                active = _active_startup_text(path, text)
                if active:
                    candidates.append(f"{path}\n{active}")
        for path in files:
            if not path.is_file():
                continue
            try:
                active = _active_startup_text(
                    path,
                    path.read_text(encoding="utf-8", errors="replace"),
                )
            except OSError:
                continue
            if active:
                candidates.append(f"{path}\n{active}")
    matched = [item for item in candidates if patterns.search(item)]
    if not matched:
        return RpiSetupAdvisory(
            "legacy_autostart",
            "Previous controller",
            True,
            False,
            "No recognised legacy PTZ startup was found",
        )
    suffix = "entry" if len(matched) == 1 else "entries"
    return RpiSetupAdvisory(
        "legacy_autostart",
        "Previous controller",
        False,
        False,
        f"Found {len(matched)} possible legacy startup {suffix}",
        "Setup will back them up, disable them and install the canonical HALLPTZ startup chain.",
    )


def collect_rpi_setup_advisories() -> List[RpiSetupAdvisory]:
    return [
        check_raspberry_pi_os(),
        check_utf8(),
        check_display(),
        check_xhost(),
        check_legacy_autostart(),
    ]


def _read_os_release(path: Path = Path("/etc/os-release")) -> Mapping[str, str]:
    values = {}
    try:
        for raw_line in path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values
