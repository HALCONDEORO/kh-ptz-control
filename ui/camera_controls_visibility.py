"""Keep session controls stable; transport loss only disables motion."""
from PyQt5.QtCore import QTimer

DISCONNECT_HIDE_DELAY_MS = 1800


class CameraControlsVisibility:
    def __init__(self, window):
        self.window = window
        self.visible = False
        self.camera = None
        self.timer = QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._hide_if_still_disconnected)

    def _snapshot(self):
        key = 1 if self.window.Cam1.isChecked() else 2
        camera = self.window.Cam1 if key == 1 else self.window.Cam2
        return key, bool(camera._connected)

    def _show(self, visible):
        self.visible = visible
        self.window._right_panel.show_camera_controls(visible)

    def update(self):
        key, connected = self._snapshot()
        self.camera = key
        self.timer.stop()
        active = (self.window.session_active
                  and not getattr(self.window, '_shutting_down', False))
        self._show(bool(active))
        self.window._right_panel.set_camera_transport_state(bool(active and connected))

    def _hide_if_still_disconnected(self):
        # A queued deadline from the old hide policy must not remove the panel.
        self.update()


def update_camera_controls_visibility(window):
    controller = window.__dict__.get('_camera_controls_visibility')
    if controller is None:
        controller = CameraControlsVisibility(window)
        window._camera_controls_visibility = controller
    controller.update()

    power = window.__dict__.get('_operator_camera_power')
    if power is None and hasattr(window, 'BtnSession'):
        from ui.operator_camera_power import OperatorCameraPower
        power = OperatorCameraPower(window)
        window._operator_camera_power = power
    if power is not None:
        power.refresh()
