#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# main.py — Punto de entrada de la aplicación
#
# Wire-up mínimo: todo el estado, servicios y controller se instancian
# dentro de MainWindow.__init__ para mantener el arranque simple y testeable.
#
# Flujo completo: Login → Splash → MainWindow (ready)
#   MainWindow construye:
#     SystemState, AsyncEventBus, PresetService, ViscaCameraAdapter,
#     SessionService, Controller

from __future__ import annotations

import signal
import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox

import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from data_paths import migrate_legacy_files
from app_version import app_version_label
from core.logging_utils import install_repeated_message_filter
from ui.main_window import MainWindow
from adapters.power_management import disable_screen_blanking
from ui.virtual_keyboard import install_virtual_keyboard
import adapters.sim_mode as _sim_mode

def _init_logging() -> None:
    from runtime.logging_setup import setup_logging, log_startup_summary
    from runtime.path_resolver import RuntimePathResolver
    from runtime.build_info import build_info
    from application.crash_reporter import install_crash_reporter
    resolver = RuntimePathResolver()
    info = build_info(data_dir=resolver.data_dir)
    log_dir = None if resolver.running_from_source else resolver.log_dir
    setup_logging(log_dir=log_dir, version_line=info.version_line())

    # The GUI is the process that actually crashes on an appliance, yet the
    # crash reporter was only ever installed by the `hallptz` CLI — so the field
    # failures that ended in `status=6/ABRT` left nothing behind but a
    # photograph of the screen. PyQt5 passes an unhandled exception raised in a
    # slot to sys.excepthook *before* calling qFatal()/abort(), so installing it
    # here is what turns those aborts into a readable report.
    install_crash_reporter(
        version=info.version_line(),
        mode=info.runtime_profile,
        log_dir=log_dir,
    )

    log_startup_summary(resolver, mode=info.runtime_profile)

logger = logging.getLogger(__name__)


def main():
    _init_logging()
    install_repeated_message_filter()

    # Legacy migration and screen-blanking are conveniences, not preconditions.
    # They touch the filesystem and the X server, so on a Pi with an unexpected
    # data layout or no display yet either can raise — and raising here, before
    # the Qt try/except below, killed the whole application with nothing but a
    # traceback. Under systemd that is a restart loop for a non-essential step.
    for _step in (migrate_legacy_files, disable_screen_blanking):
        try:
            _step()
        except Exception as exc:  # noqa: BLE001 — never block startup on these
            logger.warning(
                "Startup step %s failed (continuing): %s",
                getattr(_step, "__name__", _step), exc, exc_info=True,
            )

    app = None
    try:
        app = QApplication(sys.argv)
        signal.signal(signal.SIGTERM, lambda *_: app.quit())
        from ui.styles import message_box_qss
        app.setStyleSheet(message_box_qss())
        install_virtual_keyboard(app)

        main_win = MainWindow()
        if _sim_mode.is_active():
            main_win.show()
        else:
            main_win.showFullScreen()

        logger.info("Application started: %s", app_version_label())
        sys.exit(app.exec_())

    except Exception as exc:
        logger.error("Fatal error in main(): %s", exc, exc_info=True)
        if app is not None:
            QMessageBox.critical(
                None,
                "Fatal Error",
                f"Failed to start application:\n{exc}"
            )
        sys.exit(1)


if __name__ == '__main__':
    main()
