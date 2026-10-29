#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_visca_commands_full.py — Verificación de bytes exactos de todos los constructores VISCA
#
# Sin Qt, sin red, sin threading: funciones puras → bytes deterministas.

from __future__ import annotations


from ptz.visca import commands as vcmd
from ptz.visca.types import PanDir, TiltDir, ZOOM_MAX

C1 = '81'   # cam_id cámara 1
C2 = '82'   # cam_id cámara 2


def _b(cam: str, body: str) -> bytes:
    """Construye bytes esperados: cam_id + body (hex sin espacios)."""
    return bytes.fromhex(cam + body.replace(' ', ''))


# ─────────────────────────────────────────────────────────────────────────────
#  Alimentación
# ─────────────────────────────────────────────────────────────────────────────

class TestPowerCommands:
    def test_power_on_cam1(self):
        assert vcmd.power_on(C1) == _b(C1, '01040002FF')

    def test_power_on_cam2(self):
        assert vcmd.power_on(C2) == _b(C2, '01040002FF')

    def test_power_off_cam1(self):
        assert vcmd.power_off(C1) == _b(C1, '01040003FF')

    def test_power_on_off_differ(self):
        assert vcmd.power_on(C1) != vcmd.power_off(C1)

    def test_power_on_terminates_ff(self):
        assert vcmd.power_on(C1)[-1] == 0xFF

    def test_power_off_terminates_ff(self):
        assert vcmd.power_off(C1)[-1] == 0xFF


# ─────────────────────────────────────────────────────────────────────────────
#  Pan / Tilt
# ─────────────────────────────────────────────────────────────────────────────

class TestPanTiltCommandsExact:
    def test_pan_right_tilt_up(self):
        # 81 01 06 01 05(pan_spd) 03(tilt_spd) 02(Right) 01(Up) FF
        expected = _b(C1, '01060105030201FF')
        assert vcmd.pan_tilt(C1, 5, 3, PanDir.RIGHT, TiltDir.UP) == expected

    def test_pan_left_tilt_down(self):
        expected = _b(C1, '010601' + '18' + '14' + '01' + '02' + 'FF')
        assert vcmd.pan_tilt(C1, 0x18, 0x14, PanDir.LEFT, TiltDir.DOWN) == expected

    def test_pan_stop_tilt_stop(self):
        # velocidades 0, dirección STOP en ambos ejes
        expected = _b(C1, '010601' + '00' + '00' + '03' + '03' + 'FF')
        assert vcmd.pan_tilt(C1, 0, 0, PanDir.STOP, TiltDir.STOP) == expected

    def test_pan_tilt_stop_exact(self):
        assert vcmd.pan_tilt_stop(C1) == _b(C1, '01060100000303FF')

    def test_pan_tilt_stop_cam2(self):
        assert vcmd.pan_tilt_stop(C2) == _b(C2, '01060100000303FF')

    def test_home_exact(self):
        assert vcmd.home(C1) == _b(C1, '010604FF')

    def test_home_cam2(self):
        assert vcmd.home(C2) == _b(C2, '010604FF')

    def test_direction_encoding_all_combos(self):
        """Los 9 combos pan×tilt colocan los bytes de dirección en posición -3/-2."""
        for pan_d in PanDir:
            for tilt_d in TiltDir:
                b = vcmd.pan_tilt(C1, 1, 1, pan_d, tilt_d)
                assert b[-3] == pan_d.value
                assert b[-2] == tilt_d.value


# ─────────────────────────────────────────────────────────────────────────────
#  Zoom
# ─────────────────────────────────────────────────────────────────────────────

class TestZoomCommandsExact:
    def test_zoom_0pct(self):
        # pos=0: p=q=r=s=0
        assert vcmd.zoom_absolute(C1, 0) == _b(C1, '010447' + '00'*4 + 'FF')

    def test_zoom_100pct(self):
        # pos=0x4000: p=4, q=0, r=0, s=0
        assert vcmd.zoom_absolute(C1, 100) == _b(C1, '010447' + '04000000' + 'FF')

    def test_zoom_50pct(self):
        # pos=0x2000: p=2, q=0, r=0, s=0
        assert vcmd.zoom_absolute(C1, 50) == _b(C1, '010447' + '02000000' + 'FF')

    def test_zoom_25pct(self):
        # pos=0x1000: p=1, q=0, r=0, s=0
        assert vcmd.zoom_absolute(C1, 25) == _b(C1, '010447' + '01000000' + 'FF')

    def test_zoom_75pct(self):
        # pos=round(0.75*16384)=12288=0x3000: p=3, q=0, r=0, s=0
        assert vcmd.zoom_absolute(C1, 75) == _b(C1, '010447' + '03000000' + 'FF')

    def test_zoom_nibble_encoding_mixed(self):
        """Verificar que cada nibble del valor VISCA se codifica en su propio byte."""
        # Construir directamente el valor y comparar nibble a nibble
        pct = 50
        cmd = vcmd.zoom_absolute(C1, pct)
        pos = round(pct * ZOOM_MAX / 100)
        assert cmd[-5] == (pos >> 12) & 0xF
        assert cmd[-4] == (pos >>  8) & 0xF
        assert cmd[-3] == (pos >>  4) & 0xF
        assert cmd[-2] ==  pos        & 0xF

    def test_zoom_inquiry_exact(self):
        assert vcmd.zoom_inquiry(C1) == _b(C1, '090447FF')

    def test_ptz_position_inquiry_exact(self):
        assert vcmd.ptz_position_inquiry(C1) == _b(C1, '090612FF')

    def test_zoom_cam2_prefix(self):
        assert vcmd.zoom_absolute(C2, 50)[0] == 0x82

    def test_zoom_clamp_negative(self):
        assert vcmd.zoom_absolute(C1, -10) == vcmd.zoom_absolute(C1, 0)

    def test_zoom_clamp_over_100(self):
        assert vcmd.zoom_absolute(C1, 150) == vcmd.zoom_absolute(C1, 100)

    def test_zoom_clamp_float_coerced(self):
        assert vcmd.zoom_absolute(C1, 50.9) == vcmd.zoom_absolute(C1, 50)


# ─────────────────────────────────────────────────────────────────────────────
#  Focus
# ─────────────────────────────────────────────────────────────────────────────

class TestFocusCommandsExact:
    def test_focus_auto_exact(self):
        assert vcmd.focus_auto(C1) == _b(C1, '01043802FF')

    def test_focus_manual_exact(self):
        assert vcmd.focus_manual(C1) == _b(C1, '01043803FF')

    def test_one_push_af_exact(self):
        assert vcmd.one_push_af(C1) == _b(C1, '01041801FF')

    def test_focus_auto_manual_differ(self):
        assert vcmd.focus_auto(C1) != vcmd.focus_manual(C1)

    def test_focus_auto_manual_opcode_byte(self):
        # Byte antes del terminador (operando): auto=02, manual=03
        assert vcmd.focus_auto(C1)[-2]   == 0x02
        assert vcmd.focus_manual(C1)[-2] == 0x03


# ─────────────────────────────────────────────────────────────────────────────
#  Exposición y brillo
# ─────────────────────────────────────────────────────────────────────────────

class TestExposureCommandsExact:
    def test_ae_mode_inquiry_exact(self):
        assert vcmd.ae_mode_inquiry(C1) == _b(C1, '090439FF')

    def test_exp_comp_inquiry_exact(self):
        assert vcmd.exp_comp_inquiry(C1) == _b(C1, '09044EFF')

    def test_exp_comp_on_exact(self):
        assert vcmd.exp_comp_on(C1) == _b(C1, '01043E02FF')

    def test_brightness_up_direct_exact(self):
        assert vcmd.brightness_up_direct(C1) == _b(C1, '01040D02FF')

    def test_brightness_down_direct_exact(self):
        assert vcmd.brightness_down_direct(C1) == _b(C1, '01040D03FF')

    def test_exp_comp_up_exact(self):
        assert vcmd.exp_comp_up(C1) == _b(C1, '01040E02FF')

    def test_exp_comp_down_exact(self):
        assert vcmd.exp_comp_down(C1) == _b(C1, '01040E03FF')

    def test_brightness_up_down_differ(self):
        assert vcmd.brightness_up_direct(C1) != vcmd.brightness_down_direct(C1)

    def test_exp_comp_up_down_differ(self):
        assert vcmd.exp_comp_up(C1) != vcmd.exp_comp_down(C1)

    def test_bright_direct_vs_expcomp_differ(self):
        # CAM_Bright (0D) ≠ CAM_ExpComp (0E)
        assert vcmd.brightness_up_direct(C1) != vcmd.exp_comp_up(C1)

    def test_backlight_on_exact(self):
        assert vcmd.backlight_on(C1) == _b(C1, '01043302FF')

    def test_backlight_off_exact(self):
        assert vcmd.backlight_off(C1) == _b(C1, '01043303FF')

    def test_backlight_on_off_differ(self):
        assert vcmd.backlight_on(C1) != vcmd.backlight_off(C1)


# ─────────────────────────────────────────────────────────────────────────────
#  Presets
# ─────────────────────────────────────────────────────────────────────────────

class TestPresetCommandsExact:
    def test_preset_recall_slot_01(self):
        # 81 01 04 3f 02 01 ff
        assert vcmd.preset_recall(C1, '01') == _b(C1, '01043f0201ff')

    def test_preset_recall_slot_0a(self):
        assert vcmd.preset_recall(C1, '0a') == _b(C1, '01043f020aff')

    def test_preset_save_slot_05(self):
        # 81 01 04 3f 01 05 ff
        assert vcmd.preset_save(C1, '05') == _b(C1, '01043f0105ff')

    def test_recall_save_opcode_differs(self):
        # recall=02, save=01 en posición -3 (antes del preset byte y FF)
        assert vcmd.preset_recall(C1, '01')[-3] == 0x02
        assert vcmd.preset_save(C1, '01')[-3]   == 0x01

    def test_preset_number_byte(self):
        # El byte -2 (antes de FF) es el número de preset
        assert vcmd.preset_recall(C1, '08')[-2] == 0x08
        assert vcmd.preset_save(C1, '0f')[-2]   == 0x0F

    def test_preset_cam2_prefix(self):
        assert vcmd.preset_recall(C2, '01')[0] == 0x82

    def test_all_commands_terminate_ff(self):
        cmds = [
            vcmd.power_on(C1), vcmd.power_off(C1),
            vcmd.pan_tilt(C1, 1, 1, PanDir.STOP, TiltDir.STOP),
            vcmd.pan_tilt_stop(C1), vcmd.home(C1),
            vcmd.zoom_absolute(C1, 50), vcmd.zoom_inquiry(C1),
            vcmd.ptz_position_inquiry(C1),
            vcmd.focus_auto(C1), vcmd.focus_manual(C1),
            vcmd.one_push_af(C1), vcmd.ae_mode_inquiry(C1),
            vcmd.exp_comp_inquiry(C1), vcmd.exp_comp_on(C1),
            vcmd.brightness_up_direct(C1), vcmd.brightness_down_direct(C1),
            vcmd.exp_comp_up(C1), vcmd.exp_comp_down(C1),
            vcmd.backlight_on(C1), vcmd.backlight_off(C1),
            vcmd.preset_recall(C1, '01'), vcmd.preset_save(C1, '01'),
        ]
        for cmd in cmds:
            assert cmd[-1] == 0xFF, f"Comando no termina en FF: {cmd.hex()}"

    def test_all_commands_start_with_cam_id(self):
        for cam_id in (C1, C2):
            expected = bytes.fromhex(cam_id)
            for cmd in [vcmd.power_on(cam_id), vcmd.home(cam_id),
                        vcmd.focus_auto(cam_id), vcmd.preset_recall(cam_id, '01')]:
                assert cmd[:len(expected)] == expected

