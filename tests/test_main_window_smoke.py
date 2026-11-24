#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Hardware-free MainWindow construction smoke test.

test_startup_smoke.py covers the non-UI path (bootstrap -> AppContext) but
explicitly does not build the MainWindow. This fills that gap: it constructs the
real MainWindow in simulation mode (no PTZ cameras, no ATEM, offscreen Qt) so
that every _build_* method — and, after #894, every ui/config_pages tab builder
reachable from construction — runs for real. It is the runtime net that turns
future MainWindow/ConfigDialog extraction from a static-only change into a
verifiable one: a NameError or a broken widget wiring in any build path aborts
this test instead of only surfacing on the Pi.

Per-test Qt widget cleanup comes from a conftest autouse fixture. These tests
run unforked (see the comment above the imports), so simulation mode is undone
by the sim_mode_active fixture rather than by process teardown.
"""

from __future__ import annotations

import sys

import pytest

from conftest import ensure_real_qt, is_poisoned_by_qt_stub

# NOT forked. Building a full real widget tree in a freshly forked child aborts
# (SIGABRT) inside Qt's offscreen platform init every time, even though the
# child is throwaway — the same failure that already forces
# test_setup_wizard.py and test_login_countdown_integration.py to run unforked
# (see the two pytest steps in .github/workflows/tests.yml). MainWindow builds
# the largest tree in the suite, so it runs in that second, unforked step and
# is excluded from the --forked run.

import adapters.sim_mode as sim_mode  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    """Put the real PyQt5 in sys.modules before conftest's _qapp_available runs.

    That autouse fixture is a no-op when "PyQt5.QtWidgets" is not yet imported,
    and this module imports Qt lazily (inside the main_window fixture), so
    without this nothing would build a QApplication and QMainWindow.__init__
    would abort the process. It also drops any collection-time PyQt5 stub left
    by another module. Module-scoped fixtures run before function-scoped ones,
    so importing Qt here is enough for _qapp_available to do its job.
    """
    ensure_real_qt()


@pytest.fixture
def _qapp(_real_qt):
    """The process-wide QApplication, created on first use."""
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def sim_mode_active(tmp_path, monkeypatch):
    """Run the body in simulation mode, then restore the previous state.

    sim_mode's app dir defaults to the REPOSITORY ROOT: activate() writes
    sim_ip_backup.json plus simulator PTZ1IP/PTZ2IP.txt there, and deactivate()
    then rewrites PTZ1IP/PTZ2IP/ATEMIP.txt from the backup - every run of this
    file dirtied the checkout (empty ATEMIP.txt showed as untracked), and on a
    real appliance checkout a crashed run would leave simulator IPs in the
    camera config. Redirect all of sim_mode's storage into a tmp dir.
    """
    monkeypatch.setattr(sim_mode, "_APP_DIR", tmp_path)
    monkeypatch.setattr(sim_mode, "BACKUP", tmp_path / "sim_ip_backup.json")
    was_active = sim_mode.is_active()
    if not was_active:
        sim_mode.activate()
    try:
        yield
    finally:
        if not was_active:
            try:
                sim_mode.deactivate()
            except Exception:  # noqa: BLE001 — teardown must never fail the test
                pass


@pytest.fixture
def main_window(_qapp, sim_mode_active):
    """Construct the real MainWindow offscreen and close it afterwards."""
    from ui.main_window import MainWindow

    if is_poisoned_by_qt_stub(MainWindow):
        pytest.skip("ui.main_window was imported under a PyQt5 stub by another "
                    "test module — run this file in isolation")

    window = MainWindow()
    try:
        yield window
    finally:
        window.close()


def test_main_window_constructs_without_hardware(main_window):
    """All _build_* methods run during construction without raising."""
    # 475+ child widgets are built; assert the tree is non-trivial rather than
    # pinning an exact count that harmless layout tweaks would churn.
    assert len(main_window.findChildren(object)) > 100


def test_main_window_wires_the_camera_seam(main_window):
    """The #893 CameraConfigService seam and its collaborators exist."""
    assert main_window._camera_config is not None
    assert main_window._cameras is not None
    assert main_window._camera_port is not None


def test_main_window_session_starts_inactive(main_window):
    """Construction must not auto-start a session (lifecycle contract)."""
    assert main_window.session_active is False


def test_config_dialog_opens_from_main_window(main_window):
    """Building the split ConfigDialog (all ui/config_pages tabs) does not raise.

    This is the runtime check the #894 split could not get on its own: it forces
    every extracted tab builder to run against a real MainWindow.
    """
    from ui.config_dialog import ConfigDialog

    dialog = ConfigDialog(main_window)
    try:
        assert dialog.findChild(object) is not None
    finally:
        dialog.close()


def test_queued_zoom_rechecks_generation_on_qt_delivery(main_window, _qapp):
    from unittest.mock import Mock
    from PyQt5.QtCore import QMetaObject, Qt, Q_ARG

    current = [1]
    main_window._camera_port.display_generation = lambda key: current[0]
    main_window._selected_cam_key = lambda: 1
    main_window._set_zoom_feedback = Mock()
    QMetaObject.invokeMethod(main_window, "_apply_zoom_feedback", Qt.QueuedConnection,
                             Q_ARG(int, 1), Q_ARG(int, 1), Q_ARG(int, 75))
    current[0] = 2  # Change after enqueue, before Qt delivers.
    _qapp.processEvents()
    main_window._set_zoom_feedback.assert_not_called()


def test_queued_zoom_drops_result_after_camera_selection_changes(main_window, _qapp):
    from unittest.mock import Mock
    from PyQt5.QtCore import QMetaObject, Qt, Q_ARG

    main_window._camera_port.display_generation = lambda key: 0
    selected = [1]
    main_window._selected_cam_key = lambda: selected[0]
    main_window._set_zoom_feedback = Mock()
    QMetaObject.invokeMethod(main_window, "_apply_zoom_feedback", Qt.QueuedConnection,
                             Q_ARG(int, 1), Q_ARG(int, 0), Q_ARG(int, 75))
    selected[0] = 2
    _qapp.processEvents()
    main_window._set_zoom_feedback.assert_not_called()


def test_queued_exposure_rechecks_generation_on_qt_delivery(main_window, _qapp):
    from unittest.mock import Mock
    from PyQt5.QtCore import QMetaObject, Qt, Q_ARG

    current = [1]
    main_window._camera_port.display_generation = lambda key: current[0]
    main_window._selected_cam_key = lambda: 1
    main_window._update_exposure_ui = Mock()
    QMetaObject.invokeMethod(main_window, "_apply_exposure_update", Qt.QueuedConnection,
                             Q_ARG(int, 1), Q_ARG(int, 1))
    current[0] = 2
    _qapp.processEvents()
    main_window._update_exposure_ui.assert_not_called()


def test_retired_worker_connection_does_not_query_camera_one(main_window):
    from unittest.mock import Mock

    main_window._camera_port.async_refresh_ae_mode = Mock()
    main_window._cameras.cam_key = Mock(side_effect=ValueError("retired endpoint"))
    main_window._on_cam_connected(True, "192.0.2.99")
    main_window._camera_port.async_refresh_ae_mode.assert_not_called()


def test_current_queued_display_updates_are_delivered(main_window, _qapp):
    from unittest.mock import Mock
    from PyQt5.QtCore import QMetaObject, Qt, Q_ARG

    main_window._camera_port.display_generation = lambda key: 3
    main_window._selected_cam_key = lambda: 1
    main_window._set_zoom_feedback = Mock()
    main_window._update_exposure_ui = Mock()
    QMetaObject.invokeMethod(main_window, "_apply_zoom_feedback", Qt.QueuedConnection,
                             Q_ARG(int, 1), Q_ARG(int, 3), Q_ARG(int, 75))
    QMetaObject.invokeMethod(main_window, "_apply_exposure_update", Qt.QueuedConnection,
                             Q_ARG(int, 1), Q_ARG(int, 3))
    _qapp.processEvents()
    main_window._set_zoom_feedback.assert_called_once_with(75)
    main_window._update_exposure_ui.assert_called_once()


def test_seat_save_cannot_follow_camera_selection_change(main_window, monkeypatch):
    from unittest.mock import Mock
    # This regression concerns preset targeting, not background display reads.
    monkeypatch.setattr(main_window._camera_port, "refresh_zoom_display", Mock())
    monkeypatch.setattr(main_window._camera_port, "async_refresh_ae_mode", Mock())
    main_window.Cam2.click()
    main_window._enter_seat_selection(37)
    main_window.Cam1.click()
    main_window._bus = Mock()
    main_window._exit_seat_selection(save=True)
    main_window._bus.emit.assert_not_called()
    assert main_window._seat_pending is None
    assert not main_window._btn_save_seat.isVisible()


def test_seat_save_keeps_selected_camera_when_unchanged(main_window, monkeypatch):
    from unittest.mock import Mock
    # This regression concerns preset targeting, not background display reads.
    monkeypatch.setattr(main_window._camera_port, "refresh_zoom_display", Mock())
    monkeypatch.setattr(main_window._camera_port, "async_refresh_ae_mode", Mock())
    from core.events import EventType
    main_window.Cam2.click()
    main_window._enter_seat_selection(37)
    main_window._bus = Mock()
    main_window._exit_seat_selection(save=True)
    main_window._bus.emit.assert_called_once_with(
        EventType.PRESET_SAVE_SLOT, camera=2, slot=37,
    )


def test_cancelled_seat_selection_cannot_be_saved_later(main_window, monkeypatch):
    from unittest.mock import Mock
    # This regression concerns preset targeting, not background display reads.
    monkeypatch.setattr(main_window._camera_port, "refresh_zoom_display", Mock())
    monkeypatch.setattr(main_window._camera_port, "async_refresh_ae_mode", Mock())
    main_window._enter_seat_selection(37)
    main_window._bus = Mock()
    main_window._exit_seat_selection(save=False)
    main_window._exit_seat_selection(save=True)
    main_window._bus.emit.assert_not_called()


def test_custom_special_seat_builds_without_known_legacy_icon(main_window, monkeypatch):
    """A valid custom special layout must not abort construction with KeyError."""
    from domain.room_layout import SeatLayout
    from ui.widgets import SpecialDragButton

    seat = SeatLayout(id="side", label="Side room", preset=37,
                      camera_role="comments", x=10, y=20, type="special")
    monkeypatch.setattr(main_window._layout_svc, "visible_seats", lambda: [seat])
    main_window._build_seat_buttons()
    button = main_window.Seat37
    assert isinstance(button, SpecialDragButton)
    assert button.seat_number == 37
    assert button.text() == "Side room"
    assert button.x() == 10 and button.y() == 20
    assert button.icon().isNull()


@pytest.mark.parametrize("transition", ["unchanged", "ended", "restarted", "closing", "rejected"])
def test_platform_save_confirmation_stays_in_its_session(main_window, monkeypatch, transition):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from PyQt5.QtWidgets import QMessageBox
    from core.events import EventType
    from domain.call_set_policy import InputType

    main_window._camera_port.refresh_zoom_display = Mock()
    main_window._camera_port.async_refresh_ae_mode = Mock()
    main_window.session_active = True
    main_window._app_ctrl = Mock()
    main_window._app_ctrl.recall_seat.return_value = SimpleNamespace(error_code="set_action")
    main_window._bus = Mock()

    def confirm_after_transition(*args, **kwargs):
        if transition in ("ended", "restarted"):
            main_window._session.shutdown("inactivity")
            if transition == "restarted":
                main_window._session.ToggleSession()
        elif transition == "closing":
            main_window._shutting_down = True
        main_window._bus.reset_mock()
        return QMessageBox.No if transition == "rejected" else QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm_after_transition)
    main_window._dispatch_preset_action(1, InputType.LONG_PRESS)
    if transition == "unchanged":
        main_window._bus.emit.assert_called_once_with(EventType.PRESET_SAVE_SLOT, camera=1, slot=1)
    else:
        main_window._bus.emit.assert_not_called()


@pytest.mark.parametrize("deleted", [False, True])
def test_right_panel_fit_handles_container_lifetime(_qapp, deleted):
    from PyQt5 import sip
    from PyQt5.QtWidgets import QFrame
    from ui.right_panel import RightPanel

    panel = RightPanel.__new__(RightPanel)
    panel._container = QFrame()
    if deleted:
        sip.delete(panel._container)
    # A queued fit can outlive its parent widget during window teardown.
    panel._fit_container_height()
    if not deleted:
        assert panel._container.geometry().getRect() == (1446, 0, 474, 1080)


@pytest.mark.parametrize("deleted", [False, True])
def test_right_panel_flash_handles_button_lifetime(_qapp, monkeypatch, deleted):
    from PyQt5 import sip
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QPushButton
    from ui.right_panel import RightPanel

    callbacks = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: callbacks.append(callback))
    panel = RightPanel.__new__(RightPanel)
    panel._btn_focus_base_style = "QPushButton { color: black; }"
    button = QPushButton()
    panel._flash_button(button, True)
    if deleted:
        sip.delete(button)
    callbacks[0]()
    if not deleted:
        assert button.styleSheet() == panel._btn_focus_base_style


@pytest.mark.parametrize("deleted", [False, True])
def test_main_window_blocked_flash_handles_button_lifetime(_qapp, monkeypatch, deleted):
    from PyQt5 import sip
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QPushButton
    from ui.main_window import MainWindow

    callbacks = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: callbacks.append(callback))
    button = QPushButton()
    button.setStyleSheet("QPushButton { color: black; }")
    original = button.styleSheet()
    MainWindow._flash_blocked(None, button)
    if deleted:
        sip.delete(button)
    callbacks[0]()
    if not deleted:
        assert button.styleSheet() == original


def test_session_end_cancels_unconfirmed_seat_save(main_window, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(main_window._camera_port, "refresh_zoom_display", Mock())
    monkeypatch.setattr(main_window._camera_port, "async_refresh_ae_mode", Mock())
    main_window._enter_seat_selection(37)
    main_window._bus = Mock()
    main_window._session.shutdown("manual")
    assert main_window._seat_pending is None
    assert main_window._seat_pending_camera is None
    main_window._bus.reset_mock()
    main_window.session_active = True  # a later session must not inherit Save
    main_window._exit_seat_selection(save=True)
    main_window._bus.emit.assert_not_called()


@pytest.mark.parametrize("kind", ["zoom", "exposure"])
def test_late_display_callback_ignores_destroyed_window(_qapp, kind):
    """A completed network read may outlive the window receiving its result."""
    from unittest.mock import Mock
    from PyQt5 import sip
    from PyQt5.QtWidgets import QWidget
    from ui.camera_display_mixin import CameraDisplayMixin

    class DisplayWindow(CameraDisplayMixin, QWidget):
        pass

    window = DisplayWindow()
    window.Cam1 = Mock()
    window.Cam1.isChecked.return_value = True
    window._camera_port = Mock()
    window._camera_port.display_generation.return_value = 0
    window._cameras = Mock()
    window._cameras.cam_key.return_value = 1
    if kind == "zoom":
        window._refresh_zoom()
        callback = window._camera_port.refresh_zoom_display.call_args.args[1]
    else:
        window._on_cam_connected(True, "192.0.2.1")
        callback = window._camera_port.async_refresh_ae_mode.call_args.args[1]
    sip.delete(window)
    if kind == "zoom":
        callback(50)
    else:
        callback()


@pytest.mark.parametrize("kind", ["zoom", "exposure"])
def test_display_callback_still_delivers_to_live_receiver(_qapp, kind):
    from unittest.mock import Mock
    from PyQt5.QtWidgets import QWidget
    from ui.camera_display_mixin import CameraDisplayMixin

    class DisplayWindow(CameraDisplayMixin, QWidget):
        pass

    window = DisplayWindow()
    window.Cam1 = Mock()
    window.Cam1.isChecked.return_value = True
    window._camera_port = Mock()
    window._camera_port.display_generation.return_value = 0
    window._cameras = Mock()
    window._cameras.cam_key.return_value = 1
    window._set_zoom_feedback = Mock()
    window._update_exposure_ui = Mock()
    if kind == "zoom":
        window._refresh_zoom()
        window._camera_port.refresh_zoom_display.call_args.args[1](50)
        _qapp.processEvents()
        window._set_zoom_feedback.assert_called_once_with(50)
    else:
        window._on_cam_connected(True, "192.0.2.1")
        window._camera_port.async_refresh_ae_mode.call_args.args[1]()
        _qapp.processEvents()
        window._update_exposure_ui.assert_called_once_with()
    window.close()


@pytest.mark.parametrize("kind", ["zoom", "exposure"])
def test_queued_display_update_is_dropped_after_shutdown(_qapp, kind):
    from unittest.mock import Mock
    from PyQt5.QtWidgets import QWidget
    from ui.camera_display_mixin import CameraDisplayMixin

    class DisplayWindow(CameraDisplayMixin, QWidget):
        pass

    window = DisplayWindow()
    window.Cam1 = Mock()
    window.Cam1.isChecked.return_value = True
    window._camera_port = Mock()
    window._camera_port.display_generation.return_value = 0
    window._cameras = Mock()
    window._cameras.cam_key.return_value = 1
    window._set_zoom_feedback = Mock()
    window._update_exposure_ui = Mock()
    if kind == "zoom":
        window._refresh_zoom()
        callback = window._camera_port.refresh_zoom_display.call_args.args[1]
        callback(50)
    else:
        window._on_cam_connected(True, "192.0.2.1")
        callback = window._camera_port.async_refresh_ae_mode.call_args.args[1]
        callback()
    window._shutting_down = True
    _qapp.processEvents()
    window._set_zoom_feedback.assert_not_called()
    window._update_exposure_ui.assert_not_called()
    window.close()


@pytest.mark.parametrize("transition", ["ended", "restarted", "restarted_and_ended", "closing"])
def test_delayed_screen_sleep_belongs_to_ended_session(main_window, monkeypatch, transition):
    from unittest.mock import Mock
    from PyQt5.QtCore import QTimer
    import ui.main_window as module

    main_window._camera_port.refresh_zoom_display = Mock()
    main_window._camera_port.async_refresh_ae_mode = Mock()
    main_window._bus = Mock()
    main_window.session_active = True
    dialog = Mock()
    dialog.exec_.return_value = 1
    factory = Mock(return_value=dialog)
    factory.Accepted = 1
    monkeypatch.setattr(module, "ScreenOffDialog", factory)
    sleep = Mock()
    monkeypatch.setattr(module.ScreenMonitor, "sleep", sleep)
    monkeypatch.setattr(module.ScreenMonitor, "wake", Mock())
    callbacks = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: callbacks.append((delay, callback)))

    main_window._on_screen_turned_off()
    sleep_callback = next(callback for delay, callback in callbacks if delay == 1500)
    if transition in ("restarted", "restarted_and_ended"):
        main_window._session.ToggleSession()
        if transition == "restarted_and_ended":
            main_window._session.shutdown("manual")
    elif transition == "closing":
        main_window._shutting_down = True
    sleep_callback()

    if transition == "ended":
        sleep.assert_called_once_with()
    else:
        sleep.assert_not_called()


def test_recall_blocked_set_flashes_gear_when_visible(main_window, monkeypatch):
    """operator_no_set flashes the Settings gear while it is visible (ADMIN)."""
    panel = main_window._right_panel
    flashes = []
    monkeypatch.setattr(main_window, "_flash_blocked", flashes.append)
    monkeypatch.setattr(panel._btn_gear, "isVisible", lambda: True)
    main_window._handle_recall_blocked("operator_no_set", 3)
    assert flashes == [panel._btn_gear]


def test_recall_blocked_set_flashes_admin_entry_when_gear_hidden(main_window, monkeypatch):
    """operator_no_set with the gear hidden (USER) falls back to
    _btn_enter_admin. Regression net: the fallback previously referenced
    _btn_switch_admin, which never existed and raised AttributeError."""
    panel = main_window._right_panel
    flashes = []
    monkeypatch.setattr(main_window, "_flash_blocked", flashes.append)
    monkeypatch.setattr(panel._btn_gear, "isVisible", lambda: False)
    main_window._handle_recall_blocked("operator_no_set", 3)
    assert flashes == [panel._btn_enter_admin]


@pytest.fixture
def zoom_feedback_window(_qapp, sim_mode_active, monkeypatch):
    # These display tests never open even a synthetic camera TCP socket.
    from ui.main_window import MainWindow
    monkeypatch.setattr('simulation.sim_worker.start_simulation', lambda *args: None)
    monkeypatch.setattr('ui.camera_worker_startup.start_configured_camera_workers', lambda *args: None)
    window = MainWindow()
    try:
        yield window
    finally:
        window.close()


@pytest.mark.parametrize('selected', [True, False])
def test_reconnection_retires_old_zoom_and_refreshes_selected_camera(zoom_feedback_window, _qapp, monkeypatch, selected):
    from unittest.mock import Mock

    window = zoom_feedback_window
    window.Cam1.setChecked(True)
    window.session_active = True
    window._state.session.active = True
    window._set_zoom_feedback(10)
    port = window._camera_port
    monkeypatch.setattr(port, 'zoom_absolute', Mock())
    monkeypatch.setattr(window._cameras, 'cam_key', lambda ip: 1 if selected else 2)
    monkeypatch.setattr(port, 'async_refresh_ae_mode', Mock())
    invalidated = Mock()
    monkeypatch.setattr(port, 'invalidate_zoom', invalidated)
    def observed(key, callback):
        invalidated.assert_called_with(key)
        callback(77)
    refresh = Mock(side_effect=observed)
    monkeypatch.setattr(port, 'refresh_zoom_display', refresh)
    window._on_cam_connected(True, '192.0.2.1')
    _qapp.processEvents()
    invalidated.assert_called_once_with(1 if selected else 2)
    if selected:
        refresh.assert_called_once()
        assert window.ZoomValueLabel.text() == '77%'
        assert window._right_panel._joystick._ring_pct == 77
        port.zoom_absolute.assert_not_called()
        assert not window._zoom_timer.isActive()
    else:
        refresh.assert_not_called()
        assert window.ZoomValueLabel.text() == '10%'


@pytest.mark.parametrize('confirmed', [True, False])
def test_preset_completion_refreshes_zoom_without_camera_reselection(zoom_feedback_window, _qapp, monkeypatch, confirmed):
    from unittest.mock import Mock
    from core.events import EventType

    window = zoom_feedback_window
    window.Cam1.setChecked(True)
    window.session_active = True
    window._state.session.active = True
    window._set_zoom_feedback(10)
    port = window._camera_port
    monkeypatch.setattr(port, 'zoom_absolute', Mock())
    monkeypatch.setattr(port, 'recall_preset', Mock(return_value=confirmed))
    monkeypatch.setattr(port, 'invalidate_zoom', Mock())
    def observed(key, callback):
        port.invalidate_zoom.assert_called_with(key)
        callback(77)
    refresh = Mock(side_effect=observed)
    monkeypatch.setattr(port, 'refresh_zoom_display', refresh)
    window._bus.emit(EventType.SEAT_SELECTED, camera=1, preset=1)
    window._bus._queue.join()
    _qapp.processEvents()
    _qapp.processEvents()
    if confirmed:
        refresh.assert_called_once()
        assert window.ZoomValueLabel.text() == '77%'
        assert window._right_panel._joystick._ring_pct == 77
        port.zoom_absolute.assert_not_called()
        assert not window._zoom_timer.isActive()
    else:
        refresh.assert_not_called()
        assert window.ZoomValueLabel.text() == '10%'


@pytest.mark.parametrize('state', ['inactive', 'closing', 'other_camera'])
def test_zoom_invalidated_event_cannot_refresh_wrong_context(zoom_feedback_window, monkeypatch, state):
    from unittest.mock import Mock
    from core.events import Event, EventType
    window = zoom_feedback_window
    window.Cam1.setChecked(True)
    window.session_active = state != 'inactive'
    window._shutting_down = state == 'closing'
    refresh = Mock()
    monkeypatch.setattr(window, '_refresh_zoom', refresh)
    window._on_zoom_invalidated(Event(EventType.CAMERA_ZOOM_INVALIDATED,
        {'camera': 2 if state == 'other_camera' else 1}))
    refresh.assert_not_called()


@pytest.mark.parametrize('admitted,active', [(True, True), (False, True), (True, False)])
def test_comments_home_button_observes_zoom_without_claiming_home_completion(zoom_feedback_window, _qapp, monkeypatch, admitted, active):
    from unittest.mock import Mock

    window = zoom_feedback_window
    window.Cam2.setChecked(True)
    window.session_active = active
    window._state.session.active = active
    window._set_zoom_feedback(10)
    port = window._camera_port
    monkeypatch.setattr(port, 'home', Mock(return_value=admitted))
    monkeypatch.setattr(port, 'invalidate_zoom', Mock())
    monkeypatch.setattr(port, 'zoom_absolute', Mock())
    refresh = Mock(side_effect=lambda key, callback: callback(77))
    monkeypatch.setattr(port, 'refresh_zoom_display', refresh)
    # Match the live active-session control state before clicking the real button.
    from domain.call_set_policy import OperatingMode
    window._access_mode_svc.set_mode(OperatingMode.USER)
    window.Cam2.set_connected(True)
    window._update_controls_visibility()
    window._right_panel._home_btn.setEnabled(True)
    window._right_panel._home_btn.click()
    window._bus._queue.join()
    _qapp.processEvents()
    _qapp.processEvents()
    if active:
        port.home.assert_called_once_with('cam2')
    else:
        port.home.assert_not_called()
    if admitted and active:
        port.invalidate_zoom.assert_called_once_with(2)
        refresh.assert_called_once()
        assert window.ZoomValueLabel.text() == '77%'
        assert window._right_panel._joystick._ring_pct == 77
    else:
        port.invalidate_zoom.assert_not_called()
        refresh.assert_not_called()
        assert window.ZoomValueLabel.text() == '10%'
    port.zoom_absolute.assert_not_called()
    assert not window._zoom_timer.isActive()


@pytest.mark.parametrize('values', [(70,), (70, 10)])
def test_zoom_readback_cannot_replace_newer_slider_intent(zoom_feedback_window, _qapp, monkeypatch, values):
    from unittest.mock import Mock
    window = zoom_feedback_window
    window._set_zoom_feedback(10)
    callbacks = []
    monkeypatch.setattr(window._camera_port, 'refresh_zoom_display',
                        lambda key, callback: callbacks.append(callback))
    monkeypatch.setattr(window._camera_port, 'zoom_absolute', Mock())
    window._refresh_zoom()
    for value in values:
        window.ZoomSlider.setValue(value)
    callbacks[0](23)
    _qapp.processEvents()
    assert window.ZoomSlider.value() == values[-1]
    window._camera_port.zoom_absolute.assert_not_called()
    window._zoom_timer.stop()


def test_comments_home_button_only_flashes_on_confirmed_save(zoom_feedback_window, _qapp):
    """Regresión: el botón Comments Home no anuncia éxito sin confirmación real.

    Una petición de guardado sin sesión (rechazada por el controller) no debe
    mover el botón; el éxito o el fallo solo aparecen cuando llega el evento
    de resultado confirmado.
    """
    from core.events import EventType

    window = zoom_feedback_window
    btn = window._right_panel._home_btn
    assert btn.text() == 'Comments → Home'

    window._bus.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
    window._bus._queue.join()
    _qapp.processEvents()
    _qapp.processEvents()
    assert btn.text() == 'Comments → Home'  # sin sesión: rechazado, sin feedback falso

    window._bus.emit(EventType.COMMENTS_HOME_SAVE_FAILED, camera=2)
    window._bus._queue.join()
    _qapp.processEvents()
    _qapp.processEvents()
    assert btn.text() == 'Save failed'

    window._bus.emit(EventType.COMMENTS_HOME_SAVED, camera=2, slot=3)
    window._bus._queue.join()
    _qapp.processEvents()
    _qapp.processEvents()
    assert btn.text() == 'Position saved ✓'
