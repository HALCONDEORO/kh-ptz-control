#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config_edit_dialogs.py — Sub-diálogos de edición directa usados por ConfigDialog
#
# Pequeños QDialog modales que editan un único valor:
#   - _CamEditDialog  : IP o VISCA ID de una cámara (Platform / Comments)
#   - _ATEMEditDialog : IP del switcher ATEM
#
# Extraídos de config_dialog.py para reducir su tamaño. El comportamiento es
# idéntico; config_dialog.py re-exporta estas clases y _config_yaml_path para
# mantener compatibilidad con `from ui.config_dialog import _CamEditDialog`.

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QWidget, QLineEdit,
)

from config import CAM1, CAM2, is_valid_ip, is_valid_cam_id
from ui.styles import (
    apply_shadow as _apply_shadow,
    close_button_qss,
    error_label_qss,
    input_field_qss,
    primary_button_qss,
    secondary_button_qss,
    BRAND_DARK as _C_BRAND_DARK,
    CARD_BD as _C_CARD_BD,
)


def _config_yaml_path():
    """Return the active config.yaml path, or None if unresolvable."""
    try:
        from runtime.path_resolver import RuntimePathResolver
        return RuntimePathResolver().config_dir / "config.yaml"
    except Exception:
        return None


class _CamEditDialog(QDialog):
    """
    Diálogo de edición directa para IP o VISCA ID de una cámara.
    - Sin diálogo de confirmación previo.
    - Lanza teclado virtual al abrirse.
    - OK → valida, actualiza en memoria, persiste al archivo y cierra solo este diálogo.
    - Cancel → cierra solo este diálogo; ConfigDialog queda abierto.
    """

    def __init__(self, parent, mw, cam_num: int, config_type: str):
        super().__init__(parent)
        self._mw         = mw
        self._cam_num    = cam_num
        self._config_type = config_type

        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        if config_type == 'ip':
            current   = CAM1.ip     if cam_num == 1 else CAM2.ip
            self._validate = is_valid_ip
            field     = 'IP address'
            hint      = 'e.g. 172.16.1.11'
        else:
            current   = CAM1.cam_id if cam_num == 1 else CAM2.cam_id
            self._validate = is_valid_cam_id
            field     = 'VISCA ID'
            hint      = 'e.g. 81'

        self.setWindowTitle(f'Edit {cam_name} {field}')
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(380, 200)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self.setStyleSheet(
            "QDialog { background: white; border: 1px solid #DCDEDB;"
            " border-radius: 14px; }"
        )

        _apply_shadow(self, blur=40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        head = QWidget()
        head.setStyleSheet(
            f"background: white; border-bottom: 1px solid {_C_CARD_BD};"
            " border-top-left-radius: 14px; border-top-right-radius: 14px;"
        )
        head_h = QHBoxLayout(head)
        head_h.setContentsMargins(18, 14, 14, 14)
        head_h.setSpacing(10)

        title_lbl = QLabel(f'{cam_name}  —  {field}')
        title_lbl.setStyleSheet(
            f"font: 700 14px 'Inter Tight', 'Segoe UI'; color: {_C_BRAND_DARK};"
            " background: transparent; border: none;"
        )
        head_h.addWidget(title_lbl, stretch=1)

        btn_x = QPushButton('✕')
        btn_x.setFixedSize(30, 30)
        btn_x.setStyleSheet(close_button_qss())
        btn_x.clicked.connect(self.reject)
        head_h.addWidget(btn_x)
        layout.addWidget(head)

        # Body
        body = QWidget()
        body.setStyleSheet("background: white; border: none;")
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(18, 16, 18, 18)
        body_v.setSpacing(10)

        self._input = QLineEdit(current)
        self._input.setPlaceholderText(hint)
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(input_field_qss())
        self._input.selectAll()
        body_v.addWidget(self._input)

        self._err = QLabel('')
        self._err.setStyleSheet(error_label_qss())
        body_v.addWidget(self._err)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_ok = QPushButton('OK')
        btn_ok.setFixedHeight(40)
        btn_ok.setStyleSheet(primary_button_qss())
        btn_ok.clicked.connect(self._apply)

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet(secondary_button_qss())
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        body_v.addLayout(btn_row)
        layout.addWidget(body)

        QTimer.singleShot(0, self._input.setFocus)

    def _apply(self):
        text = self._input.text().strip()
        if not text:
            self._err.setText('Value cannot be empty.')
            return
        if not self._validate(text):
            self._err.setText(f'Invalid value. Expected format: {self._input.placeholderText()}')
            return

        # All camera config writes go through CameraConfigService (ADR-006): it
        # validates, updates the in-memory config, repoints the live CameraManager
        # and CameraPort, and persists to config.yaml — in one owned place.
        svc = getattr(self._mw, '_camera_config', None)
        if svc is not None:
            if self._config_type == 'ip':
                svc.set_camera_ip(self._cam_num, text)
            else:
                svc.set_camera_visca_id(self._cam_num, text)

        self.accept()


class _ATEMEditDialog(QDialog):
    """Diálogo de edición de IP del switcher ATEM."""

    def __init__(self, parent, mw=None):
        super().__init__(parent)
        self._mw = mw
        import config as _cfg

        self.setWindowTitle('Edit ATEM IP')
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(380, 200)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self.setStyleSheet(
            "QDialog { background: white; border: 1px solid #DCDEDB;"
            " border-radius: 14px; }"
        )

        _apply_shadow(self, blur=40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        head = QWidget()
        head.setStyleSheet(
            f"background: white; border-bottom: 1px solid {_C_CARD_BD};"
            " border-top-left-radius: 14px; border-top-right-radius: 14px;"
        )
        head_h = QHBoxLayout(head)
        head_h.setContentsMargins(18, 14, 14, 14)
        head_h.setSpacing(10)

        title_lbl = QLabel('ATEM Switcher  —  IP address')
        title_lbl.setStyleSheet(
            f"font: 700 14px 'Inter Tight', 'Segoe UI'; color: {_C_BRAND_DARK};"
            " background: transparent; border: none;"
        )
        head_h.addWidget(title_lbl, stretch=1)

        btn_x = QPushButton('✕')
        btn_x.setFixedSize(30, 30)
        btn_x.setStyleSheet(close_button_qss())
        btn_x.clicked.connect(self.reject)
        head_h.addWidget(btn_x)
        layout.addWidget(head)

        # Body
        body = QWidget()
        body.setStyleSheet("background: white; border: none;")
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(18, 16, 18, 18)
        body_v.setSpacing(10)

        self._input = QLineEdit(_cfg.ATEM.ip)
        self._input.setPlaceholderText('e.g. 176.16.1.10')
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(input_field_qss())
        self._input.selectAll()
        body_v.addWidget(self._input)

        self._err = QLabel('')
        self._err.setStyleSheet(error_label_qss())
        body_v.addWidget(self._err)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_ok = QPushButton('OK')
        btn_ok.setFixedHeight(40)
        btn_ok.setStyleSheet(primary_button_qss())
        btn_ok.clicked.connect(self._apply)

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(40)
        btn_cancel.setStyleSheet(secondary_button_qss())
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        body_v.addLayout(btn_row)
        layout.addWidget(body)

        QTimer.singleShot(0, self._input.setFocus)

    def _apply(self):
        text = self._input.text().strip()
        if not text:
            self._err.setText('Value cannot be empty.')
            return
        if not is_valid_ip(text):
            self._err.setText(f'Invalid value. Expected format: {self._input.placeholderText()}')
            return

        # ATEM IP write goes through CameraConfigService (ADR-006).
        svc = getattr(self._mw, '_camera_config', None)
        if svc is not None:
            svc.set_atem_ip(text)

        self.accept()
