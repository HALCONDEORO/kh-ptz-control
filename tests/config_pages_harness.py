#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Test doubles for the ConfigDialog tab builders (ui/config_pages/*).

Each ``build_*_tab(dialog, layout, mw, …)`` function is a slice of what used to
be ConfigDialog._build_ui. Driving it needs two collaborators:

  * the *dialog*, for the styled-widget helpers and operator feedback;
  * the *main window*, for the services the controls act on.

Building a real ConfigDialog would drag in a real MainWindow, so this module
provides doubles instead. The dialog double deliberately reuses ConfigDialog's
own static helpers (``_btn``, ``_field_row``, ``_cam_panel``, …) so the widget
tree under test is the real one — only the interactive parts (toasts, modal
confirmations, closing) are recorded rather than shown. What is stubbed here is
therefore also the contract the tabs rely on: if ConfigDialog loses one of these
members, importing this module fails and the tab tests say so.

Everything is built lazily inside ``make_harness`` because other test modules
inject bare PyQt5 stubs at collection time.
"""

from __future__ import annotations

#: Keeps the QApplication alive for the whole session. Without a strong
#: reference the freshly built application is garbage-collected the moment
#: make_harness returns, and the next QWidget construction aborts the process.
_QAPP = None


def make_harness(*, sim_active: bool = False, session_active: bool = False,
                 visible: bool = True, confirm: bool = True):
    """Return ``(dialog, mw, layout)`` ready to hand to a tab builder."""
    global _QAPP

    from conftest import ensure_real_qt
    ensure_real_qt()

    import sys

    from PyQt5.QtCore import QObject, pyqtSignal
    from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

    # Constructing a QWidget without a live QApplication aborts the process
    # (SIGABRT, not an exception). conftest's autouse fixture is best-effort, so
    # build one here and hold the reference in a module global.
    _QAPP = QApplication.instance() or QApplication(sys.argv)

    from ui.config_dialog import ConfigDialog

    class _Result:
        """Stands in for an application-service OperationResult."""

        def __init__(self, ok: bool = True, code: str = "OK"):
            self.ok = ok
            self.code = code

    class _CameraConfigDouble:
        """Records camera/ATEM writes instead of touching config.yaml."""

        def __init__(self, result: _Result | None = None):
            self.result = result if result is not None else _Result()
            self.camera_ips: list[tuple[int, str]] = []
            self.atem_ips: list[str] = []

        def set_camera_ip(self, cam_num: int, ip: str):
            self.camera_ips.append((cam_num, ip))
            # The real CameraConfigService updates the in-memory camera before
            # persisting, and the tab's connectivity re-check reads it back from
            # config — so the double has to do the same or the re-check probes a
            # stale address. Callers monkeypatch config.CAM*.ip, which reverts
            # this at teardown.
            import config
            camera = config.CAM1 if cam_num == 1 else config.CAM2
            if hasattr(camera, "ip"):
                camera.ip = ip
            return self.result

        def set_atem_ip(self, ip: str):
            self.atem_ips.append(ip)
            return self.result

    class _Recorder:
        """Counts calls to whichever attribute is asked for."""

        def __init__(self):
            self.calls: list[str] = []

        def __getattr__(self, name):
            def _record(*args, **kwargs):
                self.calls.append(name)
            return _record

    class _AccessModeDouble:
        def __init__(self, mode):
            self.mode = mode
            self.applied: list = []
            self.subscribers: list = []

        def set_mode(self, mode):
            self.mode = mode
            self.applied.append(mode)
            for callback in self.subscribers:
                callback(mode)

        def subscribe(self, callback):
            self.subscribers.append(callback)

    class _AtemMonitorDouble:
        def __init__(self, state=None, last_error: str = ""):
            self.state = state
            self.last_error = last_error

    class _CameraServiceDouble:
        """Records preset recalls instead of driving VISCA."""

        def __init__(self):
            self.recalls: list[tuple[int, int]] = []
            self.result = True

        def recall_preset(self, cam: int, slot: int):
            self.recalls.append((cam, slot))
            return self.result

    class _MainWindowDouble(QObject):
        """Only the members the tabs actually reach for."""

        atem_state_changed = pyqtSignal(object)

        def __init__(self):
            super().__init__()
            from domain.call_set_policy import OperatingMode

            self.session_active = session_active
            self._session = _Recorder()
            self._dialogs = _Recorder()
            self._cameras = _Recorder()
            self._camera_config = _CameraConfigDouble()
            self._access_mode_svc = _AccessModeDouble(OperatingMode.CAMERA_OPERATOR)
            self._right_panel = _Recorder()
            self._atem_monitor = _AtemMonitorDouble()
            # None keeps the automation sub-section in its "unavailable" branch:
            # it belongs to ui/config_pages/sections.py, not to the tab builders.
            self._atem_dispatcher = None
            self._atem_panel = None
            self._camera_svc = _CameraServiceDouble()
            self.restarts = 0
            self.panel_toggles = 0
            self.second_platform_visibility: list[bool] = []

        def _do_restart_atem_monitor(self):
            self.restarts += 1

        def _toggle_atem_panel(self):
            self.panel_toggles += 1

        def apply_second_platform_visibility(self, value: bool):
            self.second_platform_visibility.append(value)

    class _DialogDouble(QDialog):
        """ConfigDialog's helper surface, with feedback recorded."""

        # The real, shared widget builders — the tabs must keep working with
        # exactly these.
        _btn = staticmethod(ConfigDialog._btn)
        _field_row = staticmethod(ConfigDialog._field_row)
        _status_pill = staticmethod(ConfigDialog._status_pill)
        _info_line = staticmethod(ConfigDialog._info_line)
        _cam_panel = staticmethod(ConfigDialog._cam_panel)
        _set_led = staticmethod(ConfigDialog._set_led)
        _set_online_badge = staticmethod(ConfigDialog._set_online_badge)
        _led = staticmethod(ConfigDialog._led)
        _lock_if_live = staticmethod(ConfigDialog._lock_if_live)
        _session_lock_banner = staticmethod(ConfigDialog._session_lock_banner)
        _disconnect_signal = staticmethod(ConfigDialog._disconnect_signal)
        _current_runtime_mode = staticmethod(ConfigDialog._current_runtime_mode)

        # Class-level default on purpose: QDialog's constructor calls isVisible()
        # internally, i.e. before __init__ can set an instance attribute, and an
        # AttributeError raised inside that virtual call aborts the process.
        _pretend_visible = True

        def __init__(self):
            super().__init__()
            self.toasts: list[tuple[str, str]] = []
            self.confirmations: list[str] = []
            self.confirm_answer = confirm
            self.accepted_count = 0
            self.closed_count = 0
            self.restart_requests: list[str] = []
            self._pretend_visible = visible

        def _restart_in_runtime_mode(self, mw, target: str):
            """Recorded, never performed — the real one re-execs the process."""
            self.restart_requests.append(target)

        # ── recorded operator feedback ───────────────────────────────────
        def _toast(self, message: str, kind: str = 'ok', duration: int = 2800):
            self.toasts.append((message, kind))

        def _confirm_danger(self, title: str, text: str, action_label: str) -> bool:
            self.confirmations.append(title)
            return self.confirm_answer

        def _try_close(self):
            self.closed_count += 1

        def accept(self):
            self.accepted_count += 1

        # A tab that updates widgets after the dialog is gone would crash on a
        # real appliance; the builders guard with isVisible(), so the double has
        # to be able to say "no" without going through a real show/hide.
        def isVisible(self) -> bool:            # noqa: N802 - Qt naming
            return self._pretend_visible

    dialog = _DialogDouble()
    host = QWidget(dialog)
    layout = QVBoxLayout(host)
    return dialog, _MainWindowDouble(), layout


def panel_layout(parent_layout, title_text: str, badge_text=None,
                 badge_kind: str = 'muted', accent=None):
    """Stand-in for ConfigDialog._build_ui's local card-layout helper.

    The real one wraps each section in a styled card; the tabs only ever use the
    returned layout, so a nested QVBoxLayout is enough — and it keeps the tests
    about behaviour rather than card chrome.
    """
    from PyQt5.QtWidgets import QVBoxLayout

    inner = QVBoxLayout()
    inner.setObjectName(title_text)
    parent_layout.addLayout(inner)
    return inner


class AtemDispatcherDouble:
    """Stand-in for adapters.atem_dispatcher — arming and the reconnect guard.

    Plain object on purpose: the automation section only reads ``armed`` /
    ``reconnect_guard`` and calls ``set_armed`` / ``clear_reconnect_guard``.
    """

    def __init__(self, armed: bool = False, reconnect_guard: bool = False):
        self.armed = armed
        self.reconnect_guard = reconnect_guard
        self.arm_calls: list[bool] = []
        self.guard_clears = 0

    def set_armed(self, value: bool) -> None:
        self.armed = bool(value)
        self.arm_calls.append(bool(value))

    def clear_reconnect_guard(self) -> None:
        self.reconnect_guard = False
        self.guard_clears += 1


def run_threads_inline(monkeypatch, module) -> None:
    """Make *module*'s ``threading.Thread(...).start()`` run the target inline.

    The tabs push blocking probes (network scans, diagnostics) onto worker
    threads and marshal the result back with a queued signal. Running the target
    on the calling thread keeps the tests deterministic and turns the queued
    emission into a direct call, so the GUI-side handler is exercised too.
    """
    class _InlineThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}
            self.daemon = daemon

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

        def join(self, timeout=None):
            pass

    class _ThreadingModule:
        Thread = _InlineThread

    monkeypatch.setattr(module, "threading", _ThreadingModule)


def buttons(layout) -> list:
    """Every QPushButton below *layout*'s parent widget, in creation order."""
    from PyQt5.QtWidgets import QPushButton

    widget = layout.parentWidget()
    return widget.findChildren(QPushButton)


def button_named(layout, text: str):
    """The first button whose label contains *text* (case-insensitive)."""
    for btn in buttons(layout):
        if text.lower() in btn.text().lower():
            return btn
    raise AssertionError(
        f"no button matching {text!r}; found: {[b.text() for b in buttons(layout)]}"
    )


def labels(layout) -> list:
    from PyQt5.QtWidgets import QLabel

    return layout.parentWidget().findChildren(QLabel)


def label_texts(layout) -> list[str]:
    return [lb.text() for lb in labels(layout)]


def has_text(layout, needle: str) -> bool:
    return any(needle.lower() in text.lower() for text in label_texts(layout))
