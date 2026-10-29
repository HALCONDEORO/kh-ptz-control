#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ptz/visca/__init__.py — API pública del paquete VISCA

from .types import PanDir, TiltDir, ZOOM_MAX
from .errors import ViscaError, ViscaNetworkError, ViscaParseError
from . import commands, parser
_LAZY_EXPORTS = {
    "CameraWorker": (".worker", "CameraWorker"),
    "CameraWorkerSignals": (".worker", "CameraWorkerSignals"),
    "ViscaCommand": (".worker", "ViscaCommand"),
    "CameraManager": (".manager", "CameraManager"),
}


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "PanDir", "TiltDir", "ZOOM_MAX",
    "ViscaError", "ViscaNetworkError", "ViscaParseError",
    "commands", "parser",
    "CameraWorker", "CameraWorkerSignals", "ViscaCommand",
    "CameraManager",
]
