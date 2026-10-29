# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/access_tab.py — ConfigDialog "Access" tab (#894 phase 2)
#
# Operating-mode (camera-operator / sys-admin) switch, the schedule card and
# the authentication card. Extracted from ConfigDialog._build_ui; self ->
# dialog, _panel_layout received as a parameter.

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from application.access_mode_service import AccessModeService
from domain.call_set_policy import OperatingMode
from ui.schedule_dialog import ScheduleDialog
from ui.styles import (
    BRAND_DARK as _C_BRAND_DARK,
    BRAND_MID as _C_BRAND_MID,
    MUTED as _C_MUTED,
)


def build_access_tab(dialog, access_layout, mw, panel_layout):
    """Populate the Access tab: operating mode, schedule and authentication."""
    layout = panel_layout(access_layout, 'Operating Mode')

    _svc: AccessModeService = getattr(mw, '_access_mode_svc', None)

    _mode_lbl = QLabel()
    _mode_lbl.setStyleSheet(
        f"font: 13px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
    )
    layout.addWidget(_mode_lbl)

    # Segmented toggle
    toggle_wrap = QWidget()
    toggle_wrap.setStyleSheet(
        "background: #F0F1EE; border: 1px solid #E2E4E0; border-radius: 10px;"
    )
    toggle_h = QHBoxLayout(toggle_wrap)
    toggle_h.setContentsMargins(4, 4, 4, 4)
    toggle_h.setSpacing(4)

    _SEG_ACTIVE = (
        f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f" stop:0 {_C_BRAND_MID}, stop:1 {_C_BRAND_DARK});"
        " border: none; border-radius: 7px;"
        " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; }"
    )
    _SEG_INACTIVE = (
        "QPushButton { background: transparent; border: none; border-radius: 7px;"
        f" font: 600 13px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED}; padding: 0 4px; }}"
        f"QPushButton:hover {{ background: rgba(46,82,41,0.08); color: {_C_BRAND_DARK}; }}"
    )

    from PyQt5.QtWidgets import QSizePolicy as _QSP_seg
    # Solo dos roles visibles: Operador y Administrador (#roles-simplify).
    btn_cam_op    = QPushButton('Operator')
    btn_sys_admin = QPushButton('Administrator')
    # Equal-share, shrinkable segments (design: grid 1fr columns). A small
    # minimum width lets them fit the fixed dialog whatever the font.
    for _seg_btn in (btn_cam_op, btn_sys_admin):
        _seg_btn.setFixedHeight(40)
        _seg_btn.setMinimumWidth(40)
        _seg_btn.setSizePolicy(_QSP_seg.Expanding, _QSP_seg.Fixed)
        _seg_btn.setCursor(Qt.PointingHandCursor)
    toggle_h.addWidget(btn_cam_op, 1)
    toggle_h.addWidget(btn_sys_admin, 1)
    layout.addWidget(toggle_wrap)

    # Nota de comportamiento
    mode_note = QLabel()
    mode_note.setWordWrap(True)
    mode_note.setStyleSheet(
        f"font: 400 11px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    layout.addWidget(mode_note)

    # Solo dos roles visibles. Los valores legacy/internos se agrupan en
    # uno de los dos: operador (CALL/SET/PTZ/nombres) o administrador (todo).
    _OPERATOR_ROLES = (
        OperatingMode.CAMERA_OPERATOR,
        OperatingMode.BASIC_OPERATOR,
        OperatingMode.OPERATOR,
    )
    _ADMIN_ROLES = (
        OperatingMode.SYSTEM_ADMIN,
        OperatingMode.TECHNICIAN,
        OperatingMode.ADMIN_INSTALLER,
    )
    _OPERATOR_NOTE = (
        'Operator: daily room use. CALL presets, move cameras (PTZ), '
        'move and edit seat names, and reconnect. '
        'Settings are hidden on the main panel.'
    )
    _ADMIN_NOTE = (
        'Administrator: full access — camera operation, layout editing, '
        'camera config, ATEM live switching, diagnostics, backup and reset. '
        'The ⚙ Settings button is visible on the main panel.'
    )

    def _refresh_mode_ui(_new_mode: OperatingMode | None = None):
        if _svc is None:
            _mode_lbl.setText('No disponible')
            return
        current = _new_mode if _new_mode is not None else _svc.mode
        is_admin = current in _ADMIN_ROLES
        is_operator = not is_admin
        _mode_lbl.setText(
            f"Current role: {'Administrator' if is_admin else 'Operator'}"
        )
        btn_cam_op.setStyleSheet(_SEG_ACTIVE if is_operator else _SEG_INACTIVE)
        btn_sys_admin.setStyleSheet(_SEG_ACTIVE if is_admin else _SEG_INACTIVE)
        mode_note.setText(_ADMIN_NOTE if is_admin else _OPERATOR_NOTE)

    def _apply_mode(mode: OperatingMode) -> None:
        if _svc:
            _svc.set_mode(mode)
        mw._right_panel._update_mode_buttons()

    def _set_cam_op():
        _apply_mode(OperatingMode.CAMERA_OPERATOR)

    def _set_sys_admin():
        _apply_mode(OperatingMode.SYSTEM_ADMIN)

    btn_cam_op.clicked.connect(_set_cam_op)
    btn_sys_admin.clicked.connect(_set_sys_admin)

    if _svc:
        _svc.subscribe(_refresh_mode_ui)

    # ── 2-column grid: Authentication (left) + Schedule (right) ───────
    # El Operador entra sin contraseña solo dentro del horario configurado
    # aquí (fuera de horario pide la contraseña de operador, ver login_screen).
    _acc_grid_w = QWidget()
    _acc_grid_w.setStyleSheet("background: transparent;")
    _acc_grid_h = QHBoxLayout(_acc_grid_w)
    _acc_grid_h.setContentsMargins(0, 0, 0, 0)
    _acc_grid_h.setSpacing(10)
    access_layout.addWidget(_acc_grid_w)

    # Left column — Authentication
    _auth_col_w = QWidget()
    _auth_col_w.setStyleSheet("background: transparent;")
    _auth_col_l = QVBoxLayout(_auth_col_w)
    _auth_col_l.setContentsMargins(0, 0, 0, 0)
    _auth_col_l.setSpacing(0)
    _acc_grid_h.addWidget(_auth_col_w, 1)

    # Right column — Schedule
    _sched_col_w = QWidget()
    _sched_col_w.setStyleSheet("background: transparent;")
    _sched_col_l = QVBoxLayout(_sched_col_w)
    _sched_col_l.setContentsMargins(0, 0, 0, 0)
    _sched_col_l.setSpacing(0)
    _acc_grid_h.addWidget(_sched_col_w, 1)

    # ── Schedule card (right column) ──────────────────────────────────
    layout = panel_layout(
        _sched_col_l, 'Schedule',
        badge_text='Auto-bypass', badge_kind='muted',
    )

    sched_desc = QLabel(
        'When the access screen auto-unlocks for operators '
        '(e.g. regular recording sessions). '
        'Admin always requires password entry.'
    )
    sched_desc.setWordWrap(True)
    sched_desc.setStyleSheet(
        f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    layout.addWidget(sched_desc)

    btn_schedule = dialog._btn('Weekly Schedule →', variant='primary', icon='calendar')
    btn_schedule.setToolTip('Configure days and hours when operators can auto-login')
    btn_schedule.clicked.connect(lambda: ScheduleDialog(dialog).exec_())
    layout.addWidget(btn_schedule, 0, Qt.AlignRight)

    # ── Authentication card (left column) ──────────────────────────────
    layout = panel_layout(
        _auth_col_l, 'Authentication',
        badge_text='Password', badge_kind='muted',
        accent=_C_BRAND_MID,
    )

    auth_desc = QLabel('Change the operator unlock password or the administrator password.')
    auth_desc.setWordWrap(True)
    auth_desc.setStyleSheet(
        f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    layout.addWidget(auth_desc)

    btn_pwd = dialog._btn('Change Operator Password →', variant='ghost', icon='lock')
    btn_pwd.setToolTip('Change the operator (entry) login password')
    btn_pwd.clicked.connect(lambda: (mw._dialogs.ChangePassword(), dialog._try_close()))
    layout.addWidget(btn_pwd, 0, Qt.AlignRight)

    btn_admin_pwd = dialog._btn('Change Admin Password →', variant='ghost', icon='lock')
    btn_admin_pwd.setToolTip('Change the administrator password (required for Technician mode)')
    btn_admin_pwd.clicked.connect(lambda: (mw._dialogs.ChangeAdminPassword(), dialog._try_close()))
    layout.addWidget(btn_admin_pwd, 0, Qt.AlignRight)

    # Initial render of the role segmented control + note.
    _refresh_mode_ui()

    access_layout.addStretch()
