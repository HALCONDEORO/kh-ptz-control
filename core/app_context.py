#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# app_context.py — Contenedor de dependencias de la aplicación
#
# AppContext agrupa todos los objetos de servicio construidos por bootstrap.py
# y los entrega a MainWindow en lugar de que la UI los instancie directamente.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.state import SystemState
from core.events import AsyncEventBus
from application.preset_service import PresetService
from application.session_service import SessionService
from application.app_controller import ApplicationController
from core.controller import Controller

if TYPE_CHECKING:
    from ports.camera_port import CameraPort
    from application.layout_service import LayoutService
    from application.runtime_state_store import RuntimeStateStore
    from application.runtime_audit_log import RuntimeAuditLog


@dataclass
class AppContext:
    state: SystemState
    bus: AsyncEventBus
    preset_svc: PresetService
    camera_port: CameraPort
    session_svc: SessionService
    controller: Controller
    app_ctrl: ApplicationController
    flight_recorder: Optional[object] = field(default=None)
    layout_svc: "Optional[LayoutService]" = field(default=None)
    camera_target_resolver: Optional[object] = field(default=None)
    runtime_state_store: "Optional[RuntimeStateStore]" = field(default=None)
    runtime_audit_log: "Optional[RuntimeAuditLog]" = field(default=None)
