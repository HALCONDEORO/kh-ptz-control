"""Real Qt USER power toggle with a synthetic event bus, no hardware."""
import os
from pathlib import Path
import subprocess
import sys


def test_operator_power_toggle_real_qt():
    script = "import os\nos.environ['QT_QPA_PLATFORM']='offscreen'\nfrom pathlib import Path\nfrom tempfile import TemporaryDirectory\nfrom unittest.mock import Mock,patch\nfrom PyQt5.QtWidgets import QApplication,QMessageBox\nfrom PyQt5.QtTest import QTest\nimport adapters.sim_mode as sim\nwith TemporaryDirectory() as root:\n sim._APP_DIR=Path(root);sim.BACKUP=Path(root)/'backup.json';sim.activate()\n app=QApplication([])\n from ui.main_window import MainWindow\n from domain.call_set_policy import OperatingMode\n w=MainWindow();w._access_mode_svc.set_mode(OperatingMode.USER);w.show();w._login_overlay.hide();QTest.qWait(100);app.processEvents()\n w._bus=Mock();w._session.ToggleSession();w._session._session_home();QTest.qWait(100);app.processEvents()\n power=w._operator_camera_power\n assert power.button.isVisible() and power.button.isEnabled()\n power.button.click();power._dialog.buttons()[1].click();app.processEvents()\n assert w.session_active\n power.button.click();power._dialog.buttons()[0].click();app.processEvents()\n assert not w.session_active\n assert power.status.toolTip().startswith('Standby requested.')\n power.button.click();power._dialog.buttons()[1].click();app.processEvents()\n assert not w.session_active\n power.button.click();power._dialog.buttons()[0].click();app.processEvents()\n assert w.session_active\n print('PASS visible USER, cancel/confirm off, standby status, cancel/confirm restart; fake bus only')"
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        env.update(KHPTZ_DATA_DIR=root, KHPTZ_CONFIG_DIR=root, KHPTZ_LOG_DIR=root,
                   KHPTZ_BACKUP_DIR=root, KHPTZ_RUN_DIR=root)
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).parents[1],
                                env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_panel_selftest_without_legacy_session_button():
    script = '''from runtime.selftest_support.panel import run_panel_check
assert run_panel_check()['passed'] is True
'''
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', KHPTZ_DATA_DIR=root,
                   KHPTZ_CONFIG_DIR=root, KHPTZ_RUN_DIR=root)
        result = subprocess.run([sys.executable, '-c', script],
                                cwd=Path(__file__).parents[1], env=env,
                                text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
