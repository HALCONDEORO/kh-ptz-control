# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/cameras_tab.py — ConfigDialog "Cameras" tab (#894 phase 3)
#
# Camera cards (IP/VISCA id via CameraConfigService), camera discovery, the
# connection panel and the second-platform toggle. Extracted from
# ConfigDialog._build_ui; self -> dialog; is_on, sim_active and _panel_layout
# are received as parameters. Camera writes still flow through #893.

from __future__ import annotations

import threading

from config import CAM1, CAM2

from PyQt5.QtCore import QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.config_pages.sections import build_second_platform_section
from ui.config_edit_dialogs import _CamEditDialog
from ui.styles import (
    CARD_BD as _C_CARD_BD,
    icon_button_qss,
    primary_button_qss,
    FIELD_BG as _C_FIELD_BG,
    MUTED as _C_MUTED,
    SECONDARY as _C_SECONDARY,
)


def build_cameras_tab(dialog, cameras_layout, mw, is_on, sim_active, panel_layout):
    """Populate the Cameras tab: cards, discovery, connection, second platform."""
    from ui.config_dialog import _make_pencil_icon  # lazy: avoids an import cycle
    # ── Sección: Camera ───────────────────────────────────────────────
    # Durante una sesión en vivo los campos sensibles (IP / VISCA / ATEM)
    # quedan bloqueados para no cortar el seguimiento de cámaras. En lugar
    # de dejar controles "muertos" sin explicación, mostramos un aviso
    # visible y atenuamos las filas bloqueadas (ver _lock_if_live).
    if is_on:
        cameras_layout.addWidget(dialog._session_lock_banner(
            'Session active — camera IP and VISCA ID are locked. '
            'Stop the session to make changes.'
        ))

    _icon, _icon_sz = _make_pencil_icon(16)

    def _pencil_btn():
        b = QPushButton()
        b.setIcon(_icon)
        b.setIconSize(QSize(_icon_sz, _icon_sz))
        b.setFixedSize(36, 36)
        b.setToolTip('Edit')
        b.setStyleSheet(icon_button_qss())
        return b

    # ── 2-column grid for the two camera cards (design §C) ───────────
    _cam_grid_w = QWidget()
    _cam_grid_w.setStyleSheet("background: transparent;")
    _cam_grid_h = QHBoxLayout(_cam_grid_w)
    _cam_grid_h.setContentsMargins(0, 0, 0, 0)
    _cam_grid_h.setSpacing(10)
    cameras_layout.addWidget(_cam_grid_w)

    # References kept so a re-check after assigning a discovered IP can
    # refresh the card IP value and its Online/Offline badge in place.
    dialog._cam_ip_labels: dict = {}
    dialog._cam_online_badges: dict = {}

    for cam_label, cam_obj, cam_num in (('Platform', CAM1, 1), ('Comments', CAM2, 2)):
        cam_accent = '#9B3A3A' if cam_label == 'Platform' else '#4A8C4A'
        # CAM.check is "Green"/"Red" string (check_all_cameras sets it)
        _cam_check = getattr(cam_obj, 'check', None)
        cam_online = True if _cam_check == 'Green' else (
            False if _cam_check == 'Red' else None
        )

        col_w = QWidget()
        col_w.setStyleSheet("background: transparent;")
        col_v = QVBoxLayout(col_w)
        col_v.setContentsMargins(0, 0, 0, 0)
        col_v.setSpacing(0)
        _cam_grid_h.addWidget(col_w, 1)

        layout, _online_badge = dialog._cam_panel(col_v, cam_label, cam_num,
                                                cam_accent, online=cam_online)
        dialog._cam_online_badges[cam_num] = _online_badge

        ip_row_w = dialog._field_row('IP', cam_obj.ip, on_edit=None)
        _ip_val_lbl = ip_row_w.findChild(QLabel, 'field_value')
        dialog._cam_ip_labels[cam_num] = _ip_val_lbl

        btn_ip = ip_row_w.findChild(QPushButton)
        if btn_ip:
            def _edit_ip(_, n=cam_num, vlbl=_ip_val_lbl):
                _CamEditDialog(dialog, mw, n, 'ip').exec_()
                import config as _cfg
                cam = _cfg.CAM1 if n == 1 else _cfg.CAM2
                if vlbl:
                    vlbl.setText(cam.ip)
            btn_ip.clicked.connect(_edit_ip)
            dialog._lock_if_live(btn_ip, is_on,
                               'Stop the session before changing camera IP',
                               dim_target=ip_row_w)

        layout.addWidget(ip_row_w)

        # Field-row separator (design: `.field-row + .field-row { border-top }`)
        _row_sep = QFrame()
        _row_sep.setFrameShape(QFrame.HLine)
        _row_sep.setFixedHeight(1)
        _row_sep.setStyleSheet("background: #F0F1EE; border: none;")
        layout.addWidget(_row_sep)

        id_row_w = dialog._field_row('VISCA', cam_obj.cam_id, on_edit=None)
        _id_val_lbl = id_row_w.findChild(QLabel, 'field_value')
        btn_id = id_row_w.findChild(QPushButton)
        if btn_id:
            def _edit_id(_, n=cam_num, vlbl=_id_val_lbl):
                _CamEditDialog(dialog, mw, n, 'id').exec_()
                import config as _cfg
                cam = _cfg.CAM1 if n == 1 else _cfg.CAM2
                if vlbl:
                    vlbl.setText(cam.cam_id)
            btn_id.clicked.connect(_edit_id)
            dialog._lock_if_live(btn_id, is_on,
                               'Stop the session before changing the VISCA ID',
                               dim_target=id_row_w)

        layout.addWidget(id_row_w)

    # ── Sección: Camera Discovery ─────────────────────────────────────
    layout = panel_layout(cameras_layout, 'Camera Discovery')

    # Micro description (matches design spec)
    disc_desc = QLabel('Discover PTZ cameras on the local subnet via VISCA-over-IP broadcast.')
    disc_desc.setStyleSheet(
        f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED}; background: transparent;"
    )
    disc_desc.setWordWrap(True)
    layout.addWidget(disc_desc)

    # Etiqueta de estado del escaneo
    disc_status = QLabel('')
    disc_status.setStyleSheet(
        f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_SECONDARY}; padding: 2px 0; background: transparent;"
    )
    disc_status.setWordWrap(True)
    layout.addWidget(disc_status)

    # Contenedor con scroll para los resultados (máx 110 px visible)
    disc_inner = QWidget()
    disc_inner.setStyleSheet("background: transparent;")
    disc_layout = QVBoxLayout(disc_inner)
    disc_layout.setContentsMargins(0, 0, 0, 0)
    disc_layout.setSpacing(4)

    disc_scroll = QScrollArea()
    disc_scroll.setWidgetResizable(True)
    disc_scroll.setFixedHeight(0)   # oculto hasta que haya resultados
    disc_scroll.setFrameShape(QFrame.NoFrame)
    disc_scroll.setStyleSheet("background: transparent;")
    disc_scroll.setWidget(disc_inner)
    layout.addWidget(disc_scroll)

    btn_scan = dialog._btn('Scan Network', variant='primary', icon='search')
    layout.addWidget(btn_scan, 0, Qt.AlignRight)

    # ── Helpers de asignación ─────────────────────────────────────────

    # Cross-thread bridge for the post-assignment connectivity re-check
    # (check_camera does a blocking socket connect — must run off the GUI
    # thread, result marshalled back here).
    class _CamCheckSignal(QObject):
        done = pyqtSignal(int, bool)   # (cam_num, online)

    dialog._cam_check_sig = _CamCheckSignal()

    def _apply_cam_check(cam_num: int, online: bool):
        if not dialog.isVisible():
            return
        dialog._set_online_badge(dialog._cam_online_badges.get(cam_num), online)
        strip = getattr(dialog, '_strip_cam', {}).get(cam_num)
        if strip:
            dot, val, role = strip
            try:
                dialog._set_led(dot, 'green' if online else 'red')
                val.setText(role if online else 'Offline')
            except RuntimeError:
                pass

    dialog._cam_check_sig.done.connect(_apply_cam_check)

    def _recheck_camera(cam_num: int):
        import config as _cfg
        from config import check_camera
        cam = _cfg.CAM1 if cam_num == 1 else _cfg.CAM2
        try:
            ok = bool(check_camera(cam.ip, cam.cam_id))
        except Exception:  # noqa: BLE001
            ok = False
        cam.check = 'Green' if ok else 'Red'
        dialog._cam_check_sig.done.emit(cam_num, ok)

    def _apply_ip(ip: str, cam_num: int):
        """Assign a discovered IP: update memory, live link, config.yaml and UI.

        Unlike before, this no longer requires an app restart — the camera
        worker is retired and reconnected on the new IP, the card IP value
        and the Online/Offline badges refresh in place, and feedback is a
        toast instead of a modal that hid behind the settings dialog.
        """
        # Central owner does memory + live CameraManager/CameraPort repoint +
        # config.yaml persistence in one place (ADR-006). code == "OK" means
        # persisted; a partial result means applied for this session only.
        svc = getattr(mw, '_camera_config', None)
        result = svc.set_camera_ip(cam_num, ip) if svc is not None else None
        persisted = bool(result and result.ok and result.code == "OK")

        # Reflect the new IP in the camera card immediately.
        lbl = dialog._cam_ip_labels.get(cam_num)
        if lbl:
            lbl.setText(ip)

        role = 'Platform' if cam_num == 1 else 'Comments'
        if persisted:
            dialog._toast(f'{role} camera → {ip} assigned and saved')
        else:
            dialog._toast(f'{role} camera → {ip} assigned (this session only)',
                        kind='warn')

        # Refresh the connectivity badges. In simulation the link is always
        # up; otherwise re-check off the GUI thread.
        if sim_active:
            dialog._cam_check_sig.done.emit(cam_num, True)
        else:
            threading.Thread(
                target=_recheck_camera, args=(cam_num,), daemon=True
            ).start()

    # Assign buttons keyed by role so assigning one IP resets the same-role
    # buttons on other discovered rows (only one IP per role).
    dialog._disc_buttons: dict = {1: [], 2: []}

    def _assign(ip: str, cam_num: int, this_btn):
        role = 'Platform' if cam_num == 1 else 'Comments'
        for b in dialog._disc_buttons.get(cam_num, []):
            try:
                b.setEnabled(True)
                b.setText(f'→ {role}')
            except RuntimeError:
                pass
        _apply_ip(ip, cam_num)
        this_btn.setText(f'✓ {role}')
        this_btn.setEnabled(False)

    def _clear_results():
        while disc_layout.count():
            child = disc_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_results(found: list):
        _clear_results()
        dialog._disc_buttons = {1: [], 2: []}
        if not found:
            disc_status.setText('No VISCA devices found on the network.')
            disc_scroll.setFixedHeight(0)
        else:
            disc_status.setText(f'{len(found)} device(s) found on the network:')
            for ip in found:
                row_w = QWidget()
                row_w.setStyleSheet(
                    f"background: {_C_FIELD_BG}; border-radius: 8px;"
                    f" border: 1px solid {_C_CARD_BD};"
                )
                row_h = QHBoxLayout(row_w)
                row_h.setContentsMargins(10, 4, 6, 4)
                row_h.setSpacing(8)

                lbl = QLabel(ip)
                lbl.setStyleSheet(
                    "font: 600 13px 'Consolas', 'Segoe UI'; color: #111;"
                    " background: transparent;"
                )
                row_h.addWidget(lbl)
                row_h.addStretch()

                btn_p = QPushButton('→ Platform')
                btn_p.setFixedHeight(30)
                btn_p.setFixedWidth(104)
                btn_p.setStyleSheet(primary_button_qss(radius=7, font_px=12))
                btn_p.clicked.connect(
                    lambda _=False, _ip=ip, _b=btn_p: _assign(_ip, 1, _b)
                )
                row_h.addWidget(btn_p)
                dialog._disc_buttons[1].append(btn_p)

                btn_c = QPushButton('→ Comments')
                btn_c.setFixedHeight(30)
                btn_c.setFixedWidth(104)
                btn_c.setStyleSheet(primary_button_qss(
                    radius=7, font_px=12,
                    grad_start='#C0141F', grad_end='#8E0F18', pressed='#6E080F',
                ))
                btn_c.clicked.connect(
                    lambda _=False, _ip=ip, _b=btn_c: _assign(_ip, 2, _b)
                )
                row_h.addWidget(btn_c)
                dialog._disc_buttons[2].append(btn_c)

                disc_layout.addWidget(row_w)

            # Altura: máx 4 filas visibles para no invadir el resto.
            disc_scroll.setFixedHeight(min(len(found), 4) * 42)

        btn_scan.setEnabled(True)
        btn_scan.setText('Scan Network')

    # ── Qt signal bridge: discover_cameras() runs in a worker thread ──
    # All UI updates must happen on the GUI thread. QTimer.singleShot()
    # fired from a non-Qt thread never executes (that thread has no event
    # loop), which left the Scan button stuck on "Scanning…" forever. A
    # queued cross-thread signal marshals the result back correctly.
    class _ScanSignals(QObject):
        finished = pyqtSignal(object)

    _scan_sig = _ScanSignals()

    def _on_scan_finished(found):
        if not dialog.isVisible():
            return
        _show_results(found)

    _scan_sig.finished.connect(_on_scan_finished)

    def _run_scan():
        from application.camera_discovery import discover_cameras
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            found = discover_cameras()
        except Exception as exc:  # noqa: BLE001
            _log.error("Camera scan failed: %s", exc)
            found = []
        _scan_sig.finished.emit(found)

    def _on_scan_clicked():
        _clear_results()
        disc_scroll.setFixedHeight(0)
        disc_status.setText('Scanning network…')
        btn_scan.setEnabled(False)
        btn_scan.setText('Scanning…')
        threading.Thread(target=_run_scan, daemon=True).start()

    btn_scan.clicked.connect(_on_scan_clicked)

    # ── Sección: Connection ───────────────────────────────────────────
    layout = panel_layout(cameras_layout, 'Connection')

    btn_reconnect_cams = dialog._btn('Reconnect Cameras', variant='primary', icon='sync')
    btn_reconnect_cams.setToolTip('Close and reopen TCP connections to both cameras')

    def _on_reconnect_cameras():
        cameras = getattr(mw, '_cameras', None)
        if cameras is None:
            return
        cameras.reconnect_all()
        btn_reconnect_cams.setEnabled(False)
        btn_reconnect_cams.setText('Reconnecting…')
        QTimer.singleShot(2000, lambda: (
            btn_reconnect_cams.setEnabled(True),
            btn_reconnect_cams.setText('Reconnect Cameras'),
        ))

    btn_reconnect_cams.clicked.connect(_on_reconnect_cameras)
    layout.addWidget(btn_reconnect_cams, 0, Qt.AlignRight)

    # ── Sección: Second Platform ─────────────────────────────────────
    layout = panel_layout(cameras_layout, 'Second Platform')
    build_second_platform_section(dialog, layout, mw)

    cameras_layout.addStretch()
