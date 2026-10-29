#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/role_elevation_overlay.py — Overlay inline de elevación de rol (#role-inline)
#
# RoleElevationOverlay es un QWidget hijo de MainWindow que se muestra encima
# de la interfaz existente como una capa semitransparente con un card central.
# NO abre una ventana nueva — es parte de la misma ventana.
#
# Uso:
#   overlay = RoleElevationOverlay(parent=main_window,
#                                   on_success=lambda: ...,
#                                   on_cancel=lambda: ...)
#   overlay.show_overlay()   # muestra
#   # al acertar la contraseña llama on_success(); al cancelar llama on_cancel()

from __future__ import annotations

import logging
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)


class RoleElevationOverlay(QWidget):
    """
    Overlay inline que pide contraseña para subir el rol a Técnico.

    Se coloca como hijo de MainWindow, cubre toda la ventana con un fondo
    semitransparente y muestra un card centrado con campo de contraseña.
    No abre ninguna ventana OS nueva.
    """

    def __init__(
        self,
        parent: QWidget,
        on_success: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_success = on_success
        self._on_cancel = on_cancel
        self._attempts = 0

        # Cubrir toda la ventana padre
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        # ── Card centrado ──────────────────────────────────────────────────────
        card = QFrame(self)
        card.setObjectName("RoleCard")
        card.setFixedWidth(380)
        card.setStyleSheet(
            "QFrame#RoleCard {"
            "  background: #FFFFFF;"
            "  border-radius: 16px;"
            "  border: none;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(50)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(32, 28, 32, 28)
        vbox.setSpacing(12)

        # Título
        lbl_title = QLabel("Administrator Mode")
        lbl_title.setFont(QFont("Inter Tight", 18, QFont.Bold))
        lbl_title.setStyleSheet("color: #1A3318; background: transparent;")
        lbl_title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(lbl_title)

        lbl_desc = QLabel("Enter the administrator password\nto unlock full access.")
        lbl_desc.setFont(QFont("Inter Tight", 12))
        lbl_desc.setStyleSheet("color: #555; background: transparent;")
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setWordWrap(True)
        vbox.addWidget(lbl_desc)

        vbox.addSpacing(4)

        self._pwd_input = QLineEdit()
        self._pwd_input.setEchoMode(QLineEdit.Password)
        self._pwd_input.setPlaceholderText("Password")
        self._pwd_input.setAlignment(Qt.AlignCenter)
        self._pwd_input.setMinimumHeight(52)
        self._pwd_input.setFont(QFont("Segoe UI", 16))
        self._pwd_input.setStyleSheet(
            "QLineEdit {"
            "  border: 2px solid #4A7A44;"
            "  border-radius: 8px;"
            "  padding: 0 14px;"
            "  background: #FAFAFA;"
            "  color: #111;"
            "}"
            "QLineEdit:focus {"
            "  border-color: #1A3318;"
            "  background: #FFFFFF;"
            "}"
        )
        self._pwd_input.returnPressed.connect(self._try_login)
        vbox.addWidget(self._pwd_input)

        # Etiqueta de error
        self._lbl_err = QLabel("")
        self._lbl_err.setFont(QFont("Inter Tight", 11))
        self._lbl_err.setStyleSheet(
            "color: #C0141F; background: transparent; padding: 0;"
        )
        self._lbl_err.setAlignment(Qt.AlignCenter)
        self._lbl_err.setMinimumHeight(20)
        vbox.addWidget(self._lbl_err)

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(44)
        btn_cancel.setFont(QFont("Inter Tight", 13))
        btn_cancel.setStyleSheet(
            "QPushButton { background: #F0F0F0; border: 1px solid #CCC;"
            " border-radius: 8px; color: #444; }"
            "QPushButton:hover { background: #E0E0E0; }"
            "QPushButton:pressed { background: #D0D0D0; }"
        )
        btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("Enter")
        btn_ok.setFixedHeight(44)
        btn_ok.setFont(QFont("Inter Tight", 14, QFont.Bold))
        btn_ok.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "  stop:0 #4A7A44, stop:1 #1A3318);"
            "  color: white; border: none; border-radius: 8px; }"
            "QPushButton:hover { background: #2E5229; }"
            "QPushButton:pressed { background: #1A3318; }"
        )
        btn_ok.clicked.connect(self._try_login)
        btn_row.addWidget(btn_ok)

        vbox.addLayout(btn_row)

        # Centrar el card en el overlay
        self._card = card

    # ── API pública ───────────────────────────────────────────────────────────

    def show_overlay(self) -> None:
        """Muestra el overlay sobre la ventana padre, centra el card y da foco."""
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self._center_card()
        self._pwd_input.clear()
        self._lbl_err.setText("")
        self._attempts = 0
        self._pwd_input.setFocus()

    # ── Eventos ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        """Dibuja el fondo semitransparente oscuro."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

    def resizeEvent(self, event):
        self._center_card()

    # ── Lógica interna ────────────────────────────────────────────────────────

    def _center_card(self) -> None:
        self._card.adjustSize()
        x = (self.width() - self._card.width()) // 2
        y = (self.height() - self._card.height()) // 2
        self._card.move(x, max(y, 60))

    def _try_login(self) -> None:
        # Technician elevation requires the ADMINISTRATOR password. On pre-split
        # installs (no admin.enc yet) verify_admin falls back to the entry
        # password, so existing single-password sites keep working.
        from application.authentication import verify_admin

        pwd = self._pwd_input.text()
        if not pwd:
            self._lbl_err.setText("Please enter your password.")
            return
        if verify_admin(pwd):
            self.hide()
            self._on_success()
        else:
            self._attempts += 1
            self._pwd_input.clear()
            self._lbl_err.setText(
                f"Incorrect password. (attempt {self._attempts})"
            )
            self._pwd_input.setFocus()

    def _cancel(self) -> None:
        self.hide()
        self._on_cancel()
