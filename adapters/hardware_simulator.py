#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# hardware_simulator.py — Simulador de hardware PTZ + ATEM (módulo interno)
#
# Se importa desde main_window.py cuando sim_ip_backup.json existe.
# Los servidores VISCA corren como threads daemon dentro del proceso de la app.
# El estado de las cámaras se muestra en el panel derecho (right_panel.py).
# El evento ATEM se dispara desde config_dialog.py (botón Run Test, punto ATEM).

from __future__ import annotations

import socket
import threading
import queue
import logging

logger = logging.getLogger(__name__)

VISCA_PORT = 5678


# ═══════════════════════════════════════════════════════════════════════════════
#  ESTADO DE CÁMARA SIMULADA
# ═══════════════════════════════════════════════════════════════════════════════

class SimCamera:
    """Estado interno de una cámara PTZ simulada."""

    def __init__(self, name: str):
        self.name       = name
        self.zoom       = 0        # 0–16384 (0x4000)
        self.focus_auto = True
        self.exposure   = 0
        self.backlight  = False
        self.presets: dict[int, tuple[int, int, int]] = {}
        self.pan        = 0
        self.tilt       = 0
        self.pan_spd    = 0
        self.tilt_spd   = 0
        self._lock      = threading.RLock()  # reentrant: evita deadlock si un método llama a otro dentro del lock
        self.cmd_count  = 0
        self.last_cmd   = ""

    def zoom_pct(self) -> int:
        with self._lock:
            return int(self.zoom / 0x4000 * 100)


# ═══════════════════════════════════════════════════════════════════════════════
#  PARSEO Y RESPUESTA VISCA
# ═══════════════════════════════════════════════════════════════════════════════

def _nibbles_to_bytes(val: int) -> bytes:
    return bytes([
        (val >> 12) & 0x0F,
        (val >>  8) & 0x0F,
        (val >>  4) & 0x0F,
        (val      ) & 0x0F,
    ])

def _bytes_to_val(data: bytes, offset: int) -> int:
    return (
        (data[offset    ] & 0x0F) << 12 |
        (data[offset + 1] & 0x0F) <<  8 |
        (data[offset + 2] & 0x0F) <<  4 |
        (data[offset + 3] & 0x0F)
    )


def handle_visca(data: bytes, cam: SimCamera) -> bytes:
    """Parsea un frame VISCA y devuelve la respuesta adecuada."""
    if len(data) < 3:
        return b""

    ACK      = bytes([0x90, 0x41, 0xFF])
    COMP     = bytes([0x90, 0x51, 0xFF])
    ACK_COMP = ACK + COMP

    msg_type = data[1] if len(data) > 1 else 0

    with cam._lock:
        cam.cmd_count += 1

        # ── INQUIRIES (0x09) ─────────────────────────────────────────────────
        if msg_type == 0x09 and len(data) >= 4:
            cat = data[2]
            cmd = data[3]

            if cat == 0x04 and cmd == 0x00:   # Power Status
                cam.last_cmd = "INQ:Power"
                return bytes([0x90, 0x50, 0x02, 0xFF])

            if cat == 0x04 and cmd == 0x47:   # Zoom Position
                cam.last_cmd = "INQ:Zoom"
                nibs = _nibbles_to_bytes(cam.zoom)
                return bytes([0x90, 0x50]) + nibs + bytes([0xFF])

            if cat == 0x04 and cmd == 0x38:   # Focus Mode
                cam.last_cmd = "INQ:Focus"
                return bytes([0x90, 0x50, 0x02 if cam.focus_auto else 0x03, 0xFF])

            if cat == 0x04 and cmd == 0x39:   # Exposure Mode
                cam.last_cmd = "INQ:Exposure"
                return bytes([0x90, 0x50, 0x00, 0xFF])

            if cat == 0x04 and cmd == 0x33:   # Backlight
                cam.last_cmd = "INQ:Backlight"
                return bytes([0x90, 0x50, 0x02 if cam.backlight else 0x03, 0xFF])

            if cat == 0x06 and cmd == 0x12:   # PTZ Position
                cam.last_cmd = "INQ:PTZPos"
                pan_nibs  = _nibbles_to_bytes(cam.pan  & 0xFFFF)
                tilt_nibs = _nibbles_to_bytes(cam.tilt & 0xFFFF)
                return bytes([0x90, 0x58]) + pan_nibs + tilt_nibs + bytes([0xFF])

            cam.last_cmd = f"INQ:?{cat:02X}{cmd:02X}"
            return bytes([0x90, 0x60, 0x02, 0xFF])

        # ── COMANDOS (0x01) ──────────────────────────────────────────────────
        if msg_type == 0x01 and len(data) >= 4:
            cat = data[2]
            cmd = data[3]

            # Pan/Tilt Drive
            if cat == 0x06 and cmd == 0x01 and len(data) >= 9:
                pan_spd  = data[4]
                tilt_spd = data[5]
                pan_dir  = data[6]
                tilt_dir = data[7]
                dirs = {0x01: "L", 0x02: "R", 0x03: "."}
                td   = {0x01: "U", 0x02: "D", 0x03: "."}
                cam.last_cmd = f"Move {dirs.get(pan_dir,'?')}{td.get(tilt_dir,'?')} pan={pan_spd} tilt={tilt_spd}"
                moving = pan_dir != 0x03 or tilt_dir != 0x03
                cam.pan_spd  = pan_spd  if moving else 0
                cam.tilt_spd = tilt_spd if moving else 0
                step = pan_spd * 5
                if pan_dir == 0x01:
                    cam.pan -= step
                elif pan_dir == 0x02:
                    cam.pan += step
                step = tilt_spd * 5
                if tilt_dir == 0x01:
                    cam.tilt += step
                elif tilt_dir == 0x02:
                    cam.tilt -= step
                return ACK_COMP

            # Pan/Tilt Home
            if cat == 0x06 and cmd == 0x04:
                cam.pan = 0
                cam.tilt = 0
                cam.last_cmd = "Home"
                return ACK_COMP

            # Zoom Absolute
            if cat == 0x04 and cmd == 0x47 and len(data) >= 9:
                cam.zoom = _bytes_to_val(data, 4)
                cam.last_cmd = f"Zoom={int(cam.zoom / 0x4000 * 100)}%"
                return ACK_COMP

            # Zoom Stop
            if cat == 0x04 and cmd == 0x07:
                cam.last_cmd = "ZoomStop"
                return ACK_COMP

            # Focus Mode
            if cat == 0x04 and cmd == 0x38:
                if len(data) >= 5:
                    cam.focus_auto = (data[4] == 0x02)
                    cam.last_cmd = f"Focus={'AUTO' if cam.focus_auto else 'MAN'}"
                return ACK_COMP

            # Focus One-Push
            if cat == 0x04 and cmd == 0x18:
                cam.last_cmd = "AF OnePush"
                return ACK_COMP

            # Exposure Mode
            if cat == 0x04 and cmd == 0x39:
                cam.last_cmd = "ExposureMode"
                return ACK_COMP

            # Brightness
            if cat == 0x04 and cmd == 0x0E and len(data) >= 5:
                if data[4] == 0x02:
                    cam.exposure += 1
                    cam.last_cmd = f"Bright+{cam.exposure}"
                elif data[4] == 0x03:
                    cam.exposure -= 1
                    cam.last_cmd = f"Bright{cam.exposure:+d}"
                return ACK_COMP

            # Backlight
            if cat == 0x04 and cmd == 0x33 and len(data) >= 5:
                cam.backlight = (data[4] == 0x02)
                cam.last_cmd = f"Backlight={'ON' if cam.backlight else 'OFF'}"
                return ACK_COMP

            # Preset Recall / Save
            if cat == 0x04 and cmd == 0x3F and len(data) >= 6:
                mode   = data[4]
                preset = data[5]
                if mode == 0x02:
                    cam.last_cmd = f"Recall #{preset}"
                    if preset in cam.presets:
                        cam.zoom, cam.pan, cam.tilt = cam.presets[preset]
                elif mode == 0x01:
                    cam.presets[preset] = (cam.zoom, cam.pan, cam.tilt)
                    cam.last_cmd = f"Save #{preset}"
                return ACK_COMP

            # Set Address / IF_Clear (broadcast)
            if data[0] == 0x88 and cat == 0x30:
                cam.last_cmd = "SetAddress"
                return bytes([0x90, 0x30, 0x02, 0xFF])
            if data[0] == 0x88 and cat == 0x01:
                cam.last_cmd = "IF_Clear"
                return bytes([0x90, 0x01, 0xFF])

            # Comando 0x01 no reconocido — responder ACK+COMP para no bloquear al worker
            cam.last_cmd = f"CMD:{cat:02X}{cmd:02X}"
            logger.debug("SimVISCA: unhandled command cat=%02X cmd=%02X frame=%s",
                         cat, cmd, data.hex())
            return ACK_COMP

        # Frame con msg_type no reconocido — responder error sintáctico VISCA
        cam.last_cmd = f"UNK:{data.hex()[:12]}"
        logger.debug("SimVISCA: unknown frame %s", data.hex())
        return bytes([0x90, 0x60, 0x02, 0xFF])


# ═══════════════════════════════════════════════════════════════════════════════
#  SERVIDOR TCP VISCA
# ═══════════════════════════════════════════════════════════════════════════════

class ViscaServer:
    """Servidor TCP en ip:port que emula una cámara PTZ. Corre en threads daemon."""

    def __init__(self, ip: str, cam: SimCamera, port: int = VISCA_PORT):
        self.ip   = ip
        self.port = port
        self.cam  = cam
        self._running = False
        self._server_sock: socket.socket | None = None

    def start(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.ip, self.port))
            s.listen(5)
            self._server_sock = s
            self._running = True
            threading.Thread(target=self._accept_loop, daemon=True,
                             name=f"ViscaSrv-{self.ip}").start()
            logger.info("SimVISCA: listening on %s:%d (%s)", self.ip, self.port, self.cam.name)
            return True
        except OSError as e:
            logger.exception("SimVISCA: could not bind %s:%d — %s", self.ip, self.port, e)
            return False

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,),
                                 daemon=True).start()
            except OSError:
                break

    def _handle_client(self, conn: socket.socket):
        conn.settimeout(30)
        buf = b""
        try:
            while True:
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf += chunk
                while b"\xFF" in buf:
                    idx   = buf.index(b"\xFF")
                    frame = buf[:idx + 1]
                    buf   = buf[idx + 1:]
                    resp  = handle_visca(frame, self.cam)
                    if resp:
                        conn.sendall(resp)
        except (socket.timeout, socket.error, OSError):
            pass
        except Exception as exc:
            logger.warning("SimVISCA: handler error (%s): %s", self.ip, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
#  ESTADO GLOBAL (asignado por main_window al arrancar en modo sim)
# ═══════════════════════════════════════════════════════════════════════════════

active_cam1: "SimCamera | None" = None
active_cam2: "SimCamera | None" = None

# Cola para eventos ATEM → ATEMMonitor (modo sim)
atem_event_queue: queue.Queue = queue.Queue()

# Cola para eventos de Picture-in-Picture → ATEMMonitor (modo sim)
# Valores: "pip_on" | "pip_off:<source>"  (ej. "pip_on:2" activa PiP con fuente 2)
pip_event_queue: queue.Queue = queue.Queue()
