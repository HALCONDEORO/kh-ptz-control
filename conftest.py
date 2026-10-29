# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PYTEST_RUNTIME_DIR = ROOT / ".pytest-runtime"
PYTEST_DATA_DIR = PYTEST_RUNTIME_DIR / "data"
PYTEST_PASSWORD_FILE = PYTEST_RUNTIME_DIR / "password.enc"

sys.path.insert(0, str(ROOT))

# Mantiene los tests lejos de los datos reales del operador y hace Qt
# importable en ejecuciones headless de CI/local.
os.environ.setdefault("KHPTZ_DATA_DIR", str(PYTEST_DATA_DIR))
os.environ.setdefault("KHPTZ_DATA_DIR", str(PYTEST_DATA_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The crash reporter falls back to the user state directory when the production
# log path is unwritable (#884). Without this, a test exercising that path
# writes into the developer's real ~/.local/state.
os.environ.setdefault("XDG_STATE_HOME", str(PYTEST_RUNTIME_DIR / "state"))

# Force the REAL PyQt5 into sys.modules before any test module is collected.
# Several test files inject a bare PyQt5 ModuleType stub (unittest.mock-based
# QWidget/QObject) so they can drive unbound methods with a MagicMock self,
# guarded by "if mod_name not in sys.modules". That guard only protects
# against a *later* real import — if a stubbing file is collected first (as
# can happen once the suite is split into smaller chunks/subsets, since
# collection order accidents that used to protect it no longer hold), the
# fake QtCore.QObject poisons every other file's real Qt import for the rest
# of the process (e.g. ptz.visca.worker's `from PyQt5.QtCore import QObject`
# breaks with ImportError). Importing for real here, before collection even
# starts, makes every such guard see the real module already present and
# skip stubbing. Best-effort: environments without PyQt5 installed keep
# working exactly as before.
try:
    import PyQt5.QtCore  # noqa: F401
    import PyQt5.QtGui  # noqa: F401
    import PyQt5.QtWidgets  # noqa: F401
except ImportError:
    pass

# Same reasoning, same fix, for data_paths: test_camera_worker.py and
# test_visca_worker_extra.py each inject a bare data_paths stub (missing most
# of the real module's constants, e.g. ROOM_LAYOUT_FILE) so ptz.visca.worker's
# transitive `from data_paths import ...` succeeds without touching real user
# config paths during collection — and both already pop/restore it right
# after their own import, so this is *not* needed for their own tests'
# correctness (verified: neither asserts against the stub's fake path
# values). Importing for real first means their "if not already in
# sys.modules" guard sees the real module and never stubs at all.
import data_paths  # noqa: F401

# ── Collection-time stub leakage ─────────────────────────────────────────────
# Several test files inject a bare ModuleType into sys.modules at import time,
# guarded by "if '<module>' not in sys.modules", so their subject imports
# without a QApplication. The stub carries only the two or three names that file
# needs and is never removed, so the next module collected that imports the real
# one raises — and an ImportError during collection aborts the WHOLE suite
# (pytest exits 2 without running a single test). That is what CI kept hitting:
#
#   ERROR collecting tests/test_startup_power_prompt.py
#   ui/main_window.py: from ui.widgets import ... PlatformPresetButton
#   ImportError: cannot import name 'PlatformPresetButton' (unknown location)
#
# Drop those leaked stubs between test modules instead of pre-importing the real
# ones here. The stubbing file's own subject already bound the fake classes into
# its namespace at import time, so removing the sys.modules entry afterwards
# costs it nothing (test_seat_builder.py has always done exactly this by hand),
# and a file that still wants a stub simply re-injects it — its guard sees the
# name absent again. Importing the real ui.* modules in this process instead
# would work too, but this file runs in the pytest-forked MASTER process, and
# every module imported here is inherited by every forked child; keeping Qt out
# of the master is the whole reason no QApplication is built here either.
_LEAKY_STUB_MODULES = (
    "ui.widgets", "ui.platform_icons",
    "adapters.sim_mode", "application.camera_discovery",
)


def pytest_collectstart(collector):
    """Purge bare-ModuleType stubs an earlier test module left behind."""
    if type(collector).__name__ != "Module":
        return
    for _name in _LEAKY_STUB_MODULES:
        _mod = sys.modules.get(_name)
        if _mod is not None and getattr(_mod, "__file__", None) is None:
            del sys.modules[_name]

# NOTE: deliberately NOT constructing a QApplication here. This module runs
# once in the pytest-forked *master* process before any test forks — a
# QApplication built here would carry Qt's internal C++/thread state across
# fork(), which Qt does not support and reliably aborts a forked child the
# first time it touches Qt (see the _qapp_available autouse fixture below for
# the fork-safe replacement, and issue #873 for the full story).

# config.py descifra la contraseña durante el import. En CI no existe
# password.enc real, así que los tests usan un archivo cifrado temporal.
PYTEST_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
import runtime.secret_manager as _secret_manager

_secret_manager._ENC_FILE = PYTEST_PASSWORD_FILE
if not PYTEST_PASSWORD_FILE.exists():
    _secret_manager.encrypt_password("pytest-password")


# ── Test isolation: clear hardware_simulator queues between tests ─────────────
# atem_event_queue and pip_event_queue are module-level Queue instances.
# Without cleanup, events left by one test contaminate the next test's
# simulation run, causing order-dependent failures.

import logging as _logging
import pytest as _pytest

_conftest_log = _logging.getLogger("conftest")


def ensure_real_qt() -> None:
    """Guarantee the real PyQt5 is in sys.modules (drop any collection-time stub).

    Several test modules (test_login_screen_password_warning.py and others)
    inject bare PyQt5 ModuleType stubs into sys.modules at collection time so
    they can drive Qt-touching methods unbound with a MagicMock self, without
    a real QApplication. If one of those modules is collected first, its stub
    wins the race and sys.modules["PyQt5.QtWidgets"] stays fake for the rest
    of the session. This only swaps the PyQt5.* entries themselves — safe,
    since nothing string-patches "PyQt5.QtWidgets.X" — and does NOT touch any
    ui.* module: a ui.* module already imported under the stub has its widget
    class permanently baked against MagicMock (fixing PyQt5 afterwards can't
    retroactively fix an already-defined class), and popping/reimporting that
    ui.* module here would break OTHER test files that string-patch it (e.g.
    patch("ui.login_screen.password_is_configured", ...) resolves against
    whatever module object is currently in sys.modules — swap it out from
    under them and the patch silently stops taking effect on the code those
    files actually exercise). Use is_poisoned_by_qt_stub() to detect and skip
    a widget class that got baked against a stub instead.
    """
    for name in ("PyQt5.QtWidgets", "PyQt5.QtGui", "PyQt5.QtCore", "PyQt5"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None) is None:
            sys.modules.pop(name, None)  # bare ModuleType stub → drop it
    import PyQt5.QtWidgets  # noqa: F401  (force real import)


def is_poisoned_by_qt_stub(widget_class: type) -> bool:
    """True if widget_class was defined against a MagicMock PyQt5 stub.

    A test module that wins the collection-order race (see ensure_real_qt)
    can cause a production ui.* module to import PyQt5 under a fake stub, so
    its widget class ends up inheriting from unittest.mock.MagicMock instead
    of the real Qt base class — permanently, since this is decided at
    class-definition time. Constructing that hybrid real/fake object later
    aborts the process (Fatal Python error: Aborted). Call this from a test
    that builds a *real* widget and pytest.skip() if it returns True, rather
    than trying to force a fresh import (see ensure_real_qt's docstring for
    why that mutation is unsafe).
    """
    return any(cls.__module__ == "unittest.mock" for cls in widget_class.__mro__)


@_pytest.fixture(autouse=True)
def _qapp_available():
    """Ensure a QApplication exists in *this* test's process before it runs.

    PyQt5 aborts the process (SIGABRT, not a catchable exception) if any
    QWidget is constructed before a QApplication exists — and several
    production methods build a real widget directly even when called from a
    test with a MagicMock self (e.g. AtemAdminPanel.update_input_names's bare
    `QPushButton(...)`; nothing on that path checks for a QApplication on the
    Python side). Under pytest-forked, each test runs in its own forked
    child, so this must create the QApplication fresh *inside* that child —
    building it once in conftest.py's module-level code (which only runs in
    the pre-fork master process) would instead hand every child an already-
    initialized QApplication carrying Qt's internal C++/thread state across
    fork(), which Qt does not support and aborts on first use (this is what
    broke test_login_countdown_integration.py's and test_setup_wizard.py's
    own module-scoped `qapp`/`_qapp` fixtures — fixed there by making them
    function-scoped so they no longer rely on cross-fork sharing either). A
    plain autouse function-scoped fixture runs fresh per test/per fork, which
    is exactly what's needed here. No-op when PyQt5 is absent or stubbed.
    """
    qtw = sys.modules.get("PyQt5.QtWidgets")
    if qtw is None or getattr(qtw, "__file__", None) is None:
        return
    try:
        if qtw.QApplication.instance() is None:
            qtw.QApplication([])
    except Exception:  # noqa: BLE001 — best-effort, never block a test on this
        pass


@_pytest.fixture(autouse=True)
def _qt_widget_cleanup():
    """Destroy leftover Qt top-level widgets after each test.

    Prevents cross-test segfaults under the offscreen platform: a widget left
    alive by one Qt test (e.g. a panel created in an xfail smoke test) and then
    garbage-collected while a later test drives a different widget tree can crash
    the interpreter. No-op when PyQt5 is absent or only a bare stub is loaded.
    """
    yield
    qtw = sys.modules.get("PyQt5.QtWidgets")
    if qtw is None or getattr(qtw, "__file__", None) is None:
        return
    try:
        app = qtw.QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            widget.close()
            widget.deleteLater()
        # deleteLater only frees on the next event-loop pass; under the offscreen
        # platform we must flush the DeferredDelete queue explicitly, otherwise
        # widgets accumulate across modules and eventually segfault a later
        # real-Qt test (the setup wizard) at module transition.
        qtc = sys.modules.get("PyQt5.QtCore")
        if qtc is not None:
            app.sendPostedEvents(None, qtc.QEvent.DeferredDelete)
        app.processEvents()
    except Exception:  # noqa: BLE001 — cleanup must never fail a test
        pass


@_pytest.fixture(autouse=True)
def _clear_simulator_queues():
    """Drain both hardware-simulator event queues before AND after each test."""
    import queue as _q
    def _drain(q: _q.Queue) -> None:
        while True:
            try:
                q.get_nowait()
            except _q.Empty:
                break

    def _drain_all() -> None:
        try:
            import adapters.hardware_simulator as _hw
            _drain(_hw.atem_event_queue)
            _drain(_hw.pip_event_queue)
        except ImportError as _e:
            _conftest_log.debug("hardware_simulator not loaded — queues not drained: %s", _e)

    _drain_all()   # drain before test
    yield
    _drain_all()   # drain after test


# ── Test isolation: redirect atem_mapping.json writes to a temp file ──────────
# Tests that call set_pip_automation_enabled() or update_mapping() without
# patching _save_mapping would write to the real runtime data path
# (e.g. /var/lib/khptz/atem_mapping.json), contaminating subsequent non-mocked
# dispatchers.  This fixture redirects _mapping_file() to an isolated per-test
# temp path for the duration of each test.
#
# tests/test_atem_mapping_location.py deliberately opts out: it is ABOUT which
# directory that function resolves to, so it restores the real implementation
# (captured at its own import time) inside its own fixtures.

@_pytest.fixture(autouse=True)
def _isolate_atem_mapping(tmp_path, monkeypatch):
    """Redirect atem_dispatcher._mapping_file to a per-test temp path."""
    try:
        import adapters.atem_dispatcher as _disp
        _test_path = tmp_path / "atem_mapping.json"
        monkeypatch.setattr(_disp, "_mapping_file", lambda: _test_path)
    except ImportError:
        pass
    yield
