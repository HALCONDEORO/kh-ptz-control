#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_cli_console_encoding.py — Regression tests for #884
#
# The first physical Raspberry Pi install failed with:
#   UnicodeEncodeError: 'charmap' codec can't encode character '—'
#   Permission denied: '/var/log/khptz/app.log'
#
# A terminal locale or an unwritable log directory must never decide whether a
# CLI command succeeds.

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from runtime.console import (
    configure_console_encoding,
    safe_print,
    safe_text,
    user_state_dir,
    writable_log_dir,
)


class _LegacyStream(io.TextIOBase):
    """A stdout that behaves like a cp1252/ascii terminal: raises on an em dash."""

    def __init__(self, encoding: str = "cp1252"):
        self._encoding = encoding
        self.written: list[str] = []

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding

    def write(self, text: str) -> int:
        text.encode(self._encoding)  # raises UnicodeEncodeError, like the real thing
        self.written.append(text)
        return len(text)


# ═══════════════════════════════════════════════════════════════════════════════
# safe_text / safe_print under a non-UTF-8 stdout
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeTextOnLegacyEncoding:
    def test_em_dash_is_downgraded_for_ascii_stream(self):
        stream = _LegacyStream("ascii")
        result = safe_text("Already provisioned — setup wizard not needed.", stream)
        assert "—" not in result
        assert "--" in result
        result.encode("ascii")  # must not raise

    def test_text_is_unchanged_on_utf8_stream(self):
        stream = _LegacyStream("utf-8")
        text = "Already provisioned — setup wizard not needed."
        assert safe_text(text, stream) == text

    def test_ascii_text_is_never_altered(self):
        stream = _LegacyStream("ascii")
        assert safe_text("plain ascii output", stream) == "plain ascii output"

    def test_unknown_glyph_falls_back_to_replacement(self):
        stream = _LegacyStream("ascii")
        result = safe_text("box drawing ═ here", stream)
        result.encode("ascii")  # must not raise

    def test_safe_print_does_not_raise_on_legacy_stream(self):
        stream = _LegacyStream("cp1252")
        # The exact line that crashed `khptz setup` on the Pi.
        safe_print("  [INFO]  Already provisioned — setup wizard not needed.", file=stream)
        assert stream.written  # something was actually emitted

    def test_safe_print_survives_a_stream_that_lies_about_encoding(self):
        class _Liar(_LegacyStream):
            @property
            def encoding(self) -> str:
                return "utf-8"  # claims UTF-8 but write() still enforces ascii

            def write(self, text: str) -> int:
                text.encode("ascii")
                self.written.append(text)
                return len(text)

        stream = _Liar()
        safe_print("doctor — overall status", file=stream)
        assert stream.written


# ═══════════════════════════════════════════════════════════════════════════════
# configure_console_encoding()
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigureConsoleEncoding:
    def test_never_raises_on_a_stream_without_reconfigure(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _LegacyStream("ascii"))
        monkeypatch.setattr(sys, "stderr", _LegacyStream("ascii"))
        configure_console_encoding()  # must not raise

    def test_never_raises_when_reconfigure_fails(self, monkeypatch):
        class _Stubborn(_LegacyStream):
            def reconfigure(self, **kwargs):
                raise OSError("cannot reconfigure a pipe")

        monkeypatch.setattr(sys, "stdout", _Stubborn())
        monkeypatch.setattr(sys, "stderr", _Stubborn())
        configure_console_encoding()  # must not raise

    def test_reports_true_for_utf8_streams(self, monkeypatch):
        class _Utf8(_LegacyStream):
            def __init__(self):
                super().__init__("utf-8")

            def reconfigure(self, **kwargs):
                return None

        monkeypatch.setattr(sys, "stdout", _Utf8())
        monkeypatch.setattr(sys, "stderr", _Utf8())
        assert configure_console_encoding() is True


# ═══════════════════════════════════════════════════════════════════════════════
# Log directory selection under an unwritable production path
# ═══════════════════════════════════════════════════════════════════════════════

class TestWritableLogDir:
    def test_returns_preferred_when_writable(self, tmp_path):
        preferred = tmp_path / "var-log-khptz"
        assert writable_log_dir(preferred) == preferred
        assert preferred.is_dir()

    def test_falls_back_when_preferred_is_unwritable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

        unwritable = tmp_path / "denied"

        real_mkdir = Path.mkdir

        def fake_mkdir(self, *args, **kwargs):
            if self == unwritable:
                raise PermissionError(f"Permission denied: '{self}'")
            return real_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)

        result = writable_log_dir(unwritable)
        assert result is not None
        assert result != unwritable
        assert str(tmp_path / "state") in str(result)

    def test_returns_none_when_nothing_is_writable(self, monkeypatch):
        def always_denied(self, *args, **kwargs):
            raise PermissionError("read-only file system")

        monkeypatch.setattr(Path, "mkdir", always_denied)
        assert writable_log_dir(Path("/var/log/khptz")) is None

    def test_none_preferred_still_yields_user_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        result = writable_log_dir(None)
        assert result is not None
        assert result.is_dir()


class TestUserStateDir:
    def test_honours_xdg_state_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        assert user_state_dir() == tmp_path / "khptz"

    def test_defaults_under_home_without_xdg(self, monkeypatch):
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        assert user_state_dir() == Path.home() / ".local" / "state" / "khptz"


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive commands must not target service-owned log paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestCliLogDirSelection:
    def _resolver(self, log_dir: Path):
        class _R:
            pass

        r = _R()
        r.log_dir = log_dir
        return r

    @pytest.mark.parametrize("command", ["setup", "demo"])
    def test_interactive_commands_use_user_state_dir(self, command, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        from runtime.cli import _cli_log_dir

        production = tmp_path / "var-log-khptz"
        result = _cli_log_dir(command, self._resolver(production))

        assert result is not None
        assert production not in result.parents and result != production
        assert str(tmp_path / "state") in str(result)

    def test_service_commands_prefer_production_log_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        from runtime.cli import _cli_log_dir

        production = tmp_path / "var-log-khptz"
        assert _cli_log_dir("status", self._resolver(production)) == production

    def test_readonly_command_falls_back_instead_of_failing(self, tmp_path, monkeypatch):
        """`khptz doctor` as the desktop user must not need /var/log/khptz."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        from runtime.cli import _cli_log_dir

        production = tmp_path / "denied"
        real_mkdir = Path.mkdir

        def fake_mkdir(self, *args, **kwargs):
            if self == production:
                raise PermissionError(f"Permission denied: '{production}'")
            return real_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)

        result = _cli_log_dir("doctor", self._resolver(production))
        assert result is not None
        assert result != production


# ═══════════════════════════════════════════════════════════════════════════════
# Crash reporting has a user-mode fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrashReportFallback:
    def test_falls_back_to_user_dir_when_install_root_is_readonly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        import application.crash_reporter as cr

        readonly = tmp_path / "opt-khptz-logs"
        monkeypatch.setattr(cr, "_installed_log_dir", readonly)

        real_mkdir = Path.mkdir

        def fake_mkdir(self, *args, **kwargs):
            if self == readonly:
                raise PermissionError("Read-only file system")
            return real_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fake_mkdir)

        path = cr._write_report("boom")
        assert path is not None
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "boom"
        assert str(tmp_path / "state") in str(path)

    def test_returns_none_when_no_location_is_writable(self, tmp_path, monkeypatch):
        import application.crash_reporter as cr

        monkeypatch.setattr(cr, "_installed_log_dir", tmp_path / "nope")

        def always_denied(self, *args, **kwargs):
            raise PermissionError("read-only file system")

        monkeypatch.setattr(Path, "mkdir", always_denied)
        assert cr._write_report("boom") is None  # must not raise

    def test_uses_configured_dir_when_writable(self, tmp_path, monkeypatch):
        import application.crash_reporter as cr

        target = tmp_path / "var-log-khptz"
        monkeypatch.setattr(cr, "_installed_log_dir", target)
        path = cr._write_report("boom")
        assert path is not None
        assert path.parent == target


# ═══════════════════════════════════════════════════════════════════════════════
# Logging setup tolerates an unwritable directory
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoggingSetupTolerance:
    def test_setup_logging_does_not_raise_on_permission_denied(self, tmp_path, monkeypatch):
        import runtime.logging_setup as ls

        monkeypatch.setattr(ls, "_configured", False)

        def always_denied(self, *args, **kwargs):
            raise PermissionError("Permission denied: '/var/log/khptz'")

        monkeypatch.setattr(Path, "mkdir", always_denied)

        # Console-only is the correct degraded outcome, not an exception.
        assert ls.setup_logging(log_dir=Path("/var/log/khptz")) is False

