"""A camera transport loss cannot remove the operator's control panel."""
import os
from pathlib import Path
import subprocess
import sys


def test_real_panel_stays_visible_during_sustained_loss_and_offline_selection():
    script = r'''
from pathlib import Path
from tempfile import TemporaryDirectory
from PyQt5.QtWidgets import QApplication
from unittest.mock import patch
import adapters.sim_mode as sim
# This is a UI policy test, not a transport integration test. Real worker
# callbacks can reconnect Cam2 between the offline-selection assertions.
with TemporaryDirectory() as root, \
        patch('ptz.visca.worker.CameraWorker._run', return_value=None), \
        patch('simulation.sim_worker.start_simulation', return_value=(False, False)):
    sim._APP_DIR = Path(root)
    sim.BACKUP = Path(root) / 'backup.json'
    sim.activate()
    app = QApplication([])
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    # Drain initial disconnected snapshots before manually driving UI state.
    app.processEvents()
    w._login_overlay.hide()
    w.session_active = True
    w.Cam2.set_connected(False)
    w.Cam1.set_connected(True)
    w._update_controls_visibility()
    panel = w._right_panel
    assert panel._controls_widget.isVisible()
    w.Cam1.set_connected(False)
    w._update_controls_visibility()
    # Deliver the old 1.8s deadline as well as an ordinary refresh.
    w._camera_controls_visibility._hide_if_still_disconnected()
    app.processEvents()
    assert panel._controls_widget.isVisible(), 'transport loss hides panel'
    assert not panel._motion_widget.isEnabled()
    assert panel._connection_status_label.isVisible()
    assert panel._connection_status_label.text() == 'Reconnecting...'
    w.Cam2.click()
    app.processEvents()
    assert panel._controls_widget.isVisible()
    assert not panel._motion_widget.isEnabled()
    w.Cam2.set_connected(True)
    w._update_controls_visibility()
    assert panel._motion_widget.isEnabled()
    assert panel._connection_status_label.isHidden()
    w.session_active = False
    w._update_controls_visibility()
    assert panel._controls_widget.isHidden()
    w._shutting_down = True
    w._supervisor.stop()
    w._cameras.stop_all()
    w.hide()
'''
    result = subprocess.run([sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
