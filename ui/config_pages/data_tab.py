# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/data_tab.py — ConfigDialog "Data" tab: backup/restore + About (#894 phase 2)
#
# Backup export/restore (via BackupService/RestoreService) and the version/About
# card. Extracted from ConfigDialog._build_ui; self -> dialog, _panel_layout param.

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel

from ui.styles import MUTED as _C_MUTED


def build_data_tab(dialog, data_layout, mw, panel_layout):
    """Populate the Data tab: backup/restore and the About card."""
    layout = panel_layout(data_layout, 'Data Backup', badge_text='JSON · settings', badge_kind='muted')

    backup_desc = QLabel(
        'Export the current configuration (cameras, presets, attendees, schedule) '
        'or import a previous backup.'
    )
    backup_desc.setWordWrap(True)
    backup_desc.setStyleSheet(
        f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    layout.addWidget(backup_desc)

    # ── Sección: Backup ───────────────────────────────────────────────
    row_backup = QHBoxLayout()
    row_backup.setSpacing(8)

    btn_export = dialog._btn('Export…', variant='primary', width='row', icon='export')
    btn_export.setToolTip('Save seat names, chairman presets and schedule to a ZIP file')

    btn_import = dialog._btn('Import…', variant='ghost', width='row', icon='import')
    btn_import.setToolTip('Restore data from a previously exported ZIP backup')

    row_backup.addWidget(btn_export)
    row_backup.addWidget(btn_import)
    layout.addLayout(row_backup)

    def _export():
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from application.backup_service import BackupService
        default_name = f"khptz_backup_{datetime.now():%Y%m%d_%H%M}.zip"
        dest, _ = QFileDialog.getSaveFileName(
            dialog, "Export Backup", default_name, "ZIP files (*.zip)"
        )
        if not dest:
            return
        btn_export.setEnabled(False)
        btn_export.setText('Exporting…')
        try:
            result = BackupService().create_backup(dest=Path(dest))
            dialog._toast(f'Backup exported · {len(result.included)} item(s)')
        except Exception as exc:
            QMessageBox.warning(dialog, "Export Error", str(exc))
        finally:
            btn_export.setEnabled(True)
            btn_export.setText('Export…')

    def _import():
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from application.restore_service import RestoreService, RestoreError
        src, _ = QFileDialog.getOpenFileName(
            dialog, "Import Backup", "", "ZIP files (*.zip)"
        )
        if not src:
            return
        try:
            result = RestoreService().restore(Path(src))
            names_str = '\n'.join(f"  ✓ {n}" for n in result.restored)
            pre_backup_msg = (
                f"\n\nPre-restore backup en:\n{result.pre_restore_backup}"
                if result.pre_restore_backup else ""
            )
            QMessageBox.information(
                dialog, "Import OK",
                f"Restaurados {len(result.restored)} archivo(s):\n{names_str}"
                f"{pre_backup_msg}"
                "\n\nReinicia la aplicación para aplicar los cambios."
            )
        except RestoreError as exc:
            QMessageBox.warning(dialog, "Import Error", str(exc))
        except Exception as exc:
            QMessageBox.warning(dialog, "Import Error", str(exc))

    btn_export.clicked.connect(_export)
    btn_import.clicked.connect(_import)

    # ── Versión y ayuda ───────────────────────────────────────────────
    from app_version import APP_NAME, read_version
    _ver_text = read_version()

    layout = panel_layout(data_layout, 'About', badge_text=f'v{_ver_text}', badge_kind='muted')

    layout.addWidget(dialog._info_line(APP_NAME, f'v{_ver_text}'))
    layout.addWidget(dialog._info_line(
        'Runtime · Python · PyQt5',
        f'{sys.version[:4]} · 5.15',
    ))
    import platform as _platform
    layout.addWidget(dialog._info_line('Host', _platform.node() or 'Unknown'))

    btn_help = dialog._btn('Help & Documentation', variant='ghost', height=40, icon='help')
    btn_help.clicked.connect(mw._dialogs.HelpMsg)
    layout.addWidget(btn_help, 0, Qt.AlignRight)

    data_layout.addStretch()
