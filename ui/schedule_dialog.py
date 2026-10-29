#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# schedule_dialog.py — Editor visual del calendario semanal de bypass de contraseña

from __future__ import annotations

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QCheckBox, QTimeEdit,
    QMessageBox, QPushButton, QFrame, QWidget,
)

from application.schedule_config import load_schedule, save_schedule, DAYS

DAY_LABELS = {
    'monday':    'Monday',
    'tuesday':   'Tuesday',
    'wednesday': 'Wednesday',
    'thursday':  'Thursday',
    'friday':    'Friday',
    'saturday':  'Saturday',
    'sunday':    'Sunday',
}

# ── Design tokens (heredados del resto del diálogo) ───────────────────────────
_C_BRAND_DARK  = '#1A3318'
_C_BRAND_MID   = '#2E5229'
_C_BRAND_LIGHT = '#4A7A44'
_C_WARNING     = '#B84F00'
_C_WARNING_BG  = '#FFF3E6'
_C_WARNING_BD  = 'rgba(184,79,0,0.30)'
_C_MUTED       = '#666666'


class ScheduleDialog(QDialog):
    """
    Diálogo para editar el horario semanal de auto-login.

    Incluye dos modos:
      · Always open  — operador entra siempre sin contraseña (always_bypass).
      · Weekly schedule — operador entra sin contraseña solo en los tramos configurados.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Weekly Schedule')
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(440, 610)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(
            "ScheduleDialog {"
            "  background: white;"
            "  border: 2px solid #9e9e9e;"
            "  border-radius: 10px;"
            "}"
        )

        # Filas de widgets: {day: (checkbox, time_start, time_end)}
        self._rows: dict = {}
        self._always_bypass: bool = False

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        # ── Título ────────────────────────────────────────────────────────
        title = QLabel('📅  Operator Auto-login')
        title.setStyleSheet("font: bold 16px; color: #222;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            'Configure when operators can start the app without a password. '
            'Admin always requires a password.'
        )
        subtitle.setStyleSheet("font: 11px; color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")
        layout.addWidget(line)

        # ── Always open toggle ────────────────────────────────────────────
        always_card = QWidget()
        always_card.setObjectName('AlwaysCard')
        always_card_layout = QHBoxLayout(always_card)
        always_card_layout.setContentsMargins(12, 10, 12, 10)
        always_card_layout.setSpacing(10)

        always_text_col = QVBoxLayout()
        always_text_col.setSpacing(2)
        always_title = QLabel('Always open — no password')
        always_title.setStyleSheet("font: 600 13px 'Inter Tight', 'Segoe UI'; color: #222;")
        always_desc = QLabel('Operators always start without a password, regardless of the schedule.')
        always_desc.setWordWrap(True)
        always_desc.setStyleSheet("font: 11px 'Inter Tight', 'Segoe UI'; color: #666;")
        always_text_col.addWidget(always_title)
        always_text_col.addWidget(always_desc)
        always_card_layout.addLayout(always_text_col, stretch=1)

        self._btn_always = QPushButton()
        self._btn_always.setFixedSize(80, 32)
        self._btn_always.setCheckable(False)
        self._btn_always.clicked.connect(self._toggle_always)
        always_card_layout.addWidget(self._btn_always)

        layout.addWidget(always_card)
        self._always_card = always_card

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #ccc;")
        layout.addWidget(line2)

        # ── Cabecera de columnas del calendario ───────────────────────────
        header = QHBoxLayout()
        lbl_day   = QLabel('Day')
        lbl_start = QLabel('Start')
        lbl_end   = QLabel('End')
        for lbl in (lbl_day, lbl_start, lbl_end):
            lbl.setStyleSheet("font: bold 11px; color: #555;")
        lbl_day.setFixedWidth(110)
        lbl_start.setFixedWidth(90)
        lbl_end.setFixedWidth(90)
        header.addWidget(lbl_day)
        header.addStretch()
        header.addWidget(lbl_start)
        header.addSpacing(10)
        header.addWidget(lbl_end)
        layout.addLayout(header)
        self._schedule_header = header

        # ── Fila por día ──────────────────────────────────────────────────
        self._day_rows_widgets: list[QHBoxLayout] = []
        for day in DAYS:
            row = QHBoxLayout()
            row.setSpacing(8)

            chk = QCheckBox(DAY_LABELS[day])
            chk.setFixedWidth(110)
            chk.setStyleSheet("font: 13px; color: #222;")

            t_start = QTimeEdit()
            t_start.setDisplayFormat("HH:mm")
            t_start.setFixedWidth(80)
            t_start.setStyleSheet(self._time_style())

            t_end = QTimeEdit()
            t_end.setDisplayFormat("HH:mm")
            t_end.setFixedWidth(80)
            t_end.setStyleSheet(self._time_style())

            def _toggle(state, ts=t_start, te=t_end):
                enabled = bool(state)
                ts.setEnabled(enabled)
                te.setEnabled(enabled)
                ts.setStyleSheet(self._time_style(enabled))
                te.setStyleSheet(self._time_style(enabled))

            chk.stateChanged.connect(_toggle)

            row.addWidget(chk)
            row.addStretch()
            row.addWidget(t_start)
            row.addWidget(QLabel('—'))
            row.addWidget(t_end)

            layout.addLayout(row)
            self._rows[day] = (chk, t_start, t_end)
            self._day_rows_widgets.append((chk, t_start, t_end))

        # ── Separador ─────────────────────────────────────────────────────
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setStyleSheet("color: #ccc;")
        layout.addWidget(line3)

        # ── Botones Save / Cancel ─────────────────────────────────────────
        btn_row = QHBoxLayout()

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #424242; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            "QPushButton:pressed { background: #212121; }"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton('Save')
        btn_save.setFixedHeight(36)
        btn_save.setStyleSheet(
            "QPushButton { background: #4A7A44; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            "QPushButton:pressed { background: #2E5229; }"
        )
        btn_save.clicked.connect(self._save)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    # ── Toggle "Always open" ──────────────────────────────────────────────────

    def _toggle_always(self):
        self._always_bypass = not self._always_bypass
        self._refresh_always_ui()

    def _refresh_always_ui(self):
        """Actualiza el botón y el estado visual del calendario según _always_bypass."""
        on = self._always_bypass

        # Botón: ON (verde) / OFF (gris)
        if on:
            self._btn_always.setText('ON')
            self._btn_always.setStyleSheet(
                "QPushButton { background: #4A7A44; border: none; border-radius: 6px;"
                " font: bold 13px; color: white; }"
                "QPushButton:pressed { background: #2E5229; }"
            )
            self._always_card.setStyleSheet(
                "QWidget#AlwaysCard { background: #EAF6EE;"
                " border: 1px solid rgba(27,127,62,0.30); border-radius: 8px; }"
            )
        else:
            self._btn_always.setText('OFF')
            self._btn_always.setStyleSheet(
                "QPushButton { background: #9e9e9e; border: none; border-radius: 6px;"
                " font: bold 13px; color: white; }"
                "QPushButton:pressed { background: #616161; }"
            )
            self._always_card.setStyleSheet(
                "QWidget#AlwaysCard { background: #F4F5F3;"
                " border: 1px solid #E0E2DE; border-radius: 8px; }"
            )

        # Deshabilitar el calendario cuando always_bypass está activo
        for chk, t_start, t_end in self._day_rows_widgets:
            chk.setEnabled(not on)
            chk.setStyleSheet(f"font: 13px; color: {'#aaa' if on else '#222'};")
            row_enabled = chk.isChecked() and not on
            t_start.setEnabled(row_enabled)
            t_end.setEnabled(row_enabled)
            t_start.setStyleSheet(self._time_style(row_enabled))
            t_end.setStyleSheet(self._time_style(row_enabled))

    # ── Carga y guardado ──────────────────────────────────────────────────────

    def _load_values(self):
        """Cargar valores actuales desde schedule.json."""
        schedule = load_schedule()

        self._always_bypass = bool(schedule.get('always_bypass', False))
        self._refresh_always_ui()

        for day, (chk, t_start, t_end) in self._rows.items():
            entry = schedule.get(day, {})
            enabled = entry.get("enabled", False)

            chk.setChecked(enabled)
            if not self._always_bypass:
                t_start.setEnabled(enabled)
                t_end.setEnabled(enabled)
                t_start.setStyleSheet(self._time_style(enabled))
                t_end.setStyleSheet(self._time_style(enabled))

            try:
                sh, sm = map(int, entry.get("start", "00:00").split(":"))
                eh, em = map(int, entry.get("end",   "23:59").split(":"))
            except ValueError:
                sh, sm, eh, em = 0, 0, 23, 59

            t_start.setTime(QTime(sh, sm))
            t_end.setTime(QTime(eh, em))

    def _save(self):
        """Guardar configuración y cerrar."""
        data: dict = {'always_bypass': self._always_bypass}
        for day, (chk, t_start, t_end) in self._rows.items():
            data[day] = {
                "enabled": chk.isChecked(),
                "start":   t_start.time().toString("HH:mm"),
                "end":     t_end.time().toString("HH:mm"),
            }
        if save_schedule(data):
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Save failed",
                "Could not save weekly schedule.\n"
                "Check disk space and file permissions.",
            )

    @staticmethod
    def _time_style(enabled: bool = True) -> str:
        color = "#222" if enabled else "#aaa"
        bg    = "white" if enabled else "#f5f5f5"
        return (
            f"QTimeEdit {{ background: {bg}; color: {color};"
            " border: 1px solid #bbb; border-radius: 4px;"
            " font: 13px; padding: 2px 4px; }"
        )
