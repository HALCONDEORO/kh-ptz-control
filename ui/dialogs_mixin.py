#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# dialogs_mixin.py — Mixin de diálogos de configuración y ayuda
#
# Responsabilidad única: gestionar todos los diálogos modales de la app:
# cambio de IP, cambio de VISCA ID, ayuda y cierre.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - REDUNDANCIA ELIMINADA: _change_ip() y _change_cam_id() compartían
#     un 80% de código idéntico (confirmación, input, validación, escritura,
#     reinicio). Se han fusionado en _change_config(cam_num, config_type).
#
#     Flujo compartido:
#       1. Determinar nombre y valor actual según cam_num + config_type.
#       2. Pedir confirmación.
#       3. Pedir nuevo valor (QInputDialog).
#       4. Validar (is_valid_ip o is_valid_cam_id).
#       5. Redirigir al setup wizard (config.yaml). Este diálogo legacy ya NO
#          escribe archivos .txt: la config de cámara vive en config.yaml.
#
#     Los wrappers públicos PTZ1Address(), PTZ2Address(), etc. siguen existiendo
#     para no cambiar las conexiones de señal en main_window.py.


from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMessageBox, QInputDialog,
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
)

from config import (
    CAM1, CAM2, Contact,
    is_valid_ip, is_valid_cam_id,
)
from runtime.secret_manager import (
    encrypt_password as _save_password,
    encrypt_secret,
    SECRET_ADMIN,
)


class ChangePasswordDialog(QDialog):
    """Modal dialog to change a stored password — operator entry or admin.

    ``target`` selects which secret is being changed; the current-password check
    is verified through application.authentication so the same rule (and the
    admin migration fallback) applies everywhere.
    """

    # target -> (window/heading title, short noun for the confirmation)
    _LABELS = {
        "entry": ("Change Operator Password", "Operator password"),
        "admin": ("Change Administrator Password", "Administrator password"),
    }

    def __init__(self, parent=None, target: str = "entry", require_current: bool = True):
        super().__init__(parent)
        if target not in self._LABELS:
            raise ValueError(f"Unknown password target: {target!r}")
        self._target = target
        # La contraseña actual solo se pide al cambiar la PROPIA. Cuando se resetea
        # (admin sobre el operador, o supercore sobre cualquiera) no hay campo
        # "Current" ni verificación.
        self._require_current = require_current
        self.setWindowTitle(self._LABELS[target][0])
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(340, 230 if require_current else 195)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.new_password = ''
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel(f'🔒  {self._LABELS[self._target][0]}')
        title.setStyleSheet("font: bold 15px; color: #222;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Campos de contraseña
        form = QFormLayout()
        form.setSpacing(8)

        self._cur = QLineEdit()
        self._cur.setEchoMode(QLineEdit.Password)
        self._cur.setPlaceholderText('Current password')

        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.Password)
        self._new.setPlaceholderText('New password')

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.Password)
        self._confirm.setPlaceholderText('Repeat new password')

        field_style = (
            "QLineEdit { border: 1px solid #bbb; border-radius: 4px;"
            " padding: 4px 6px; font: 13px; }"
            "QLineEdit:focus { border-color: #1976D2; }"
        )
        for w in (self._cur, self._new, self._confirm):
            w.setStyleSheet(field_style)

        if self._require_current:
            form.addRow('Current:', self._cur)
        form.addRow('New:', self._new)
        form.addRow('Confirm:', self._confirm)
        layout.addLayout(form)

        # Etiqueta de error inline
        self._err = QLabel('')
        self._err.setStyleSheet("color: #c62828; font: 12px;")
        self._err.setAlignment(Qt.AlignCenter)
        self._err.setWordWrap(True)
        layout.addWidget(self._err)

        # Botones OK / Cancel
        btn_row = QHBoxLayout()
        btn_ok = QPushButton('OK')
        btn_ok.setFixedHeight(32)
        btn_ok.setStyleSheet(
            "QPushButton { background: #1976D2; border: none; border-radius: 5px;"
            " font: bold 12px; color: white; }"
            "QPushButton:pressed { background: #1251a0; }"
        )
        btn_ok.clicked.connect(self._validate)

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #e0e0e0; border: none; border-radius: 5px;"
            " font: 12px; color: #333; }"
            "QPushButton:pressed { background: #bdbdbd; }"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.setStyleSheet(
            "ChangePasswordDialog {"
            "  background: white;"
            "  border: 2px solid #9e9e9e;"
            "  border-radius: 10px;"
            "}"
        )

    def _validate(self):
        new = self._new.text()
        confirm = self._confirm.text()

        if self._require_current:
            cur = self._cur.text()
            if not cur or not new or not confirm:
                self._err.setText('All fields are required.')
                return
            # Verify the current password through the central auth service
            # (constant-time; admin honours the no-admin-yet migration fallback).
            from application.authentication import verify_admin, verify_entry
            verify = verify_admin if self._target == "admin" else verify_entry
            if not verify(cur):
                self._err.setText('Current password is incorrect.')
                self._cur.clear()
                self._cur.setFocus()
                return
        elif not new or not confirm:
            # Reset (sin contraseña actual): solo new + confirm.
            self._err.setText('All fields are required.')
            return

        if new != confirm:
            self._err.setText('New passwords do not match.')
            self._new.clear()
            self._confirm.clear()
            self._new.setFocus()
            return

        self.new_password = new
        self.accept()


class DialogsController:

    def __init__(self, window):
        self._w = window

    def _change_config(self, cam_num: int, config_type: str):
        """
        Diálogo genérico para cambiar IP o VISCA ID de una cámara.

        Parámetros:
          cam_num:     1 (Platform) o 2 (Comments).
          config_type: 'ip' o 'id'.

        MOTIVO DE UNIFICACIÓN:
        _change_ip() y _change_cam_id() eran prácticamente idénticos:
        misma estructura de confirmación → input → validación → escritura → reinicio.
        La única diferencia era qué constante leer, qué archivo escribir
        y qué función de validación llamar. Con un solo método parametrizado,
        cualquier cambio en el flujo (p.ej. el mensaje de confirmación) solo
        se hace en un sitio.

        MOTIVO DEL REINICIO:
        Las IPs e IDs se cargan al importar config.py (ejecución a nivel de módulo).
        Recargarlas en caliente requeriría reimportar el módulo y redistribuir
        las referencias. Se solicita un reinicio limpio mediante close(), que
        ejecuta closeEvent (supervisor, workers, ATEM monitor) antes de salir.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'

        # Guard: camera hardware config must not change during an active session
        if getattr(self._w, 'session_active', False):
            QMessageBox.warning(
                self._w, 'Session Active',
                'Session is active. End the session before changing system settings.',
                QMessageBox.Ok,
            )
            return

        # Determinar qué campo cambiar según config_type
        if config_type == 'ip':
            current  = CAM1.ip  if cam_num == 1 else CAM2.ip
            field    = 'IP address'
            validate = is_valid_ip
            hint     = 'four numbers separated by dots (e.g. 172.16.1.11)'
            label    = 'IP Address'
        else:  # 'id'
            current  = CAM1.cam_id if cam_num == 1 else CAM2.cam_id
            field    = 'VISCA ID'
            validate = is_valid_cam_id
            hint     = 'a hex value such as "81" or "82"'
            label    = 'Camera ID'

        title = f'{cam_name} PTZ Control'

        # Paso 1: confirmación — evitar cambios accidentales
        if QMessageBox.warning(
            self._w, title,
            f'Do you want to change the {field} used to control the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        ) != QMessageBox.Ok:
            return

        # Paso 2: pedir nuevo valor
        dlg = QInputDialog(self._w)
        dlg.setWindowTitle(title)
        dlg.setLabelText(f'New {field} for {cam_name} Camera (current: {current}):')
        dlg.setTextValue(current)
        dlg.setWindowModality(Qt.WindowModal)
        ok = dlg.exec_() == QDialog.Accepted
        text = dlg.textValue()
        if not (ok and text.strip()):
            return  # Usuario canceló o dejó vacío

        text = text.strip()

        # Paso 3: validar
        if not validate(text):
            QMessageBox.warning(
                self._w, f'Invalid {label}',
                f'"{text}" is not a valid {field}.\nPlease enter {hint}.'
            )
            return

        # Paso 4: camera IP / VISCA ID now live in config.yaml, managed by the
        # setup wizard — not in per-field .txt files written from the UI. The
        # old behaviour wrote a bare-relative "PTZ1IP.txt" into the process CWD
        # (which is read-only under /opt/hallptz on the Pi) and was never read back
        # as authoritative config, so it silently did nothing. Direct the
        # operator to the supported path instead of persisting from the UI,
        # which also removes an ADR-001/006 UI-writes-persistence violation.
        QMessageBox.information(
            self._w,
            'Managed by the setup wizard',
            f'The {field} is now configured in config.yaml, not here.\n'
            'Run "hallptz setup" to change camera settings.',
        )

    # ── Wrappers públicos ─────────────────────────────────────────────────
    # Conectados a los botones en main_window.py — no cambian la interfaz pública.

    def PTZ1Address(self):  self._change_config(1, 'ip')
    def PTZ2Address(self):  self._change_config(2, 'ip')
    def PTZ1IDchange(self): self._change_config(1, 'id')
    def PTZ2IDchange(self): self._change_config(2, 'id')

    def ChangePassword(self):
        """Diálogo para cambiar la contraseña de entrada (operador)."""
        self._change_password("entry")

    def ChangeAdminPassword(self):
        """Diálogo para cambiar la contraseña de administrador."""
        self._change_password("admin")

    def _change_password(self, target: str):
        """Open the change-password dialog for *target* and persist on accept.

        La contraseña actual solo se exige al cambiar la PROPIA credencial:
          • Supercore (maestro) gestiona todas sin poner la actual.
          • Admin resetea la del operador sin conocerla; para la suya (admin) sí.
        """
        is_supercore = getattr(self._w, '_session_is_supercore', False)
        require_current = (not is_supercore) and (target == "admin")
        dlg = ChangePasswordDialog(self._w, target=target, require_current=require_current)
        if dlg.exec_() != QDialog.Accepted:
            return
        if target == "admin":
            encrypt_secret(SECRET_ADMIN, dlg.new_password)
        else:
            _save_password(dlg.new_password)
        label = ChangePasswordDialog._LABELS[target][1]
        QMessageBox.information(
            self._w, 'Password Changed',
            f'{label} updated successfully.\n'
            'The new password applies the next time it is used.',
            QMessageBox.Ok,
        )

    def HelpMsg(self):
        """Muestra el mensaje de contacto de soporte técnico."""
        QMessageBox.information(self._w, 'For Technical Assistance', Contact, QMessageBox.Ok)
