#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_config_validators.py — Tests de is_valid_ip, is_valid_cam_id, PRESET_MAP
y validación de IP en _CamEditDialog._apply().
Lógica pura: sin I/O, sin hardware real.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
#  Qt stubs — required so ui.config_dialog can be imported without a display
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_qt_stubs() -> None:
    """Inject minimal Qt stubs into sys.modules so config_dialog can import."""
    for mod_name in (
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets",
        "PyQt5.QtGui", "PyQt5.QtSvg",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "QSize", "QTimer", "QTime", "pyqtSignal", "QObject"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QIcon", "QPixmap", "QPainter", "QColor", "QGraphicsDropShadowEffect"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock())

    qtsvg = sys.modules["PyQt5.QtSvg"]
    if not hasattr(qtsvg, "QSvgRenderer"):
        qtsvg.QSvgRenderer = MagicMock()

    qtw = sys.modules["PyQt5.QtWidgets"]
    _widget_defaults = {
        "QDialog":                    type("QDialog", (), {"__init__": lambda s, p=None: None}),
        "QVBoxLayout":                MagicMock(return_value=MagicMock()),
        "QHBoxLayout":                MagicMock(return_value=MagicMock()),
        "QLabel":                     MagicMock,
        "QPushButton":                MagicMock,
        "QFrame":                     MagicMock,
        "QScrollArea":                MagicMock,
        "QWidget":                    MagicMock,
        "QLineEdit":                  MagicMock,
        "QTabWidget":                 MagicMock,
        "QCheckBox":                  MagicMock,
        "QTimeEdit":                  MagicMock,
        "QGraphicsDropShadowEffect":  MagicMock,
        "QGraphicsOpacityEffect":     MagicMock,
        "QMessageBox":                MagicMock(),
        "QFileDialog":                MagicMock(),
    }
    for name, value in _widget_defaults.items():
        if not hasattr(qtw, name):
            setattr(qtw, name, value)


_ensure_qt_stubs()


# ═══════════════════════════════════════════════════════════════════════════════
#  _CamEditDialog IP validation
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeCamEditDialog:
    """
    _CamEditDialog with Qt __init__ bypassed.
    Wires only the attributes used by _apply().
    """

    def __init__(self, cam_num: int, config_type: str, input_text: str):
        from config import is_valid_ip, is_valid_cam_id
        self._cam_num = cam_num
        self._config_type = config_type
        self._validate = is_valid_ip if config_type == "ip" else is_valid_cam_id

        self._input = MagicMock()
        self._input.text.return_value = input_text
        self._input.placeholderText.return_value = "e.g. 172.16.1.11"

        self._err = MagicMock()
        self._mw = MagicMock()
        self.accept = MagicMock()

    # Bring in the real _apply logic without any Qt widget construction:
    from ui.config_dialog import _CamEditDialog
    _apply = _CamEditDialog._apply


class TestCamEditDialogIpValidation:
    """_CamEditDialog._apply() must reject malformed IPs before saving."""

    def test_invalid_ip_does_not_call_accept(self):
        dlg = _FakeCamEditDialog(cam_num=1, config_type="ip",
                                 input_text="999.999.999.999")
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None):
            dlg._apply()
        dlg.accept.assert_not_called()

    def test_invalid_ip_sets_error_label(self):
        dlg = _FakeCamEditDialog(cam_num=1, config_type="ip",
                                 input_text="not-an-ip")
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None):
            dlg._apply()
        dlg._err.setText.assert_called_once()
        error_text = dlg._err.setText.call_args[0][0]
        assert error_text  # non-empty message

    def test_empty_ip_does_not_call_accept(self):
        dlg = _FakeCamEditDialog(cam_num=1, config_type="ip", input_text="   ")
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None):
            dlg._apply()
        dlg.accept.assert_not_called()

    def test_valid_ip_calls_accept(self):
        dlg = _FakeCamEditDialog(cam_num=1, config_type="ip",
                                 input_text="192.168.1.10")
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None), \
             patch("config.CAM1") as mock_cam1, \
             patch("config.CAM2") as mock_cam2:
            mock_cam1.ip = "192.168.1.1"
            mock_cam2.ip = "192.168.1.2"
            dlg._apply()
        dlg.accept.assert_called_once()

    @pytest.mark.parametrize("bad_ip", [
        "256.0.0.1",
        "192.168.1",
        "192.168.1.1.5",
        "192.168.1.-1",
        "abc.def.ghi.jkl",
        "192.168.1.1/24",
        "192.168.1.1:80",
    ])
    def test_various_invalid_ips_are_rejected(self, bad_ip):
        dlg = _FakeCamEditDialog(cam_num=2, config_type="ip",
                                 input_text=bad_ip)
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None):
            dlg._apply()
        dlg.accept.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
#  is_valid_ip
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsValidIp:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import is_valid_ip
        self.fn = is_valid_ip

    @pytest.mark.parametrize("ip", [
        "192.168.1.1",
        "0.0.0.0",
        "255.255.255.255",
        "10.0.0.1",
        "172.16.1.11",
        "1.2.3.4",
    ])
    def test_valid_ips(self, ip):
        assert self.fn(ip) is True

    @pytest.mark.parametrize("ip", [
        "256.0.0.1",        # octeto > 255
        "192.168.1.256",
        "192.168.1",        # solo 3 octetos
        "192.168.1.1.1",    # 5 octetos
        "",
        "abc.def.ghi.jkl",
        "192.168.1.-1",
        "192.168.1.1/24",   # con máscara
        "192.168.1.1:80",   # con puerto
    ])
    def test_invalid_ips(self, ip):
        assert self.fn(ip) is False

    def test_non_string_returns_false(self):
        assert self.fn(None) is False
        assert self.fn(192168) is False
        assert self.fn(["192.168.1.1"]) is False

    def test_strips_whitespace(self):
        # _read_config ya llama .strip(), pero is_valid_ip también debe tolerarlo
        assert self.fn("  192.168.1.1  ") is True

    def test_empty_string_is_invalid(self):
        assert self.fn("") is False


# ═══════════════════════════════════════════════════════════════════════════════
#  is_valid_cam_id
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsValidCamId:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import is_valid_cam_id
        self.fn = is_valid_cam_id

    @pytest.mark.parametrize("cam_id", [
        "81",    # Cam1 real
        "82",    # Cam2 real
        "FF",
        "ff",    # minúsculas también son hex válido
        "00",
        "8181",  # longitud 4 — par y hex válido
        "FFFF",
    ])
    def test_valid_cam_ids(self, cam_id):
        assert self.fn(cam_id) is True

    @pytest.mark.parametrize("cam_id", [
        "",       # vacío
        "8",      # longitud impar
        "819",    # longitud impar
        "GG",     # no es hex
        "8X",
    ])
    def test_invalid_cam_ids(self, cam_id):
        assert self.fn(cam_id) is False

    def test_non_string_returns_false(self):
        assert self.fn(81) is False
        assert self.fn(None) is False

    def test_strips_whitespace_before_check(self):
        # "  81  " → stripped "81" → longitud par, hex válido
        assert self.fn("  81  ") is True


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESET_MAP — mapeo preset_number → hex string VISCA
# ═══════════════════════════════════════════════════════════════════════════════

class TestPresetMap:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import PRESET_MAP
        self.pm = PRESET_MAP

    def test_total_count(self):
        # Presets 1-89 + 90-99 + 100-131 + 132 (Platform 2) = 132 entradas
        assert len(self.pm) == 132

    def test_range_1_to_89_is_direct_hex(self):
        # Preset 1 → "01", preset 10 → "0A", preset 89 → "59"
        assert self.pm[1]  == "01"
        assert self.pm[10] == "0A"
        assert self.pm[15] == "0F"
        assert self.pm[89] == "59"

    def test_range_90_to_99_has_offset(self):
        # 0x8C + (i - 90): 90→"8C", 95→"91", 99→"95"
        assert self.pm[90] == "8C"
        assert self.pm[91] == "8D"
        assert self.pm[95] == "91"
        assert self.pm[99] == "95"

    def test_range_100_to_131_is_direct_hex(self):
        # Vuelta al hex directo: 100 → "64", 131 → "83"
        assert self.pm[100] == "64"
        assert self.pm[110] == "6E"
        assert self.pm[131] == "83"

    def test_preset_132_is_second_platform(self):
        # 132 = segunda plataforma opcional → hex directo 0x84
        assert self.pm[132] == "84"

    def test_no_collision_between_ranges(self):
        # Cada número VISCA hex es único en el mapa
        hex_values = list(self.pm.values())
        assert len(hex_values) == len(set(hex_values)), "Colisión detectada en PRESET_MAP"

    def test_all_values_are_valid_hex(self):
        import binascii
        for preset, hex_str in self.pm.items():
            try:
                binascii.unhexlify(hex_str)
            except Exception:
                pytest.fail(f"Preset {preset} → '{hex_str}' no es hex válido")

    def test_all_values_are_two_chars(self):
        for preset, hex_str in self.pm.items():
            assert len(hex_str) == 2, f"Preset {preset} tiene hex de longitud {len(hex_str)}: '{hex_str}'"

    def test_90_to_99_not_contiguous_with_1_to_89(self):
        # El salto de 89→90 en valores hex: "59" vs "8C" (no son consecutivos)
        assert int(self.pm[89], 16) + 1 != int(self.pm[90], 16)

    def test_boundary_between_offset_and_direct_again(self):
        # Preset 99 → "95" y preset 100 → "64": tampoco son consecutivos
        assert int(self.pm[99], 16) + 1 != int(self.pm[100], 16)


# ═══════════════════════════════════════════════════════════════════════════════
#  config import safety — must not raise even when password.enc is absent (#192)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigImportSafety:
    """config can be imported safely without a valid password.enc (#192)."""

    def test_import_config_without_password_enc(self, tmp_path, monkeypatch):
        """Importing config must not raise when password.enc is missing."""
        monkeypatch.chdir(tmp_path)  # no password.enc here
        import importlib
        import config
        # Re-importing (already cached) should also be fine
        importlib.reload(config)

    def test_login_password_not_exported(self):
        """config must not expose LOGIN_PASSWORD as a module attribute (#192)."""
        import config
        assert not hasattr(config, "LOGIN_PASSWORD"), (
            "LOGIN_PASSWORD must not be a module-level attribute — "
            "password decryption must stay lazy inside secret_manager / login_screen"
        )

    def test_cam1_still_available_after_import(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import importlib
        import config
        importlib.reload(config)
        assert hasattr(config, "CAM1")

    def test_is_valid_ip_still_importable_without_password(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from config import is_valid_ip
        assert is_valid_ip("192.168.1.1") is True


# ═══════════════════════════════════════════════════════════════════════════════
#  ConfigDialog static helper methods
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigDialogCurrentRuntimeMode:
    """ConfigDialog._current_runtime_mode derives the effective profile."""

    @staticmethod
    def _mode(sim_active: bool) -> str:
        from ui.config_dialog import ConfigDialog
        return ConfigDialog._current_runtime_mode(sim_active)

    def test_production_when_no_env_and_sim_inactive(self, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        assert self._mode(sim_active=False) == "production"

    def test_simulation_when_no_env_and_sim_active(self, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        assert self._mode(sim_active=True) == "simulation"

    def test_env_demo_overrides_sim_inactive(self, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "demo")
        assert self._mode(sim_active=False) == "demo"

    def test_env_simulation_overrides_sim_inactive(self, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "simulation")
        assert self._mode(sim_active=False) == "simulation"

    def test_env_production_returns_production(self, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "production")
        assert self._mode(sim_active=False) == "production"

    def test_env_demo_takes_precedence_over_sim_active(self, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "demo")
        assert self._mode(sim_active=True) == "demo"


class TestConfigDialogRuntimeModeButtonStyle:
    """ConfigDialog._runtime_mode_button_style returns valid CSS per mode."""

    @staticmethod
    def _style(mode: str) -> str:
        from ui.config_dialog import ConfigDialog
        return ConfigDialog._runtime_mode_button_style(mode)

    @pytest.mark.parametrize("mode", ["production", "demo", "simulation"])
    def test_returns_non_empty_string(self, mode):
        assert isinstance(self._style(mode), str) and self._style(mode).strip()

    @pytest.mark.parametrize("mode", ["production", "demo", "simulation"])
    def test_contains_border_radius(self, mode):
        assert "border-radius" in self._style(mode)

    def test_production_differs_from_demo(self):
        assert self._style("production") != self._style("demo")

    def test_demo_and_simulation_share_colour(self):
        assert self._style("demo") == self._style("simulation")

    def test_unknown_mode_raises_key_error(self):
        with pytest.raises(KeyError):
            self._style("unknown")
