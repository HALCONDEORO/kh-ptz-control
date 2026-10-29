# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/crash_reporter.py (#118)."""
from __future__ import annotations

import sys


from application.crash_reporter import (
    _build_report,
    _write_report,
    install_crash_reporter,
    _excepthook,
)


# ── Report content ─────────────────────────────────────────────────────────────

class TestBuildReport:
    def _exc(self, msg="test error"):
        try:
            raise RuntimeError(msg)
        except RuntimeError:
            return sys.exc_info()

    def test_contains_traceback(self):
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "Traceback" in report
        assert "RuntimeError" in report

    def test_contains_version(self):
        import application.crash_reporter as cr
        cr._installed_version = "9.8.7"
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "9.8.7" in report

    def test_contains_mode(self):
        import application.crash_reporter as cr
        cr._installed_mode = "demo"
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "demo" in report

    def test_contains_timestamp(self):
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "Time:" in report

    def test_contains_python_info(self):
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "Python:" in report

    def test_contains_platform_info(self):
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "Platform:" in report

    def test_no_secrets_in_report(self):
        exc_type, exc_value, exc_tb = self._exc()
        report = _build_report(exc_type, exc_value, exc_tb)
        assert "password" not in report.lower()

    def test_report_bounded_size(self):
        from application.crash_reporter import _MAX_REPORT_BYTES
        exc_type, exc_value, exc_tb = self._exc("x" * 200_000)
        report = _build_report(exc_type, exc_value, exc_tb)
        assert len(report.encode()) <= _MAX_REPORT_BYTES + 200  # small margin for truncation line

    def test_keyboard_interrupt_not_written(self, tmp_path):
        orig_hook = sys.excepthook
        install_crash_reporter(log_dir=tmp_path)
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            exc_type, exc_value, exc_tb = sys.exc_info()
        _excepthook(exc_type, exc_value, exc_tb)
        sys.excepthook = orig_hook
        assert not list(tmp_path.glob("crash_*.log"))


# ── File writing ───────────────────────────────────────────────────────────────

class TestWriteReport:
    def test_creates_log_file(self, tmp_path):
        import application.crash_reporter as cr
        cr._installed_log_dir = tmp_path
        path = _write_report("test crash content")
        assert path is not None
        assert path.exists()

    def test_log_file_named_crash(self, tmp_path):
        import application.crash_reporter as cr
        cr._installed_log_dir = tmp_path
        path = _write_report("content")
        assert path.name.startswith("crash_")
        assert path.suffix == ".log"

    def test_log_file_content(self, tmp_path):
        import application.crash_reporter as cr
        cr._installed_log_dir = tmp_path
        path = _write_report("hello crash")
        assert "hello crash" in path.read_text(encoding="utf-8")

    def test_creates_log_dir_if_missing(self, tmp_path):
        import application.crash_reporter as cr
        log_dir = tmp_path / "new" / "logs"
        cr._installed_log_dir = log_dir
        path = _write_report("content")
        assert log_dir.exists()
        assert path is not None

    def test_falls_back_to_user_dir_when_log_dir_unwritable(self, tmp_path, monkeypatch):
        import application.crash_reporter as cr
        # Simulate unwritable directory by pointing at a file
        fake_dir = tmp_path / "not_a_dir"
        fake_dir.write_text("blocker", encoding="utf-8")
        cr._installed_log_dir = fake_dir / "logs"
        # On a real install /var/log/hallptz belongs to the service user, so a
        # report written by the desktop user must land somewhere rather than be
        # lost (#884).
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        result = _write_report("content")
        assert result is not None
        assert "content" in result.read_text(encoding="utf-8")
        assert tmp_path / "state" in result.parents

    def test_returns_none_when_no_directory_is_writable(self, tmp_path, monkeypatch):
        import application.crash_reporter as cr
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("blocker", encoding="utf-8")
        cr._installed_log_dir = blocker / "logs"
        # Both candidates unwritable: the reporter gives up quietly rather than
        # raising from inside an excepthook.
        monkeypatch.setenv("XDG_STATE_HOME", str(blocker / "state"))
        assert _write_report("content") is None


# ── install_crash_reporter ─────────────────────────────────────────────────────

class TestInstallCrashReporter:
    def test_sets_excepthook(self, tmp_path):
        from application.crash_reporter import _excepthook
        orig = sys.excepthook
        try:
            install_crash_reporter(log_dir=tmp_path)
            assert sys.excepthook is _excepthook
        finally:
            sys.excepthook = orig

    def test_records_version(self, tmp_path):
        import application.crash_reporter as cr
        install_crash_reporter(version="1.2.3", log_dir=tmp_path)
        assert cr._installed_version == "1.2.3"

    def test_records_mode(self, tmp_path):
        import application.crash_reporter as cr
        install_crash_reporter(mode="demo", log_dir=tmp_path)
        assert cr._installed_mode == "demo"

    def test_records_log_dir(self, tmp_path):
        import application.crash_reporter as cr
        install_crash_reporter(log_dir=tmp_path)
        assert cr._installed_log_dir == tmp_path


# ── excepthook integration ─────────────────────────────────────────────────────

class TestExcepthookIntegration:
    def test_crash_creates_log_file(self, tmp_path):
        orig = sys.excepthook
        try:
            install_crash_reporter(version="0.1", mode="test", log_dir=tmp_path)
            try:
                raise ValueError("integration test crash")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
            # Call the hook directly (don't let it call sys.__excepthook__ which prints)
            import application.crash_reporter as cr
            cr._excepthook(exc_type, exc_value, exc_tb)
        finally:
            sys.excepthook = orig

        crash_files = list(tmp_path.glob("crash_*.log"))
        assert len(crash_files) == 1
        content = crash_files[0].read_text(encoding="utf-8")
        assert "ValueError" in content
        assert "integration test crash" in content

    def test_crash_hook_does_not_raise(self, tmp_path):
        orig = sys.excepthook
        try:
            install_crash_reporter(log_dir=tmp_path)
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                exc_type, exc_value, exc_tb = sys.exc_info()
            import application.crash_reporter as cr
            cr._excepthook(exc_type, exc_value, exc_tb)
        finally:
            sys.excepthook = orig
