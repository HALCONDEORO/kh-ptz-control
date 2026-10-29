#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_data_tab.py — ui/config_pages/data_tab.py had no coverage
#
# This is the operator's only route to backup and restore from the touchscreen,
# and it is the last thing used before a risky change on a customer site. What
# had to be pinned down:
#
#   - a cancelled file dialog must do nothing at all (no half-written ZIP, no
#     restore of the previously chosen file);
#   - a failure must be reported and must leave the button usable, otherwise the
#     operator is left with a dead "Exporting…" control and no way to retry;
#   - a restore must surface where the pre-restore backup went — that path is the
#     only way back if the imported data turns out to be wrong.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, has_text, make_harness, panel_layout,
)


class _BackupResult:
    def __init__(self, included):
        self.included = included


class _RestoreResult:
    def __init__(self, restored, pre_restore_backup=None):
        self.restored = restored
        self.pre_restore_backup = pre_restore_backup


@pytest.fixture
def messages(monkeypatch):
    """Capture the modal feedback instead of showing it."""
    from PyQt5.QtWidgets import QMessageBox

    captured: dict[str, list[tuple[str, str]]] = {"warning": [], "information": []}
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda parent, title, text, *a, **k: captured["warning"].append((title, text)),
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda parent, title, text, *a, **k: captured["information"].append((title, text)),
    )
    return captured


@pytest.fixture
def file_dialog(monkeypatch, tmp_path):
    """Answer the save/open dialogs with a chosen path (or a cancellation)."""
    from PyQt5.QtWidgets import QFileDialog

    state = {"save": str(tmp_path / "backup.zip"), "open": str(tmp_path / "in.zip")}
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *a, **k: (state["save"], "ZIP files (*.zip)"),
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **k: (state["open"], "ZIP files (*.zip)"),
    )
    return state


def build():
    dialog, mw, layout = make_harness()
    from ui.config_pages.data_tab import build_data_tab
    build_data_tab(dialog, layout, mw, panel_layout)
    return dialog, mw, layout


class TestLayout:
    def test_offers_export_and_import(self):
        dialog, mw, layout = build()
        assert button_named(layout, "Export")
        assert button_named(layout, "Import")

    def test_explains_what_a_backup_contains(self):
        """The operator has to know whether this covers presets before relying
        on it ahead of a risky change."""
        dialog, mw, layout = build()
        assert has_text(layout, "presets")

    def test_shows_the_installed_version(self):
        """The first question support asks."""
        from app_version import read_version
        dialog, mw, layout = build()
        assert has_text(layout, read_version())

    def test_help_button_opens_the_help_dialog(self):
        dialog, mw, layout = build()
        button_named(layout, "Help").click()
        assert mw._dialogs.calls == ["HelpMsg"]


class TestExport:
    def test_cancelling_writes_nothing(self, monkeypatch, file_dialog, messages):
        calls = []
        import application.backup_service as backup_service
        monkeypatch.setattr(
            backup_service, "BackupService",
            lambda *a, **k: calls.append("built") or object(),
        )
        file_dialog["save"] = ""          # operator pressed Cancel
        dialog, mw, layout = build()
        button_named(layout, "Export").click()
        assert calls == []
        assert dialog.toasts == []

    def test_cancelling_leaves_the_button_usable(self, file_dialog, messages):
        file_dialog["save"] = ""
        dialog, mw, layout = build()
        btn = button_named(layout, "Export")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Export…"

    def test_success_reports_how_much_was_saved(self, monkeypatch, file_dialog, messages):
        import application.backup_service as backup_service

        class _Service:
            def create_backup(self, dest):
                return _BackupResult(["config.yaml", "presets.json"])

        monkeypatch.setattr(backup_service, "BackupService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Export").click()
        assert dialog.toasts == [("Backup exported · 2 item(s)", "ok")]

    def test_success_writes_to_the_chosen_path(self, monkeypatch, file_dialog, messages):
        import application.backup_service as backup_service
        seen = {}

        class _Service:
            def create_backup(self, dest):
                seen["dest"] = dest
                return _BackupResult([])

        monkeypatch.setattr(backup_service, "BackupService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Export").click()
        assert str(seen["dest"]) == file_dialog["save"]

    def test_failure_is_reported_to_the_operator(self, monkeypatch, file_dialog, messages):
        import application.backup_service as backup_service

        class _Service:
            def create_backup(self, dest):
                raise OSError("No space left on device")

        monkeypatch.setattr(backup_service, "BackupService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Export").click()
        assert messages["warning"]
        assert "No space left on device" in messages["warning"][0][1]

    def test_failure_leaves_the_button_usable(self, monkeypatch, file_dialog, messages):
        """Without the finally-branch the control stays stuck on 'Exporting…'
        and the operator cannot retry without reopening the dialog."""
        import application.backup_service as backup_service

        class _Service:
            def create_backup(self, dest):
                raise OSError("boom")

        monkeypatch.setattr(backup_service, "BackupService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        btn = button_named(layout, "Export")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Export…"

    def test_failure_is_not_reported_as_success(self, monkeypatch, file_dialog, messages):
        import application.backup_service as backup_service

        class _Service:
            def create_backup(self, dest):
                raise OSError("boom")

        monkeypatch.setattr(backup_service, "BackupService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Export").click()
        assert dialog.toasts == []


class TestImport:
    def test_cancelling_restores_nothing(self, monkeypatch, file_dialog, messages):
        import application.restore_service as restore_service
        calls = []
        monkeypatch.setattr(
            restore_service, "RestoreService",
            lambda *a, **k: calls.append("built") or object(),
        )
        file_dialog["open"] = ""
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert calls == []
        assert messages["information"] == []

    def test_success_lists_what_was_restored(self, monkeypatch, file_dialog, messages):
        import application.restore_service as restore_service

        class _Service:
            def restore(self, src):
                return _RestoreResult(["config.yaml", "room_layout.json"])

        monkeypatch.setattr(restore_service, "RestoreService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert messages["information"]
        body = messages["information"][0][1]
        assert "config.yaml" in body and "room_layout.json" in body

    def test_success_names_the_pre_restore_backup(self, monkeypatch, file_dialog, messages):
        """That ZIP is the only way back from a wrong import."""
        import application.restore_service as restore_service

        class _Service:
            def restore(self, src):
                return _RestoreResult(["config.yaml"], "/var/backups/hallptz/pre-restore.zip")

        monkeypatch.setattr(restore_service, "RestoreService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert "/var/backups/hallptz/pre-restore.zip" in messages["information"][0][1]

    def test_success_tells_the_operator_to_restart(self, monkeypatch, file_dialog, messages):
        """Restored data is only live after a restart — an operator who does not
        know that reports the restore as broken."""
        import application.restore_service as restore_service

        class _Service:
            def restore(self, src):
                return _RestoreResult(["config.yaml"])

        monkeypatch.setattr(restore_service, "RestoreService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert "einicia" in messages["information"][0][1]   # Reinicia la aplicación

    def test_a_rejected_backup_is_reported_not_raised(self, monkeypatch, file_dialog, messages):
        import application.restore_service as restore_service

        class _Service:
            def restore(self, src):
                raise restore_service.RestoreError("Backup schema is newer than this install")

        monkeypatch.setattr(restore_service, "RestoreService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert messages["warning"]
        assert "schema is newer" in messages["warning"][0][1]
        assert messages["information"] == []

    def test_an_unexpected_failure_is_also_contained(self, monkeypatch, file_dialog, messages):
        """A corrupt ZIP raises something other than RestoreError; it must not
        escape into the Qt event loop."""
        import application.restore_service as restore_service

        class _Service:
            def restore(self, src):
                raise zipfile_bad_error()

        def zipfile_bad_error():
            import zipfile
            return zipfile.BadZipFile("File is not a zip file")

        monkeypatch.setattr(restore_service, "RestoreService", lambda *a, **k: _Service())
        dialog, mw, layout = build()
        button_named(layout, "Import").click()
        assert messages["warning"]
        assert "not a zip file" in messages["warning"][0][1]
