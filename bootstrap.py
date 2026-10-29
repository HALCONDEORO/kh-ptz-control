#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# bootstrap.py — Punto único de composición de servicios
#
# build_app_context() construye el grafo de dependencias de la aplicación y
# devuelve un AppContext listo para entregar a MainWindow.
#
# Regla: ningún otro sitio del código debe instanciar SystemState, AsyncEventBus,
# PresetService, ViscaCameraAdapter, SessionService ni Controller.  Solo bootstrap.

from __future__ import annotations

import logging

from core.app_context import AppContext
from core.state import SystemState
from core.events import AsyncEventBus
from application.preset_service import PresetService
from application.session_service import SessionService
from application.app_controller import ApplicationController
from application.call_set_command_policy import CallSetCommandPolicy
from application.runtime_state_store import RuntimeStateStore
from application.runtime_audit_log import RuntimeAuditLog
from core.controller import Controller
from adapters.visca_camera_adapter import ViscaCameraAdapter

logger = logging.getLogger(__name__)


def _ensure_runtime_dirs() -> None:
    """
    Create data and config directories if they do not yet exist.

    This is especially important in production (/var/lib/khptz/, /etc/khptz/)
    where the directories are not pre-created by the OS.  Runs silently on
    failure (e.g. permission denied in tests) so the app always starts.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        r = RuntimePathResolver()
        r.data_dir.mkdir(parents=True, exist_ok=True)
        r.config_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not create runtime dirs: %s", exc)


def _create_flight_recorder():
    """
    Create a production FlightRecorder writing to the runtime blackbox path.

    Returns None when running from source (dev/test) or on any import/IO error
    so that the app always starts even without a writable log directory.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        if resolver.running_from_source:
            return None
        from application.flight_recorder import FlightRecorder
        return FlightRecorder(events_file=resolver.blackbox_events_file)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FlightRecorder unavailable (blackbox log disabled): %s", exc)
        return None


def _create_layout_service():
    """
    Create a LayoutService pointing at the runtime room_layout.json.

    Always returns a LayoutService — never None.  If the runtime path is
    unavailable, falls back to a LayoutService seeded from SEAT_POSITIONS
    (same default the service uses internally when no file exists).
    The fallback layout is in-memory only; it will be persisted on the
    next successful write cycle.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        from application.layout_service import LayoutService
        resolver = RuntimePathResolver()
        svc = LayoutService(layout_path=resolver.room_layout_file)
        svc.load()
        return svc
    except Exception as exc:
        logger.exception(
            "LayoutService could not load from runtime path (%s); "
            "falling back to default layout from SEAT_POSITIONS", exc,
        )
    # Fallback: generate from legacy positions — safe even with no file I/O
    try:
        import pathlib
        import tempfile
        from application.layout_service import LayoutService
        from config import SEAT_POSITIONS
        tmp_path = pathlib.Path(tempfile.mkdtemp()) / "room_layout_fallback.json"
        svc = LayoutService(layout_path=tmp_path, legacy_positions=SEAT_POSITIONS)
        svc.load()
        return svc
    except Exception as exc2:
        logger.exception("LayoutService fallback also failed: %s — no layout available", exc2)
        return None


def _create_camera_target_resolver(layout_svc):
    """
    Create a CameraTargetResolver from the loaded layout and config.yaml cameras.

    Returns None when config.yaml is absent or on any error.
    """
    if layout_svc is None:
        return None
    try:
        from config.loader import load_config
        from config.registry import CameraRegistry
        from application.camera_target_resolver import CameraTargetResolver
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        settings = load_config(resolver.config_dir / "config.yaml")
        registry = CameraRegistry(settings.cameras)
        return CameraTargetResolver(layout_svc, registry)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CameraTargetResolver unavailable: %s", exc)
        return None


def _load_cam_configs() -> 'dict[int, tuple[str, str]] | None':
    """Load camera IPs and VISCA IDs from config.yaml.

    Returns a dict {1: (ip, visca_id), 2: (ip, visca_id), ...} on success,
    or None on any error so the caller can fall back to legacy .txt files.
    """
    try:
        from config.loader import load_config
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        settings = load_config(resolver.config_dir / "config.yaml")
        result = {}
        for i, cam in enumerate(settings.cameras, start=1):
            result[i] = (cam.ip, cam.visca_id)
        return result if result else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("_load_cam_configs failed, falling back to legacy .txt: %s", exc)
        return None


def build_app_context(cameras, flight_recorder=None) -> AppContext:
    """
    Construye y devuelve el AppContext completo para una sesión de la aplicación.

    Parameters
    ----------
    cameras:
        Instancia de CameraManager ya creada por MainWindow (la callback
        on_worker_ready pertenece a la UI y no puede moverse aquí todavía).
    flight_recorder:
        Optional FlightRecorder override. When None, a production recorder is
        created automatically via RuntimePathResolver (disabled in dev/source).
    """
    _ensure_runtime_dirs()

    if flight_recorder is None:
        flight_recorder = _create_flight_recorder()

    layout_svc = _create_layout_service()
    camera_target_resolver = _create_camera_target_resolver(layout_svc)

    state = SystemState()

    bus = AsyncEventBus()
    bus.start()

    cam_configs = _load_cam_configs()

    # Calcula los IDs de camara para inicializar RuntimeStateStore.
    _camera_ids: list[str] = []
    if cam_configs:
        _camera_ids = [f"cam{i}" for i in sorted(cam_configs.keys())]
    else:
        _camera_ids = ["cam1", "cam2"]

    # Fuente unica de verdad para el estado runtime (#787).
    runtime_store = RuntimeStateStore(camera_ids=_camera_ids)

    # Audit log conectado como suscriptor (#799).
    audit_log = RuntimeAuditLog()
    runtime_store.subscribe(audit_log.on_state_change)

    preset_svc   = PresetService()
    camera_port  = ViscaCameraAdapter(cameras, cam_configs=cam_configs)
    session_svc  = SessionService(
        camera_port,
        flight_recorder=flight_recorder,
        system_state=state,
        runtime_state_store=runtime_store,
    )

    controller = Controller(
        state=state,
        bus=bus,
        preset_svc=preset_svc,
        session_svc=session_svc,
        camera_port=camera_port,
    )

    app_ctrl = ApplicationController(
        session_svc=session_svc,
        call_set_policy=CallSetCommandPolicy(),
        bus=bus,
    )

    return AppContext(
        state=state,
        bus=bus,
        preset_svc=preset_svc,
        camera_port=camera_port,
        session_svc=session_svc,
        controller=controller,
        app_ctrl=app_ctrl,
        flight_recorder=flight_recorder,
        layout_svc=layout_svc,
        camera_target_resolver=camera_target_resolver,
        runtime_state_store=runtime_store,
        runtime_audit_log=audit_log,
    )
