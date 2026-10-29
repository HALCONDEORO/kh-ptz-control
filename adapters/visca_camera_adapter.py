#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/visca_camera_adapter.py — VISCA-over-IP CameraPort adapter.
#
# ViscaCameraAdapter implements the CameraPort protocol directly.  It owns
# the VISCA-over-IP TCP connection logic, VISCA byte construction, and speed
# caps.  Application code never imports VISCA protocol classes, sockets, or
# concrete adapter internals.
#
# The mapping of camera IDs to camera indices is owned here; callers never
# handle VISCA addresses or hex cam IDs.

from __future__ import annotations

import binascii
import logging
import socket
import time
import uuid
import threading
from typing import TYPE_CHECKING, Callable

from config import (
    PRESET_MAP, PAN_SPEED_MAX, TILT_SPEED_MAX, ZOOM_DRIVE_MAX,
    VISCA_PORT, SOCKET_TIMEOUT, VISCA_READ_TIMEOUT,
)
from domain.ports import CameraStatus
from domain.supportability import CommandResult
from ptz.visca.parser import contains_final_response, validate_visca_response

if TYPE_CHECKING:
    from ptz.visca import CameraManager

logger = logging.getLogger(__name__)

# camera_id string → camera integer index
_CAMERA_INDEX: dict[str, int] = {
    "cam1": 1,
    "cam2": 2,
}


class ViscaCameraAdapter:
    """VISCA-over-IP CameraPort adapter.

    Satisfies the ports.camera_port.CameraPort Protocol.  Owns all
    VISCA-over-IP TCP socket logic, VISCA byte construction, and speed caps.
    Application code has no direct VISCA dependency.

    camera_id values must be one of: "cam1", "cam2".
    """

    def __init__(
        self,
        manager: "CameraManager",
        cam_configs: "dict[int, tuple[str, str]] | None" = None,
    ) -> None:
        self._mgr = manager
        self._cam_configs = cam_configs
        self._backlight_on: dict[str, bool] = {}
        # Speed caps: watchdog in main_window reduces these on VISCA error (#740).
        self.pan_cap:        int = PAN_SPEED_MAX
        self.tilt_cap:       int = TILT_SPEED_MAX
        self.zoom_drive_cap: int = ZOOM_DRIVE_MAX

    # ── Runtime reconfiguration ───────────────────────────────────────────────

    def update_camera_ip(self, camera_index: int, new_ip: str) -> None:
        """Point a camera at a new IP at runtime (1-based index), no restart.

        The adapter resolves every command's target IP from ``_cam_configs``
        (a snapshot loaded from config.yaml at boot). Without updating it here,
        changing a camera IP in Settings only reached ``config.CAMn`` and the
        CameraManager — the adapter kept sending PTZ/preset commands to the old
        address, so the panel could not move the camera until an app restart.

        The stored VISCA id is preserved. When ``_cam_configs`` is None the
        adapter already reads ``config.CAMn.ip`` live, so this is a no-op.
        """
        if self._cam_configs is None:
            return
        existing = self._cam_configs.get(camera_index)
        if existing is not None:
            cam_id_hex = existing[1]
        else:
            # No prior snapshot for this index — fall back to the live config id.
            from config import CAM1, CAM2  # noqa: PLC0415
            cam_id_hex = (
                CAM1.cam_id if camera_index == 1
                else CAM2.cam_id if camera_index == 2
                else ''
            )
        self._cam_configs[camera_index] = (new_ip, cam_id_hex)

    # ── CameraPort implementation ─────────────────────────────────────────────

    def recall_preset(self, camera_id: str, preset: int) -> CommandResult:
        preset_hex = PRESET_MAP.get(preset)
        if not preset_hex:
            logger.warning("recall_preset: slot %d not in PRESET_MAP", preset)
            return self._result("recall_preset", camera_id, False, None)
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, f"01043f02{preset_hex}ff")
        return self._result("recall_preset", camera_id, ok, t0)

    def save_preset(self, camera_id: str, preset: int) -> CommandResult:
        preset_hex = PRESET_MAP.get(preset)
        if not preset_hex:
            logger.warning("save_preset: slot %d not in PRESET_MAP", preset)
            return self._result("save_preset", camera_id, False, None)
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, f"01043f01{preset_hex}ff")
        return self._result("save_preset", camera_id, ok, t0)

    def move(self, camera_id: str, pan_speed: int, tilt_speed: int) -> CommandResult:
        pan_dir  = 0x02 if pan_speed  > 0 else (0x01 if pan_speed  < 0 else 0x03)
        tilt_dir = 0x01 if tilt_speed > 0 else (0x02 if tilt_speed < 0 else 0x03)
        pan_abs  = 0 if pan_dir  == 0x03 else max(1, min(self.pan_cap,  abs(pan_speed)))
        tilt_abs = 0 if tilt_dir == 0x03 else max(1, min(self.tilt_cap, abs(tilt_speed)))
        ip, cam_id_hex = self._cam_info(camera_id)
        self._send_queued(camera_id, ip, bytes.fromhex(
            cam_id_hex + f"010601{pan_abs:02X}{tilt_abs:02X}{pan_dir:02X}{tilt_dir:02X}FF"
        ), coalesce=True)
        return self._result("move", camera_id, True, None)

    def stop_move(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        # STOP must halt ALL motion, not only pan/tilt. A zoom-stop emitted on
        # zoom release is an ordinary coalesced command and can be lost (queue
        # drain on priority, or still sitting behind an in-flight command), so
        # STOP always sends its own zoom-stop. Pan/tilt stop first, zoom stop
        # second; both priority. CameraWorker.send_priority keeps already
        # queued priority STOP frames, so this ordering is preserved.
        self._send_queued(camera_id, ip, bytes.fromhex(cam_id_hex + "01060100000303FF"), priority=True)
        self._send_queued(camera_id, ip, bytes.fromhex(cam_id_hex + "01040700FF"), priority=True)
        return self._result("stop_move", camera_id, True, None)

    def zoom(self, camera_id: str, speed: int) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        if speed == 0:
            zoom_byte = 0x00
        elif speed > 0:
            zoom_byte = 0x20 | min(self.zoom_drive_cap, abs(speed))
        else:
            zoom_byte = 0x30 | min(self.zoom_drive_cap, abs(speed))
        self._send_queued(camera_id, ip, bytes.fromhex(cam_id_hex + f"010407{zoom_byte:02X}FF"), coalesce=True)
        return self._result("zoom", camera_id, True, None)

    def power_on(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01040002FF")
        return self._result("power_on", camera_id, ok, t0)

    def standby(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01040003FF")
        return self._result("standby", camera_id, ok, t0)

    def home(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        self._send_queued(camera_id, ip, bytes.fromhex(cam_id_hex + "010604FF"), priority=True)
        return self._result("home", camera_id, True, None)

    def focus_auto(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01043802FF")
        return self._result("focus_auto", camera_id, ok, t0)

    def focus_manual(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01043803FF")
        return self._result("focus_manual", camera_id, ok, t0)

    def one_push_af(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01041801FF")
        return self._result("one_push_af", camera_id, ok, t0)

    def brightness_up(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01040D02FF")
        return self._result("brightness_up", camera_id, ok, t0)

    def brightness_down(self, camera_id: str) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, "01040D03FF")
        return self._result("brightness_down", camera_id, ok, t0)

    def backlight_toggle(self, camera_id: str) -> CommandResult:
        current = self._backlight_on.get(camera_id, False)
        new_state = not current
        ip, cam_id_hex = self._cam_info(camera_id)
        cmd_hex = "01043302FF" if new_state else "01043303FF"
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, cmd_hex)
        if ok:
            self._backlight_on[camera_id] = new_state
        return self._result("backlight_toggle", camera_id, ok, t0)

    def zoom_absolute(self, camera_id: str, position: int) -> CommandResult:
        ip, cam_id_hex = self._cam_info(camera_id)
        _zoom_max = 0x4000
        pos = round(max(0, min(100, position)) * _zoom_max / 100)
        p = (pos >> 12) & 0xF
        q = (pos >> 8) & 0xF
        r = (pos >> 4) & 0xF
        s = pos & 0xF
        cmd_hex = f"010447{p:02X}{q:02X}{r:02X}{s:02X}FF"
        t0 = time.monotonic()
        ok = self._send_confirmed(ip, cam_id_hex, cmd_hex)
        return self._result("zoom_absolute", camera_id, ok, t0)

    def stop_all(self) -> CommandResult:
        """Send priority STOP to every configured camera.

        Attempts all cameras regardless of individual failures.
        Returns ok=True only if all cameras succeeded.
        """
        failures: list[str] = []
        for camera_id in list(_CAMERA_INDEX):
            try:
                result = self.stop_move(camera_id)
                if not result.ok:
                    failures.append(camera_id)
            except Exception as exc:
                logger.exception("stop_all: error stopping %s: %s", camera_id, exc)
                failures.append(camera_id)
        ok = len(failures) == 0
        msg = "OK" if ok else f"Failed to stop: {', '.join(failures)}"
        return self._result("stop_all", "all", ok, None, message=msg)

    def cancel_polls(self, camera_id: str) -> CommandResult:
        logger.debug("cancel_polls: no active polls to cancel for %s", camera_id)
        return self._result("cancel_polls", camera_id, True, None)

    def get_status(self, camera_id: str) -> CameraStatus:
        idx = self._index(camera_id)
        return CameraStatus(
            camera_id=camera_id,
            role="main" if idx == 1 else "comments",
            adapter_type="visca",
            connected=True,
            moving=False,
            last_error="",
        )

    def invalidate_zoom(self, camera: int) -> None:
        ip, _ = self._cam_info_by_index(camera)
        self._mgr.invalidate_zoom(ip)

    # ── UI-state synchronisation helpers (read queries) ───────────────────────
    # Called by the UI layer after startup and camera reconnection to sync
    # the zoom slider and AE mode display.  Callbacks are plain Callable with
    # no Qt imports here.

    def refresh_zoom_display(
        self,
        camera_key: int,
        update_slider: "Callable[[int], None]",
    ) -> None:
        """Sync the zoom slider with the camera's current zoom position.

        Uses the CameraManager cache when available.  Otherwise queries the
        camera in a background thread and calls *update_slider(pct)* with the
        result.  *update_slider* must be thread-safe (e.g. a
        QMetaObject.invokeMethod wrapper).
        """
        ip, cam_id_hex = self._cam_info_by_index(camera_key)
        cached = self._mgr.get_zoom(ip)
        if isinstance(cached, int) and cached >= 0:
            update_slider(cached)
            return

        if not self._mgr.zoom_query_try_acquire(ip):
            return  # query already in flight

        def _fetch() -> None:
            try:
                val = self._query_zoom(ip, cam_id_hex)
                if val is not None:
                    from ptz.visca.parser import zoom_to_pct  # noqa: PLC0415
                    pct = zoom_to_pct(val)
                    self._mgr.set_zoom(ip, pct)
                    update_slider(pct)
            finally:
                self._mgr.zoom_query_release(ip)

        threading.Thread(target=_fetch, daemon=True).start()

    def async_refresh_ae_mode(
        self,
        camera_key: int,
        on_exposure_changed: "Callable[[], None]",
    ) -> None:
        """Query AE mode and ExpComp level in a background thread.

        Updates the CameraManager caches (ae_mode, exposure_level) then calls
        *on_exposure_changed()* so the UI can refresh its controls.
        *on_exposure_changed* must be safe to call from a non-Qt thread (e.g.
        a QTimer.singleShot wrapper or a Qt signal).
        """
        ip, cam_id_hex = self._cam_info_by_index(camera_key)
        if not self._mgr.ae_query_try_acquire(ip):
            return  # query already in flight

        def _fetch() -> None:
            try:
                ae_mode, exp_level = self._query_ae_and_exp_comp(ip, cam_id_hex)
                self._mgr.ae_mode[camera_key] = ae_mode
                logger.info("AE mode cam%d (%s): %s", camera_key, ip, ae_mode)
                if exp_level is not None:
                    self._mgr.exposure_level[camera_key] = exp_level
                    logger.info("ExpComp cam%d (%s): %d", camera_key, ip, exp_level)
                on_exposure_changed()
            finally:
                self._mgr.ae_query_release(ip)

        threading.Thread(target=_fetch, daemon=True).start()

    # ── VISCA I/O ─────────────────────────────────────────────────────────────

    def _recv_visca_response(self, sock: "socket.socket") -> bytes:
        """Read from *sock* until a terminal VISCA frame (Completion/Error) or timeout.

        A single recv may capture only the ACK (9x 4y FF), which is NOT terminal:
        cameras frequently send ACK then Completion/Error in separate TCP segments.
        Stopping at the first recv could (a) confirm a command on its ACK before it
        actually completes, or (b) miss an Error frame that arrives afterwards and
        wrongly report success.  Each recv is bounded by the socket timeout and the
        whole read by VISCA_READ_TIMEOUT, so a silent camera cannot block forever.
        """
        buf = b""
        deadline = time.monotonic() + VISCA_READ_TIMEOUT
        while time.monotonic() < deadline:
            try:
                chunk = sock.recv(64)
            except (socket.timeout, socket.error, OSError):
                break
            if not chunk:
                break  # peer closed the connection
            buf += chunk
            if contains_final_response(buf):
                break
        return buf

    def _send_confirmed(self, ip: str, cam_id_hex: str, cmd_hex: str) -> bool:
        """Send a VISCA command over a new TCP connection and validate the response."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.sendall(binascii.unhexlify(cam_id_hex + cmd_hex))
                response = self._recv_visca_response(s)
            ok, reason = validate_visca_response(response)
            if not ok:
                logger.error(
                    "ViscaCameraAdapter._send_confirmed %s: %s (response: %s)",
                    ip, reason, response.hex() if response else "<empty>",
                )
            return ok
        except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
            logger.exception("ViscaCameraAdapter._send_confirmed %s: %s", ip, exc)
            return False

    def _send_queued(
        self,
        camera_id: str,
        ip: str,
        payload: bytes,
        priority: bool = False,
        coalesce: bool = False,
    ) -> None:
        """Enqueue on the CameraWorker (non-blocking)."""
        from ptz.visca import ViscaCommand  # noqa: PLC0415
        idx = self._index(camera_id)
        worker = self._mgr.worker(ip)
        cmd = ViscaCommand(camera=idx, payload=payload, coalesce=coalesce)
        if priority:
            worker.send_priority(cmd)
        else:
            worker.send(cmd)

    # ── Private ───────────────────────────────────────────────────────────────

    def _index(self, camera_id: str) -> int:
        idx = _CAMERA_INDEX.get(camera_id)
        if idx is None:
            raise ValueError(
                f"ViscaCameraAdapter: unknown camera_id {camera_id!r}. "
                f"Known IDs: {sorted(_CAMERA_INDEX)}"
            )
        return idx

    def _cam_info(self, camera_id: str) -> tuple[str, str]:
        """Return (ip, cam_id_hex) for a camera_id string."""
        idx = self._index(camera_id)
        return self._cam_info_by_index(idx)

    def _cam_info_by_index(self, idx: int) -> tuple[str, str]:
        """Return (ip, cam_id_hex) for a camera integer index."""
        if self._cam_configs is not None:
            if idx in self._cam_configs:
                return self._cam_configs[idx]
            raise ValueError(f"ViscaCameraAdapter: camera index {idx} not in cam_configs")
        from config import CAM1, CAM2  # noqa: PLC0415
        if idx == 1:
            return CAM1.ip, CAM1.cam_id
        if idx == 2:
            return CAM2.ip, CAM2.cam_id
        raise ValueError(f"ViscaCameraAdapter: invalid camera index {idx!r}")

    def _query_zoom(self, ip: str, cam_id_hex: str) -> "int | None":
        """VISCA zoom inquiry → raw 0–0x4000, or None on error."""
        from ptz.visca import commands as vcmd  # noqa: PLC0415
        from ptz.visca import parser as vparse  # noqa: PLC0415
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.sendall(vcmd.zoom_inquiry(cam_id_hex))
                data = self._recv_visca_response(s)
            return vparse.zoom(data)
        except (socket.timeout, socket.error, OSError) as exc:
            logger.exception("_query_zoom %s: %s", ip, exc)
            return None

    def _query_ae_and_exp_comp(
        self, ip: str, cam_id_hex: str
    ) -> "tuple[str, int | None]":
        """VISCA AE+ExpComp inquiry in a single TCP session.

        Returns (ae_mode, exp_level) where ae_mode is 'auto'|'manual'|'bright'
        and exp_level is -7..+7 mapped from 0-14, or None.
        """
        from ptz.visca import commands as vcmd  # noqa: PLC0415
        from ptz.visca import parser as vparse  # noqa: PLC0415
        ae_mode = "auto"
        exp_level: "int | None" = None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.sendall(vcmd.ae_mode_inquiry(cam_id_hex))
                ae_data = self._recv_visca_response(s)
                frame = vparse.inquiry_frame(ae_data, payload_len=1)
                if frame is not None:
                    ae_mode = vparse.ae_mode(frame)
                if ae_mode not in ("manual", "bright"):
                    s.sendall(vcmd.exp_comp_inquiry(cam_id_hex))
                    ec_data = self._recv_visca_response(s)
                    frame = vparse.inquiry_frame(ec_data, payload_len=4)
                    if frame is not None:
                        exp_level = vparse.exp_comp_level(frame)
        except (socket.timeout, socket.error, OSError) as exc:
            logger.warning("_query_ae_and_exp_comp %s: %s", ip, exc)
        return ae_mode, exp_level

    def _result(
        self,
        command: str,
        camera_id: str,
        ok: bool,
        t0: float | None,
        message: str | None = None,
    ) -> CommandResult:
        duration_ms = int((time.monotonic() - t0) * 1000) if t0 is not None else None
        if message is None:
            message = "OK" if ok else "Camera error or timeout"
        return CommandResult(
            ok=ok,
            command=command,
            target=camera_id,
            duration_ms=duration_ms,
            correlation_id=str(uuid.uuid4()),
            error_code=None if ok else "CAMERA_ERROR",
            message=message,
        )
