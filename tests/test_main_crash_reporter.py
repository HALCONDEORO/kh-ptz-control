#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_main_crash_reporter.py — the GUI captures its own crashes (#118/#882)
#
# The crash reporter existed but was only installed by the `hallptz` CLI. The
# process that actually crashes on an appliance is the GUI — main.py, which is
# what hallptz-control.service and hallptz-gui.service run — so every field failure
# that ended in `status=6/ABRT` left nothing behind but a photograph of the
# screen.
#
# PyQt5 hands an unhandled exception raised inside a slot to sys.excepthook
# before calling qFatal()/abort(), so installing the reporter in main.py is
# precisely what turns those aborts into a readable report for a support bundle.
#
# The second half: startup steps that are conveniences (legacy migration,
# screen-blanking) must not be able to kill the application. They ran before
# main()'s try/except, so a filesystem or X-server hiccup terminated the process
# with a bare traceback — a restart loop under systemd, for a non-essential step.

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN = REPO_ROOT / "main.py"
CLI = REPO_ROOT / "runtime" / "cli.py"


@pytest.fixture(scope="module")
def main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


class TestCrashReporterIsInstalledByTheGui:
    def test_main_installs_it(self, main_source):
        """Must be an actual call, not merely the import — importing the name
        and never calling it is exactly the state this fix corrected."""
        calls = [
            line for line in main_source.splitlines()
            if "install_crash_reporter(" in line
            and not line.lstrip().startswith(("#", "from", "import"))
        ]
        assert calls, "the GUI entry point imports the crash reporter but never installs it"

    def test_installed_before_the_ui_is_built(self, main_source):
        """A crash while constructing MainWindow must be captured too."""
        install = main_source.index("install_crash_reporter(")
        build = main_source.index("MainWindow()")
        assert install < build

    def test_cli_still_installs_it(self):
        """Both entry points need it; this fix must not have moved it."""
        assert "install_crash_reporter" in CLI.read_text(encoding="utf-8")

    def test_reports_the_real_version_and_profile(self, main_source):
        """A crash report that cannot be tied to a build is not actionable."""
        window = main_source[main_source.index("install_crash_reporter("):][:400]
        assert "version=" in window
        assert "mode=" in window


class TestNonEssentialStartupStepsCannotKillStartup:
    def test_steps_are_guarded(self, main_source):
        """Both must sit inside the guarded loop, not be called bare — the
        names alone appear in the imports regardless."""
        loop = main_source.index("for _step in (")
        body = main_source[loop:loop + 400]
        for step in ("migrate_legacy_files", "disable_screen_blanking"):
            assert step in body, f"{step} is not inside the guarded startup loop"
        assert "try:" in body and "except Exception" in body

    def test_failures_are_logged_and_survived(self, main_source):
        assert "continuing" in main_source

    def test_guard_precedes_the_qt_section(self, main_source):
        guard = main_source.index("never block startup on these")
        qapp = main_source.index("QApplication(sys.argv)")
        assert guard < qapp


class TestExcepthookIsActuallyInstalled:
    """Behavioural check on the reporter itself, independent of main.py."""

    def test_install_sets_sys_excepthook(self, tmp_path, monkeypatch):
        from application import crash_reporter

        original = sys.excepthook
        try:
            # Order-independent: another test may already have installed the
            # reporter, so start from a sentinel rather than assuming the
            # default hook is in place.
            def _sentinel(*args):  # pragma: no cover - never called
                raise AssertionError("sentinel hook should have been replaced")

            sys.excepthook = _sentinel
            crash_reporter.install_crash_reporter(
                version="test", mode="production", log_dir=tmp_path
            )
            assert sys.excepthook is not _sentinel
            assert sys.excepthook is crash_reporter._excepthook
        finally:
            sys.excepthook = original

    def test_report_is_written_for_an_unhandled_exception(self, tmp_path):
        from application import crash_reporter

        original = sys.excepthook
        try:
            crash_reporter.install_crash_reporter(
                version="3.38.3", mode="production", log_dir=tmp_path
            )
            try:
                raise RuntimeError("simulated GUI abort")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())

            reports = list(tmp_path.glob("*"))
            assert reports, "no crash report was written"
            text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in reports)
            assert "simulated GUI abort" in text
            assert "3.38.3" in text
        finally:
            sys.excepthook = original
