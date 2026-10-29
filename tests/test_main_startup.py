#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests del bootstrap de main.py sin cargar Qt real ni construir la UI real.
"""

import importlib
import sys
import types

import pytest


class _ExitCalled(BaseException):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@pytest.fixture()
def main_module(monkeypatch):
    calls = []

    # Ensure the real data_paths is in sys.modules first, so monkeypatch.setitem
    # captures it as the restore target and reinstates it on teardown — otherwise
    # the stub below can leak to later tests that do `from data_paths import ...`.
    importlib.import_module("data_paths")

    data_paths = types.ModuleType("data_paths")
    data_paths.migrate_legacy_files = lambda: calls.append("migrate")

    power_management = types.ModuleType("power_management")
    power_management.disable_screen_blanking = lambda: calls.append("screen_blanking")

    widgets = types.ModuleType("PyQt5.QtWidgets")

    class FakeApplication:
        def __init__(self, argv):
            calls.append("qapplication")
            self.argv = argv

        def setStyleSheet(self, _qss):
            pass

        def exec_(self):
            calls.append("exec")
            return 0

    class FakeMessageBox:
        @staticmethod
        def critical(*_args, **_kwargs):
            calls.append("critical")

    widgets.QApplication = FakeApplication
    widgets.QMessageBox = FakeMessageBox

    pyqt5 = types.ModuleType("PyQt5")
    pyqt5.QtWidgets = widgets

    main_window = types.ModuleType("main_window")

    class FakeMainWindow:
        def __init__(self):
            calls.append("main_window")

        def show(self):
            calls.append("show")

        def showFullScreen(self):
            calls.append("show_fullscreen")

    main_window.MainWindow = FakeMainWindow

    virtual_keyboard = types.ModuleType("virtual_keyboard")
    virtual_keyboard.install_virtual_keyboard = lambda app: calls.append("keyboard")

    sim_mode = types.ModuleType("adapters.sim_mode")
    sim_mode.is_active = lambda: False

    import adapters as _adapters_pkg

    monkeypatch.setitem(sys.modules, "data_paths", data_paths)
    monkeypatch.setitem(sys.modules, "adapters.power_management", power_management)
    monkeypatch.setitem(sys.modules, "PyQt5", pyqt5)
    monkeypatch.setitem(sys.modules, "PyQt5.QtWidgets", widgets)
    monkeypatch.setitem(sys.modules, "ui.main_window", main_window)
    monkeypatch.setitem(sys.modules, "ui.virtual_keyboard", virtual_keyboard)
    monkeypatch.setitem(sys.modules, "adapters.sim_mode", sim_mode)
    # CPython IMPORT_FROM reads the package attribute, not sys.modules, for
    # `import adapters.sim_mode as _sim_mode` — patch both. raising=False so the
    # test passes in isolation (the "startup smoke" CI job), where nothing has
    # imported adapters.sim_mode yet and the package attribute does not exist.
    monkeypatch.setattr(_adapters_pkg, "sim_mode", sim_mode, raising=False)
    sys.modules.pop("main", None)

    try:
        module = importlib.import_module("main")
        module._test_calls = calls
        module._test_sim_mode = sim_mode
        monkeypatch.setattr(module.sys, "exit", lambda code=0: (_ for _ in ()).throw(_ExitCalled(code)))
        yield module
    finally:
        sys.modules.pop("main", None)


@pytest.fixture()
def failing_main_module(monkeypatch):
    calls = []

    # See main_module: load the real data_paths first so monkeypatch restores it.
    importlib.import_module("data_paths")

    data_paths = types.ModuleType("data_paths")
    data_paths.migrate_legacy_files = lambda: calls.append("migrate")

    power_management = types.ModuleType("power_management")
    power_management.disable_screen_blanking = lambda: calls.append("screen_blanking")

    widgets = types.ModuleType("PyQt5.QtWidgets")

    class FakeApplication:
        def __init__(self, argv):
            calls.append("qapplication")
            self.argv = argv

        def setStyleSheet(self, _qss):
            pass

        def exec_(self):
            calls.append("exec")
            return 0

    class FakeMessageBox:
        @staticmethod
        def critical(*_args, **_kwargs):
            calls.append("critical")

    widgets.QApplication = FakeApplication
    widgets.QMessageBox = FakeMessageBox

    pyqt5 = types.ModuleType("PyQt5")
    pyqt5.QtWidgets = widgets

    main_window = types.ModuleType("main_window")

    class FailingMainWindow:
        def __init__(self):
            calls.append("main_window")
            raise RuntimeError("boom")

    main_window.MainWindow = FailingMainWindow

    virtual_keyboard = types.ModuleType("virtual_keyboard")
    virtual_keyboard.install_virtual_keyboard = lambda app: calls.append("keyboard")

    sim_mode = types.ModuleType("adapters.sim_mode")
    sim_mode.is_active = lambda: False

    import adapters as _adapters_pkg

    monkeypatch.setitem(sys.modules, "data_paths", data_paths)
    monkeypatch.setitem(sys.modules, "adapters.power_management", power_management)
    monkeypatch.setitem(sys.modules, "PyQt5", pyqt5)
    monkeypatch.setitem(sys.modules, "PyQt5.QtWidgets", widgets)
    monkeypatch.setitem(sys.modules, "ui.main_window", main_window)
    monkeypatch.setitem(sys.modules, "ui.virtual_keyboard", virtual_keyboard)
    monkeypatch.setitem(sys.modules, "adapters.sim_mode", sim_mode)
    # raising=False: the package attribute does not exist when this test file
    # runs in isolation (the "startup smoke" CI job).
    monkeypatch.setattr(_adapters_pkg, "sim_mode", sim_mode, raising=False)
    sys.modules.pop("main", None)

    try:
        module = importlib.import_module("main")
        module._test_calls = calls
        monkeypatch.setattr(module.sys, "exit", lambda code=0: (_ for _ in ()).throw(_ExitCalled(code)))
        yield module
    finally:
        sys.modules.pop("main", None)


class TestMainStartup:

    def test_migrates_legacy_files_before_qapplication(self, main_module):
        with pytest.raises(_ExitCalled) as exc:
            main_module.main()

        assert exc.value.code == 0
        assert main_module._test_calls[:3] == ["migrate", "screen_blanking", "qapplication"]

    def test_installs_keyboard_before_main_window(self, main_module):
        with pytest.raises(_ExitCalled):
            main_module.main()

        assert main_module._test_calls.index("keyboard") < main_module._test_calls.index("main_window")

    def test_normal_mode_starts_fullscreen(self, main_module):
        with pytest.raises(_ExitCalled):
            main_module.main()

        assert "show_fullscreen" in main_module._test_calls
        assert "show" not in main_module._test_calls

    def test_sim_mode_starts_windowed(self, main_module):
        main_module._test_sim_mode.is_active = lambda: True

        with pytest.raises(_ExitCalled):
            main_module.main()

        assert "show" in main_module._test_calls
        assert "show_fullscreen" not in main_module._test_calls

    def test_startup_error_shows_critical_message_and_exits_1(self, failing_main_module):
        with pytest.raises(_ExitCalled) as exc:
            failing_main_module.main()

        assert exc.value.code == 1
        assert "critical" in failing_main_module._test_calls
        assert "exec" not in failing_main_module._test_calls
