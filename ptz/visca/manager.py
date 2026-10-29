#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ptz/visca/manager.py — Gestor centralizado de estado y workers de cámaras PTZ
#
# Responsabilidad única: encapsular todo el estado mutable de las cámaras
# y los workers de red. Nadie más guarda estado de cámara.
#
# MOTIVO: centralizar el estado mutable de cámaras (workers, zoom cache,
# backlight, focus, exposición) en un solo objeto en lugar de atributos
# sueltos en MainWindow.  ViscaCameraAdapter y los helpers de AE/zoom del
# adaptador leen y escriben este estado.

from __future__ import annotations

import threading
from typing import Callable, Optional

from config import CameraConfig
from .worker import CameraWorker


class CameraManager:
    """
    Gestión centralizada de cámaras PTZ.

    Encapsula:
      - Workers TCP persistentes (uno por cámara).
      - Cache de zoom para evitar queries de red innecesarias.
      - Estado per-cámara: backlight, focus y nivel de exposición.

    Índices de cámara: 1 = CAM1 (Platform), 2 = CAM2 (Comments).
    """

    def __init__(self, cam1: CameraConfig, cam2: CameraConfig,
                 on_worker_ready: Optional[Callable[['CameraWorker'], None]] = None):
        self._cam1_ip = cam1.ip
        self._cam2_ip = cam2.ip
        self._cam1_id = cam1.cam_id
        self._cam2_id = cam2.cam_id
        self._on_worker_ready = on_worker_ready

        # Workers creados bajo demanda: el thread TCP no arranca hasta el
        # primer acceso, evitando conexiones con IPs aún no validadas.
        # _workers_lock protege el check-and-create: worker() se invoca desde
        # varios hilos (Qt principal, monitor ATEM vía nudge, threads de query),
        # y sin lock dos llamadas concurrentes para la misma IP crearían dos
        # CameraWorker (y dos threads TCP) — TOCTOU.
        self._workers_lock: threading.Lock = threading.Lock()
        self._workers: dict[str, CameraWorker] = {}

        # Cache de zoom: None = sin valor local, necesita query de red.
        # Clave: cam_key (1 o 2). Valor: último porcentaje enviado a la cámara.
        self._zoom_cache: dict[int, Optional[int]] = {1: None, 2: None}

        # Flags de query en vuelo: evitan lanzar un segundo thread si ya hay uno
        # consultando zoom o AE de esa cámara (race condition tras preset recall).
        # _inflight_lock protege el check-and-set de ambos flags: sin lock, dos
        # threads pueden leer False simultáneamente y ambos proceder (TOCTOU).
        self._inflight_lock:      threading.Lock  = threading.Lock()
        self._zoom_query_inflight: dict[int, bool] = {1: False, 2: False}
        self._ae_query_inflight:   dict[int, bool] = {1: False, 2: False}

        # Estado por cámara. Clave: cam_key (1 o 2).
        self.backlight_on:   dict[int, bool] = {1: False, 2: False}
        self.focus_mode:     dict[int, str]  = {1: 'auto', 2: 'auto'}
        self.exposure_level: dict[int, int]  = {1: 0,      2: 0     }
        # 'auto' cubre Full Auto, Shutter Priority, Iris Priority.
        # 'manual' y 'bright' usan CAM_Bright (0D) en lugar de CAM_ExpComp (0E).
        self.ae_mode:        dict[int, str]  = {1: 'auto', 2: 'auto'}

    # ─────────────────────────────────────────────────────────────────────────
    #  Identificación de cámara
    # ─────────────────────────────────────────────────────────────────────────

    def cam_key(self, ip: str) -> int:
        """Devuelve 1 para CAM1 y 2 para CAM2. Lanza ValueError para IPs desconocidas."""
        if ip == self._cam1_ip:
            return 1
        if ip == self._cam2_ip:
            return 2
        raise ValueError(f"Unknown camera IP: {ip!r}")

    # ─────────────────────────────────────────────────────────────────────────
    #  Workers
    # ─────────────────────────────────────────────────────────────────────────

    def stop_all(self) -> None:
        """Detiene todos los workers TCP. Llamar desde closeEvent."""
        # Snapshot bajo lock; stop() (que hace join) se ejecuta fuera del lock
        # para no bloquear worker() durante el cierre.
        with self._workers_lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()

    def update_camera_ip(self, cam_key: int, new_ip: str) -> None:
        """Update the IP for camera cam_key (1 or 2) and retire the old TCP worker."""
        with self._workers_lock:
            old_ip = self._cam1_ip if cam_key == 1 else self._cam2_ip
            if cam_key == 1:
                self._cam1_ip = new_ip
            else:
                self._cam2_ip = new_ip
            old_worker = self._workers.pop(old_ip, None)
        if old_worker is not None:
            old_worker.stop()
        # Eagerly create the worker for the new IP so it connects (and wires its
        # status signals via on_worker_ready) right away, instead of waiting for
        # the next camera command. Without this the connection LED stayed red
        # until the operator happened to trigger a camera action.
        if new_ip:
            self.worker(new_ip)

    def reconnect_all(self) -> None:
        """Cierra los sockets activos; los workers reconectan solos en el próximo heartbeat."""
        with self._workers_lock:
            workers = list(self._workers.values())
        for w in workers:
            w._close_socket()

    def worker(self, ip: str) -> CameraWorker:
        """
        Devuelve el CameraWorker para la IP dada, creándolo si aún no existe.
        El thread TCP se inicia aquí, no en __init__, para diferir la conexión
        hasta que se sabe que la IP es válida y necesaria.

        Thread-safe: el check-and-create se hace bajo _workers_lock para que
        accesos concurrentes a la misma IP no creen workers duplicados.
        """
        with self._workers_lock:
            w = self._workers.get(ip)
            created = w is None
            if created:
                w = CameraWorker(ip)
                self._workers[ip] = w
        # on_worker_ready fuera del lock: conecta señales Qt y no debe
        # ejecutarse con el lock tomado (evita reentrancia / bloqueos).
        if created and self._on_worker_ready:
            self._on_worker_ready(w)
        return w

    def is_connected(self, ip: str) -> bool:
        """True si hay worker para esa IP y está conectado. NO crea workers."""
        if not ip:
            return False
        with self._workers_lock:
            w = self._workers.get(ip)
        return bool(w is not None and w.is_connected)

    def worker_by_key(self, key: int) -> CameraWorker:
        """Devuelve el worker por clave entera (1 o 2) sin necesidad de la IP global."""
        ip = self._cam1_ip if key == 1 else self._cam2_ip
        return self.worker(ip)

    def ip_for_key(self, key: int) -> str:
        """Devuelve la IP configurada para la clave de cámara 1 o 2."""
        return self._cam1_ip if key == 1 else self._cam2_ip

    def cam_id_for_key(self, key: int) -> str:
        """Devuelve el VISCA ID (p.ej. '81') configurado para la clave de cámara 1 o 2."""
        return self._cam1_id if key == 1 else self._cam2_id

    # ─────────────────────────────────────────────────────────────────────────
    #  Zoom cache
    # ─────────────────────────────────────────────────────────────────────────

    def get_zoom(self, ip: str) -> Optional[int]:
        """Último porcentaje de zoom enviado a esta cámara, o None si no hay cache."""
        return self._zoom_cache.get(self.cam_key(ip))

    def set_zoom(self, ip: str, pct: int):
        """Actualiza el cache con el porcentaje de zoom enviado."""
        self._zoom_cache[self.cam_key(ip)] = pct

    def invalidate_zoom(self, ip: str):
        """
        Borra el cache de zoom para esta cámara.
        Usar tras un preset recall: los presets mueven el zoom a una
        posición desconocida, así el slider se sincronizará con la red.
        """
        self._zoom_cache[self.cam_key(ip)] = None

    def zoom_query_try_acquire(self, ip: str) -> bool:
        """
        Intenta reservar el slot de query de zoom para esta cámara.
        Devuelve True (y marca inflight) si no había query en vuelo.
        Devuelve False si ya hay uno activo: el llamador debe descartarse.
        Operación atómica mediante _inflight_lock para evitar TOCTOU.
        """
        with self._inflight_lock:
            key = self.cam_key(ip)
            if self._zoom_query_inflight[key]:
                return False
            self._zoom_query_inflight[key] = True
            return True

    def zoom_query_release(self, ip: str):
        """Libera el slot de query de zoom tras completarse el thread."""
        with self._inflight_lock:
            self._zoom_query_inflight[self.cam_key(ip)] = False

    def ae_query_try_acquire(self, ip: str) -> bool:
        """
        Intenta reservar el slot de query de AE para esta cámara.
        Devuelve True (y marca inflight) si no había query en vuelo.
        Devuelve False si ya hay uno activo: el llamador debe descartarse.
        Operación atómica mediante _inflight_lock para evitar TOCTOU.
        """
        with self._inflight_lock:
            key = self.cam_key(ip)
            if self._ae_query_inflight[key]:
                return False
            self._ae_query_inflight[key] = True
            return True

    def ae_query_release(self, ip: str):
        """Libera el slot de query de AE tras completarse el thread."""
        with self._inflight_lock:
            self._ae_query_inflight[self.cam_key(ip)] = False
