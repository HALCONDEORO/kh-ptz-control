#!/usr/bin/env python3
"""Pure tests for Raspberry Pi setup advisories."""
from pathlib import Path

from application.rpi_runtime_readiness import (
    check_display,
    check_legacy_autostart,
    check_raspberry_pi_os,
    check_utf8,
    check_xhost,
)


def test_utf8_passes_and_legacy_encoding_warns():
    assert check_utf8("UTF-8").ok
    legacy = check_utf8("ISO-8859-15")
    assert not legacy.ok and legacy.warn_only
    assert "Unicode" in legacy.detail


def test_display_requires_value_and_socket():
    assert check_display(":0", x11_socket_exists=True).ok
    missing = check_display("", x11_socket_exists=False)
    assert not missing.ok and not missing.blocking


def test_xhost_missing_is_repairable_warning():
    check = check_xhost(False)
    assert not check.ok and check.warn_only
    assert "x11-xserver-utils" in check.remediation


def test_validated_os_passes_other_linux_warns():
    assert check_raspberry_pi_os({
        "PRETTY_NAME": "Raspberry Pi OS Bullseye",
        "VERSION_ID": "11",
    }).ok
    assert not check_raspberry_pi_os({
        "PRETTY_NAME": "Ubuntu",
        "VERSION_ID": "24.04",
    }).ok


def test_legacy_autostart_detection_is_conservative():
    clean = check_legacy_autostart(entries=["Exec=nm-applet"])
    assert clean.ok
    old = check_legacy_autostart(entries=[
        "Exec=/usr/bin/python3 /home/hallptz/hallptz-control/main.py"
    ])
    assert not old.ok
    assert "disable" in old.remediation


def test_commented_and_quarantined_entries_are_not_active(tmp_path: Path):
    autostart = tmp_path / ".config" / "autostart"
    autostart.mkdir(parents=True)
    (autostart / "old.desktop.disabled-by-hallptz-20260722").write_text(
        "Exec=/home/hallptz/hallptz-control/main.py\n", encoding="utf-8"
    )
    openbox = tmp_path / ".config" / "openbox"
    openbox.mkdir(parents=True)
    (openbox / "autostart").write_text(
        "# disabled: /home/hallptz/hallptz-control/main.py\n",
        encoding="utf-8",
    )
    assert check_legacy_autostart(home=tmp_path).ok

