#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ptz/visca/commands.py — Constructores puros de comandos VISCA
#
# Todas las funciones son puras: reciben parámetros, devuelven bytes.
# Sin efectos secundarios, sin red, sin Qt.
#
# Formato general:   8x  <category>  <command bytes>  FF
#   8x  = dirección de la cámara (cam_id ya lo incluye)
#   FF  = terminador de trama

from __future__ import annotations

from .types import PanDir, TiltDir, ZOOM_MAX


# ─────────────────────────────────────────────────────────────────────────────
#  Alimentación
# ─────────────────────────────────────────────────────────────────────────────
# CAM_Power: 8x 01 04 00 02 FF (on) / 8x 01 04 00 03 FF (standby)

def power_on(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "01040002FF")


def power_off(cam_id: str) -> bytes:
    """Pone la cámara en standby."""
    return bytes.fromhex(cam_id + "01040003FF")


def power_inquiry(cam_id: str) -> bytes:
    """CAM_Power_Inq — respuesta: y0 50 02 FF (on) / y0 50 03 FF (standby)."""
    return bytes.fromhex(cam_id + "090400FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Pan / Tilt
# ─────────────────────────────────────────────────────────────────────────────
# Formato: 8x 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF

def pan_tilt(cam_id: str, pan_spd: int, tilt_spd: int,
             pan_dir: PanDir, tilt_dir: TiltDir) -> bytes:
    return bytes.fromhex(
        cam_id + f"010601{pan_spd:02X}{tilt_spd:02X}{pan_dir:02X}{tilt_dir:02X}FF"
    )


def pan_tilt_stop(cam_id: str) -> bytes:
    """Para pan/tilt enviando velocidad 0 en ambos ejes y dirección STOP."""
    return bytes.fromhex(cam_id + "01060100000303FF")


def home(cam_id: str) -> bytes:
    """Mueve la cámara a su posición Home."""
    return bytes.fromhex(cam_id + "010604FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Zoom
# ─────────────────────────────────────────────────────────────────────────────
# Zoom absoluto: 8x 01 04 47 0p 0q 0r 0s FF
#   pqrs = 4 nibbles del valor (0x0000 wide – 0x4000 tele)
# Zoom inquiry:  8x 09 04 47 FF

def zoom_absolute(cam_id: str, pct: int) -> bytes:
    """Construye comando de zoom absoluto a partir de porcentaje 0–100."""
    pct = max(0, min(100, int(pct)))
    pos = round(pct * ZOOM_MAX / 100)
    p = (pos >> 12) & 0xF
    q = (pos >>  8) & 0xF
    r = (pos >>  4) & 0xF
    s =  pos        & 0xF
    return bytes.fromhex(cam_id + f"010447{p:02X}{q:02X}{r:02X}{s:02X}FF")


def zoom_inquiry(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "090447FF")


# ─────────────────────────────────────────────────────────────────────────────
#  PTZ Position Inquiry
# ─────────────────────────────────────────────────────────────────────────────

def ptz_position_inquiry(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "090612FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Focus
# ─────────────────────────────────────────────────────────────────────────────

def focus_auto(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "01043802FF")


def focus_manual(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "01043803FF")


def one_push_af(cam_id: str) -> bytes:
    """Dispara un autofocus puntual (One-Push AF)."""
    return bytes.fromhex(cam_id + "01041801FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Exposición / Brillo
# ─────────────────────────────────────────────────────────────────────────────
# CAM_Bright (modo manual/bright):  01 04 0D 02/03 FF
# CAM_ExpComp (modo auto):          01 04 0E 02/03 FF
# CAM_ExpCompMode on:               01 04 3E 02 FF  (activar antes de ajustar)
# CAM_AE_ModeInq:                   09 04 39 FF
# CAM_ExpCompPosInq:                09 04 4E FF

def ae_mode_inquiry(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "090439FF")


def exp_comp_inquiry(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "09044EFF")


def exp_comp_on(cam_id: str) -> bytes:
    """Activa el modo ExpComp antes de ajustar en modo auto."""
    return bytes.fromhex(cam_id + "01043E02FF")


def brightness_up_direct(cam_id: str) -> bytes:
    """CAM_Bright Up — para modos manual/bright."""
    return bytes.fromhex(cam_id + "01040D02FF")


def brightness_down_direct(cam_id: str) -> bytes:
    """CAM_Bright Down — para modos manual/bright."""
    return bytes.fromhex(cam_id + "01040D03FF")


def exp_comp_up(cam_id: str) -> bytes:
    """CAM_ExpComp Up — para modo auto."""
    return bytes.fromhex(cam_id + "01040E02FF")


def exp_comp_down(cam_id: str) -> bytes:
    """CAM_ExpComp Down — para modo auto."""
    return bytes.fromhex(cam_id + "01040E03FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Backlight
# ─────────────────────────────────────────────────────────────────────────────

def backlight_on(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "01043302FF")


def backlight_off(cam_id: str) -> bytes:
    return bytes.fromhex(cam_id + "01043303FF")


# ─────────────────────────────────────────────────────────────────────────────
#  Presets
# ─────────────────────────────────────────────────────────────────────────────
# Formato: 8x 01 04 3F 01/02 <pp> FF
#   01 = guardar, 02 = llamar
#   pp = número de preset en hex (ya calculado por PRESET_MAP)

def preset_recall(cam_id: str, preset_hex: str) -> bytes:
    return bytes.fromhex(cam_id + f"01043f02{preset_hex}ff")


def preset_save(cam_id: str, preset_hex: str) -> bytes:
    return bytes.fromhex(cam_id + f"01043f01{preset_hex}ff")
