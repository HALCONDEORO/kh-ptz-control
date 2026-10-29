#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.

from __future__ import annotations

import subprocess

import adapters.power_management as power_management


def test_disable_screen_blanking_skips_non_linux(monkeypatch):
    calls = []

    monkeypatch.setattr(power_management.platform, "system", lambda: "Windows")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


def test_disable_screen_blanking_uses_xset_on_linux_x11(monkeypatch):
    calls = []

    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power_management.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == [
        ["/usr/bin/xset", "s", "off"],
        ["/usr/bin/xset", "-dpms"],
        ["/usr/bin/xset", "s", "noblank"],
    ]


# ── env-var override ──────────────────────────────────────────────────────────

def test_disable_screen_blanking_skipped_when_envvar_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setenv("UPDATE2026_DISABLE_SCREEN_BLANKING", "0")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


def test_disable_screen_blanking_skipped_when_envvar_false(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setenv("UPDATE2026_DISABLE_SCREEN_BLANKING", "false")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


def test_disable_screen_blanking_skipped_when_envvar_no(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setenv("UPDATE2026_DISABLE_SCREEN_BLANKING", "no")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


# ── setterm fallback ──────────────────────────────────────────────────────────

def test_disable_screen_blanking_falls_back_to_setterm_when_no_display(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power_management.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command) or True)

    power_management.disable_screen_blanking()

    assert any("setterm" in str(c) for c in calls)
    assert not any("xset" in str(c) for c in calls)


def test_disable_screen_blanking_falls_back_to_setterm_when_no_xset(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        power_management.shutil,
        "which",
        lambda name: None if name == "xset" else f"/usr/bin/{name}",
    )
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command) or True)

    power_management.disable_screen_blanking()

    assert any("setterm" in str(c) for c in calls)


def test_disable_screen_blanking_does_nothing_when_neither_available(monkeypatch):
    calls = []
    monkeypatch.setattr(power_management.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power_management.shutil, "which", lambda name: None)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(power_management, "_run_quiet", lambda command: calls.append(command))

    power_management.disable_screen_blanking()

    assert calls == []


# ── _run_quiet ────────────────────────────────────────────────────────────────

def test_run_quiet_returns_true_on_success(monkeypatch):
    import subprocess as _sp
    monkeypatch.setattr(
        power_management.subprocess,
        "run",
        lambda *a, **kw: _sp.CompletedProcess(args=[], returncode=0),
    )
    assert power_management._run_quiet(["echo", "hi"]) is True


def test_run_quiet_returns_false_on_oserror(monkeypatch):
    def _raise(*a, **kw):
        raise OSError("not found")

    monkeypatch.setattr(power_management.subprocess, "run", _raise)
    assert power_management._run_quiet(["missing-binary"]) is False


def test_run_quiet_returns_false_on_timeout(monkeypatch):
    def _raise(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=["x"], timeout=2)

    monkeypatch.setattr(power_management.subprocess, "run", _raise)
    assert power_management._run_quiet(["slow-binary"]) is False
