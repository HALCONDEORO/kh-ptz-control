#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ptz/visca/worker.py — Worker de envío de comandos VISCA
#
# Responsabilidad única: mantener una conexión TCP persistente con una cámara
# y despachar comandos desde una cola en un thread dedicado.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - FIX DEADLOCK: recv() ya no se ejecuta dentro de self._lock.
#     Antes: `with self._lock: sock.send(raw); sock.recv(1024)`
#     Si la cámara no respondía, el lock quedaba bloqueado indefinidamente.
#     Ahora: se copia la referencia del socket con el lock, se libera,
#     y se hace send/recv sin tenerlo. Si el socket se cierra entre medias
#     (por _close_socket desde otro hilo), la excepción se captura normalmente.
#
#   - FIX PYTHON 3.9: `socket.socket | None` es sintaxis 3.10+.
#     Aunque `from __future__ import annotations` la acepta como string en
#     anotaciones, usar Optional[socket.socket] es explícito y compatible
#     con cualquier herramienta de análisis estático sobre Python 3.9.
#
#   - CLARIDAD: se separa la adquisición del socket de su uso en _run(),
#     haciendo el flujo más fácil de leer y de auditar.

from __future__ import annotations  # type hints modernos sin romper Python 3.9 en runtime

import logging
import queue
import select
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional  # reemplaza `socket.socket | None` (sintaxis 3.10+)

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Command ID generator
# ─────────────────────────────────────────────────────────────────────────────
# Each command gets a short unique ID: cmd_{YYYYMMDD}_{counter:05d}
# Used to correlate queued → sent → completed/error log lines in support logs.

_cmd_id_lock    = threading.Lock()
_cmd_id_counter = 0


def _next_cmd_id() -> str:
    """Returns a short unique command ID: ``cmd_YYYYMMDD_NNNNN``."""
    global _cmd_id_counter
    with _cmd_id_lock:
        _cmd_id_counter = (_cmd_id_counter + 1) % 100_000
        counter = _cmd_id_counter
    date_str = time.strftime("%Y%m%d")
    return f"cmd_{date_str}_{counter:05d}"


from config import (
    VISCA_PORT, CAMERA_QUEUE_MAXSIZE, HEARTBEAT_TIMEOUT,
    CAMERA_CONNECT_TIMEOUT, VISCA_READ_TIMEOUT, VISCA_SLOW_CMD_MS,
)
from domain.camera_state import CameraConnectionState
from domain.retry_policy import RetryPolicy, CAMERA_RETRY_POLICY

# STOP y comandos confirmados no gastan el presupuesto largo de reconexión
# (backoffs 5/15/30 s): tres intentos inmediatos sin esperas entre ellos.
_PRIORITY_RETRY_POLICY = RetryPolicy(backoffs=(0, 0))
from .parser import contains_completion, contains_final_response


@dataclass
class ViscaCommand:
    """
    Representa un comando VISCA listo para ejecutar.

    camera:     1 = CAM1 (Platform), 2 = CAM2 (Comments).
    payload:    bytes completos del frame VISCA.
    priority:   si True, vacía la cola antes de encolar. Solo para STOP.
    coalesce:   si True, reemplaza el último comando pendiente del mismo tipo
                (move / zoom_drive). Usar en comandos de alta frecuencia
                (joystick, zoom slider) para no acumular comandos obsoletos.
    queued_at:  timestamp monotónico al encolar. Usado para calcular
                queue_wait_ms en el log de latencia.
    cmd_id:     unique command ID (cmd_YYYYMMDD_NNNNN) assigned at dispatch time.
                Used to correlate queued → sent → completed/error log lines.
    on_success / on_failure: callbacks desde el thread del worker.
    """
    camera:     int
    payload:    bytes
    priority:   bool                          = False
    coalesce:   bool                          = False
    fast_connect: bool                        = False  # conexión inmediata sin backoffs largos
    queued_at:  float                         = 0.0    # asignado por send() / send_priority()
    cmd_id:     str                           = field(default_factory=_next_cmd_id)
    on_success: Optional[Callable[[], None]] = None
    on_failure: Optional[Callable[[], None]] = None


class CameraWorkerSignals(QObject):
    """Señales Qt para CameraWorker (QObject requerido para pyqtSignal)."""
    connection_changed       = pyqtSignal(bool)    # True = conectado, False = desconectado
    connection_state_changed = pyqtSignal(object)  # CameraConnectionState — estado detallado
    visca_error              = pyqtSignal(str, str) # (ip, cmd_type): 'move'|'zoom_drive'|'other'


class CameraWorker:
    """
    Gestiona la conexión TCP con una cámara VISCA y despacha comandos
    de forma asíncrona desde una cola interna.

    DISEÑO:
    - Un único thread de fondo consume la cola y envía comandos.
    - Si el socket falla, intenta reconectar una vez antes de descartar
      el comando, evitando bloquear la UI indefinidamente.
    - La cola tiene un límite de 20 comandos para evitar acumulación
      si la cámara no responde (p.ej. apagada). Los comandos más nuevos
      se descartan cuando la cola está llena.
    """

    def __init__(self, ip: str, port: int = VISCA_PORT):
        self.ip   = ip
        self.port = port

        self.signals = CameraWorkerSignals()  # señales Qt para la UI
        self._is_connected = False                                  # derivado de _connection_state
        self._connection_state = CameraConnectionState.UNKNOWN      # estado explícito (#97)

        # Cola con límite: put_nowait() lanza queue.Full si está llena
        self._queue: queue.Queue = queue.Queue(maxsize=CAMERA_QUEUE_MAXSIZE)

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()  # protege self._sock entre hilos

        # _interrupt: lo pone send_priority() para que _read_visca_response()
        # aborte la espera sin llegar al timeout completo (fix #181). Se
        # limpia cuando el worker empieza a procesar el propio comando de
        # prioridad (ver _run), así que NO sirve como señal de apagado.
        self._interrupt = threading.Event()

        # _shutdown: lo pone stop() y nunca se limpia. A diferencia de
        # _interrupt, procesar un comando de prioridad no lo toca, así que
        # una reconexión en curso siempre lo ve y aborta (fix: un stop()
        # concurrente con un comando de prioridad dejaba el hilo vivo hasta
        # 54s tras un join(timeout=3.0) fallido, filtrando threads en tests).
        self._shutdown = threading.Event()

        self._last_heartbeat: float = time.monotonic()

        # Thread daemon: muere cuando el proceso principal termina.
        # No hace falta llamar a stop() explícitamente al cerrar la app.
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"CamWorker-{ip}")
        self._thread.start()

    def send(self, cmd: ViscaCommand) -> bool:
        """
        Encola un ViscaCommand para ejecución asíncrona.
        Devuelve True si se encoló, False si la cola estaba llena.

        Si cmd.coalesce=True, reemplaza el último comando pendiente del mismo
        tipo en la cola (move / zoom_drive), evitando acumular comandos de
        joystick obsoletos. La búsqueda es O(n) pero la cola es de 20 items.
        """
        cmd.queued_at = time.monotonic()
        if cmd.coalesce:
            cmd_type = CameraWorker._classify_payload(cmd.payload)
            with self._queue.mutex:
                dq = self._queue.queue
                for i in range(len(dq) - 1, -1, -1):
                    c = dq[i]
                    if c is not None and c.coalesce and CameraWorker._classify_payload(c.payload) == cmd_type:
                        dq[i] = cmd
                        logger.debug("%s cam=%s type=%s queued (coalesced)",
                                     cmd.cmd_id, self.ip, cmd_type)
                        return True
        try:
            self._queue.put_nowait(cmd)
            logger.debug("%s cam=%s type=%s queued",
                         cmd.cmd_id, self.ip,
                         CameraWorker._classify_payload(cmd.payload))
            return True
        except queue.Full:
            logger.warning("CameraWorker %s: cola llena, descartado: %s",
                           self.ip, cmd.payload.hex())
            return False

    def send_priority(self, cmd: ViscaCommand):
        """
        Vacía la cola de comandos pendientes y coloca cmd en primer lugar.

        También activa _interrupt para que _read_visca_response() aborte
        cualquier espera en vuelo, reduciendo la latencia del STOP al mínimo.
        """
        cmd.queued_at = time.monotonic()
        cmd.priority = True
        # Señalizar el interrupt ANTES de drenar para que el worker no lea
        # el siguiente comando entre el drain y el put.
        self._interrupt.set()
        incoming_is_stop = CameraWorker._is_stop_payload(cmd.payload)
        # Drenar → conservar → admitir es UNA operación atómica bajo el mutex
        # de la cola: ningún productor concurrente puede intercalarse entre
        # el drain y el requeue (los kept no pueden caer en queue.Full) ni
        # colarse delante del STOP.
        with self._queue.not_full:
            q = self._queue.queue
            # Drain: solo sobreviven los STOPs priority ya encolados (las
            # mitades pan/tilt y zoom de STOPs anteriores). Todo lo demás —
            # movimientos coalesced, HOMEs, presets — está obsoleto en cuanto
            # llega un comando priority nuevo.
            # Un STOP idéntico ya encolado es redundante (idempotente): el
            # nuevo lo sustituye, no se acumulan duplicados.
            kept = []
            for c in q:
                if c is None:
                    # Sentinel de stop(): la petición de apagado del worker
                    # sobrevive siempre al drain.
                    kept.append(c)
                elif (c.priority
                      and CameraWorker._is_stop_payload(c.payload)
                      and c.payload != cmd.payload):
                    kept.append(c)
            q.clear()
            q.extend(kept)
            if self._queue.maxsize > 0:
                while len(q) >= self._queue.maxsize:
                    if not incoming_is_stop:
                        # Un priority NO-STOP (p.ej. HOME) jamás desplaza
                        # STOPs pendientes: si no cabe, se descarta él mismo.
                        logger.warning(
                            "%s cam=%s priority command dropped: "
                            "queue full of pending STOPs",
                            cmd.cmd_id, self.ip,
                        )
                        return
                    # STOP contra STOP: se descarta el STOP más viejo —
                    # NUNCA el sentinel de apagado ni el propio entrante.
                    idx = next((i for i, c in enumerate(q) if c is not None), None)
                    if idx is None:
                        logger.warning(
                            "%s cam=%s STOP dropped: shutdown in progress",
                            cmd.cmd_id, self.ip,
                        )
                        return
                    del q[idx]
            q.append(cmd)
            self._queue.not_empty.notify()
        logger.debug("%s cam=%s type=%s queued (priority)",
                     cmd.cmd_id, self.ip,
                     CameraWorker._classify_payload(cmd.payload))

    def heartbeat_age(self) -> float:
        """Segundos transcurridos desde la última iteración del bucle; útil para diagnóstico."""
        return time.monotonic() - self._last_heartbeat

    def _requeue(self, cmd: ViscaCommand) -> None:
        """
        Devuelve un STOP interrumpido a la cola, detrás del STOP más nuevo que
        lo interrumpió. Solo para comandos priority: ambas mitades del STOP
        (pan/tilt y zoom) deben salir aunque se interrumpan entre sí.
        """
        try:
            self._queue.put_nowait(cmd)
            logger.info("%s cam=%s STOP reencolado tras interrupción", cmd.cmd_id, self.ip)
        except queue.Full:
            # Tras el drain de send_priority la cola solo puede llevar el
            # sentinel y las dos mitades de STOP: lleno aquí es inesperado.
            logger.error("%s cam=%s STOP perdido: cola llena al reencolar", cmd.cmd_id, self.ip)

    def send_confirmed(self, cmd: ViscaCommand, timeout: float) -> bool:
        """
        Encola `cmd` y bloquea al llamante hasta Completion, Error o timeout.

        Los comandos confirmados (preset recall/save, power, focus, zoom
        absoluto...) pasan por la MISMA sesión TCP del worker: no se abre una
        segunda conexión a la cámara (hay modelos de una sola sesión que
        tirarían la del worker) y la confirmación se lee donde se envió.
        Un STOP que lo interrumpa lo completa con fallo inmediato.
        """
        done = threading.Event()
        box: dict = {}
        cmd.on_success = lambda: (box.__setitem__("ok", True), done.set())
        cmd.on_failure = lambda: (box.__setitem__("ok", False), done.set())
        cmd.fast_connect = True
        if not self.send(cmd):
            logger.warning("%s cam=%s send_confirmed: cola llena", cmd.cmd_id, self.ip)
            return False
        if not done.wait(timeout):
            logger.warning("%s cam=%s send_confirmed: timeout %.1fs", cmd.cmd_id, self.ip, timeout)
            return False
        return box.get("ok", False)

    def stop(self) -> None:
        """
        Detiene el worker de forma limpia: interrumpe la lectura en vuelo,
        cierra el socket y espera a que el thread termine.
        Idempotente: no hace nada si el thread ya está muerto.
        """
        if not self._thread.is_alive():
            return
        self._shutdown.set()
        self._interrupt.set()
        self._close_socket()
        try:
            self._queue.put_nowait(None)  # sentinel: desbloquea _queue.get()
        except queue.Full:
            pass
        self._thread.join(timeout=3.0)

    def restart(self) -> None:
        """
        Relanza el thread del worker si ha muerto inesperadamente.
        El objeto CameraWorker reutiliza la misma instancia, por lo que
        las conexiones de señales Qt permanecen intactas.
        """
        if self._thread.is_alive():
            return
        # Relanzar implica seguir operando, no honrar un stop() previo: ambas
        # señales deben limpiarse, o el hilo nuevo descartaría todo comando
        # no prioritario (_interrupt) y toda reconexión (_shutdown) de inmediato.
        self._shutdown.clear()
        self._interrupt.clear()
        self._close_socket()
        self._last_heartbeat = time.monotonic()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"CamWorker-{self.ip}")
        self._thread.start()
        logger.info("CameraWorker %s: thread relanzado por el supervisor", self.ip)

    def _set_state(self, state: CameraConnectionState) -> None:
        """Actualiza el estado de conexión y emite señales si cambian."""
        connected = state in (CameraConnectionState.CONNECTED, CameraConnectionState.SIMULATED)
        prev_state     = getattr(self, '_connection_state', CameraConnectionState.UNKNOWN)
        prev_connected = self._is_connected

        self._connection_state = state
        self._is_connected     = connected

        if state != prev_state:
            self.signals.connection_state_changed.emit(state)
        if connected != prev_connected:
            self.signals.connection_changed.emit(connected)

    @property
    def is_connected(self) -> bool:
        """True si la sesión TCP con la cámara está activa (solo lectura)."""
        return self._is_connected

    def _set_connected(self, connected: bool) -> None:
        """Wrapper bool para compatibilidad; delega en _set_state."""
        self._set_state(
            CameraConnectionState.CONNECTED if connected
            else CameraConnectionState.DISCONNECTED
        )

    def _ping(self):
        """Heartbeat periódico: verifica/restaura la conexión cuando la cola está inactiva."""
        with self._lock:
            sock_ref = self._sock

        if sock_ref is not None and self._socket_alive(sock_ref):
            self._set_connected(True)
            return

        # Socket muerto o inexistente: reconectar SIN tener el lock.
        # _connect_with_retry() puede bloquear varios segundos; mantener el
        # lock durante ese tiempo causaría deadlock si restart() llega desde
        # la UI.  Los reintentos son interrumpibles vía _interrupt.
        self._close_socket()
        new_sock = self._connect_with_retry()
        with self._lock:
            self._sock = new_sock
        self._set_connected(new_sock is not None)

    @staticmethod
    def _socket_alive(sock: socket.socket) -> bool:
        """
        Comprueba si un socket TCP sigue activo sin enviar datos de aplicación.

        Usa select() con timeout cero para ver si el descriptor tiene datos
        listos para leer. En TCP, readable sin haber enviado nada significa
        que el par envió EOF (FIN) o RST, es decir, la conexión está cerrada.
        Si no hay nada legible el socket se considera vivo: select() confirma
        que el descriptor local es válido y no hay FIN pendiente de leer.
        No se usa send(b"") porque su comportamiento varía entre OS y algunos
        firmwares de cámara lo rechazan con EINVAL o RST inesperado.
        """
        try:
            readable, _, _ = select.select([sock], [], [], 0)
            if readable:
                # Hay datos listos sin haber enviado comando: en VISCA
                # (req/resp) significa EOF del par (FIN/RST) o basura.
                # MSG_PEEK comprueba sin consumir el byte del stream.
                data = sock.recv(1, socket.MSG_PEEK)
                return len(data) > 0
            return True
        except (OSError, socket.error, TypeError, ValueError):
            return False

    def _connect(self) -> Optional[socket.socket]:
        """
        Intenta abrir una conexión TCP nueva con la cámara.
        Devuelve el socket si tiene éxito, None si falla.

        CAMBIADO: anotación de retorno usa Optional[socket.socket]
        MOTIVO: `socket.socket | None` requiere Python 3.10+; esta forma
        es equivalente y compatible con Python 3.9 en producción (RPi).

        IMPORTANTE: si connect() lanza excepción, el socket se cierra
        explícitamente para evitar file descriptor leak.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(CAMERA_CONNECT_TIMEOUT)
            s.connect((self.ip, self.port))
            logger.info("CameraWorker: conectado a %s:%s", self.ip, self.port)
            self._set_connected(True)
            return s
        except (socket.timeout, socket.error, OSError) as exc:
            # [WARN] y no [ERROR]: fallo de conexión en arranque es esperado
            # si las cámaras aún no están encendidas o alcanzables en desarrollo.
            logger.warning("CameraWorker: no se pudo conectar a %s: %s", self.ip, exc)
            s.close()  # Cierre explícito: evita leak de file descriptors
            self._set_connected(False)
            return None

    def _wait_interruptible(self, seconds: float) -> bool:
        """Espera hasta `seconds` comprobando la señal de interrupción cada 0.2 s.

        Devuelve True si el worker fue interrumpido antes de que terminara la espera.
        Permite que stop() / send_priority() aborte un backoff de reconexión sin
        tener que esperar el timeout completo.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._interrupt.is_set() or self._shutdown.is_set():
                return True
            time.sleep(0.2)
        return False

    def _connect_with_retry(
        self,
        policy: RetryPolicy = CAMERA_RETRY_POLICY,
    ) -> Optional[socket.socket]:
        """
        Intenta conectar con reintentos acotados según *policy*.

        Prueba hasta ``policy.max_attempts`` veces, esperando los segundos de
        *policy.backoffs* entre intentos.  Cada espera es interrumpible: si
        ``_interrupt`` está activo (por stop() o send_priority()) la función
        retorna None inmediatamente sin hacer más intentos.

        Devuelve el socket si algún intento tiene éxito, None en caso contrario.
        """
        max_att = policy.max_attempts
        for attempt in range(1, max_att + 1):
            if self._interrupt.is_set() or self._shutdown.is_set():
                return None
            self._set_state(CameraConnectionState.CONNECTING)
            sock = self._connect()
            if sock is not None:
                return sock
            if attempt == max_att:
                logger.warning(
                    "CameraWorker %s: sin conexión tras %d intento(s) — se reintentará en heartbeat",
                    self.ip, max_att,
                )
                return None
            backoff = policy.backoffs[attempt - 1]
            logger.info(
                "CameraWorker %s: reintentando en %ds (intento %d/%d)",
                self.ip, backoff, attempt, max_att,
            )
            if self._wait_interruptible(backoff):
                return None
        return None  # reached only when max_attempts == 0

    def _close_socket(self):
        """Cierra el socket actual de forma segura, ignorando errores."""
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self._set_connected(False)

    # Cuerpos VISCA de STOP (sin cam_id ni 0xFF final): pan/tilt stop y zoom
    # stop. Son idempotentes: repetirlos nunca mueve la cámara.
    _STOP_PT_BODY = bytes.fromhex("01060100000303")
    _STOP_ZOOM_BODY = bytes.fromhex("01040700")

    @staticmethod
    def _is_stop_payload(payload: bytes) -> bool:
        """True si el frame VISCA es un STOP de movimiento (pan/tilt o zoom),
        con cualquier cam_id en el primer byte."""
        if len(payload) < 2 or payload[-1] != 0xFF:
            return False
        body = payload[1:-1]
        return body in (CameraWorker._STOP_PT_BODY, CameraWorker._STOP_ZOOM_BODY)

    @staticmethod
    def _classify_payload(payload: bytes) -> str:
        """Clasifica un payload VISCA por tipo de comando para el watchdog de velocidad."""
        body = payload[1:4]  # slice seguro: nunca lanza IndexError
        if body == b'\x01\x06\x01':
            return 'move'
        if body == b'\x01\x04\x07':
            return 'zoom_drive'
        return 'other'

    # Aliases de módulo para mantener la interfaz interna sin cambiar los call-sites.
    # La lógica canónica vive en ptz.visca.parser — CameraWorker no la duplica.
    _has_final_visca_frame = staticmethod(contains_final_response)
    _has_completion_frame  = staticmethod(contains_completion)

    def _read_visca_response(self, sock: socket.socket) -> bytes:
        """
        Lee la respuesta completa de la cámara (Completion o Error).

        Usa rodajas de select() de 50 ms para comprobar _interrupt entre
        esperas: si send_priority() activa el interrupt, este método aborta
        sin esperar el timeout completo (fix #181).
        """
        buf = b''
        deadline = time.monotonic() + VISCA_READ_TIMEOUT
        while True:
            if self._interrupt.is_set() or self._shutdown.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([sock], [], [], min(remaining, 0.05))
            if not readable:
                continue   # rodaja de 50 ms agotada; vuelve a comprobar interrupt y deadline
            chunk = sock.recv(1024)
            if not chunk:
                break
            buf += chunk
            if CameraWorker._has_final_visca_frame(buf):
                break
        return buf

    def _run(self):
        """
        Bucle principal del worker (corre en thread de fondo).

        FIX DEADLOCK:
        Antes, send() y recv() se ejecutaban dentro de `with self._lock`.
        Si recv() bloqueaba (cámara sin respuesta), el lock quedaba tomado
        indefinidamente, impidiendo que _close_socket() pudiera ejecutarse.

        Ahora el flujo es:
          1. Adquirir lock → copiar referencia del socket → liberar lock.
          2. Hacer send/recv SIN el lock.
          3. Si falla → _close_socket() puede adquirir el lock normalmente.

        Si el socket se cierra entre step 1 y step 2 (por _close_socket
        llamado desde otro contexto), la excepción de send/recv se captura
        y el worker reintenta reconectando.
        """
        while True:
            self._last_heartbeat = time.monotonic()
            # Espera hasta HEARTBEAT_TIMEOUT s; si no hay comando, ejecuta heartbeat y vuelve a esperar
            try:
                cmd = self._queue.get(timeout=HEARTBEAT_TIMEOUT)
            except queue.Empty:
                self._ping()
                continue

            if cmd is None:  # sentinel puesto por stop()
                break

            # Intentar hasta 2 veces: 1ª con socket existente, 2ª tras reconectar
            _succeeded  = False
            _interrupted = self._interrupt.is_set() and not cmd.priority
            send_started_at = 0.0

            if _interrupted:
                continue

            if cmd.priority and not self._shutdown.is_set():
                # El STOP ya llegó a la cabeza de la cola; ahora sí se puede
                # limpiar la señal para que el propio STOP espere su respuesta.
                # Si stop() ya pidió apagado, NO se limpia: de lo contrario
                # una reconexión sin _interrupt activo ignoraría el apagado
                # y podría tardar hasta el backoff completo de la policy en
                # terminar, dejando el hilo vivo mucho más allá del
                # join(timeout=3.0) de stop() (bug: filtraba threads en tests).
                self._interrupt.clear()

            for attempt in range(2):

                # --- Fase 1: obtener referencia del socket (con lock breve) ---
                with self._lock:
                    sock_ref = self._sock

                if sock_ref is None:
                    # Un STOP (priority) o un confirmado no gastan el
                    # presupuesto largo de reconexión: intentos inmediatos.
                    policy = _PRIORITY_RETRY_POLICY if (cmd.priority or cmd.fast_connect) else CAMERA_RETRY_POLICY
                    sock_ref = self._connect_with_retry(policy=policy)
                    with self._lock:
                        self._sock = sock_ref

                if sock_ref is None:
                    # Sin conexión. Un STOP interrumpido por otro STOP más
                    # nuevo NO se pierde: vuelve a la cola y sale después de él.
                    if cmd.priority and self._interrupt.is_set():
                        _interrupted = True
                        self._requeue(cmd)
                    break  # Sin conexión: descartar comando

                # Recheck justo antes de enviar: si llegó un comando priority
                # más nuevo durante la (re)conexión, este comando está obsoleto
                # (un MOVE jamás se envía cuando ya hay STOP pedido) o, si es
                # un STOP, sale DESPUÉS del más nuevo (reencolado, no perdido).
                if self._interrupt.is_set():
                    _interrupted = True
                    if cmd.priority:
                        self._requeue(cmd)
                    elif cmd.on_failure is not None:
                        try:
                            cmd.on_failure()
                        except Exception as exc:
                            logger.exception("CameraWorker %s: on_failure raised: %s", self.ip, exc)
                    break

                # --- Fase 2: enviar y leer respuesta SIN el lock ---
                try:
                    send_started_at = time.monotonic()
                    logger.debug("%s cam=%s sent", cmd.cmd_id, self.ip)
                    sock_ref.sendall(cmd.payload)
                    response = self._read_visca_response(sock_ref)

                    # Si send_priority() interrumpió la lectura: un STOP no se
                    # pierde — se reencola tras el más nuevo; un comando normal
                    # queda obsoleto y un confirmado falla hacia su llamante.
                    if self._interrupt.is_set():
                        _interrupted = True
                        if cmd.priority:
                            self._requeue(cmd)
                        elif cmd.on_failure is not None:
                            try:
                                cmd.on_failure()
                            except Exception as exc:
                                logger.exception("CameraWorker %s: on_failure raised: %s", self.ip, exc)
                        self._close_socket()
                        break

                    self._set_connected(True)
                    cmd_type = CameraWorker._classify_payload(cmd.payload)

                    if not CameraWorker._has_final_visca_frame(response):
                        # Timeout, socket EOF o respuesta vacía/ACK-only: no hay
                        # confirmación de la cámara → tratar como fallo.
                        logger.warning(
                            "%s cam=%s no final VISCA frame for [%s] "
                            "(%d bytes: %s)",
                            cmd.cmd_id, self.ip, cmd_type, len(response),
                            response.hex() if response else "empty",
                        )
                        # La cámara puede completar DESPUÉS del timeout; esa
                        # trama tardía quedaría en el buffer y el siguiente
                        # comando la leería como suya (confirmaciones falsas y
                        # drift permanente). Cerrar el socket fuerza una
                        # reconexión con buffer limpio en el próximo comando.
                        self._close_socket()
                        break  # _succeeded permanece False

                    if not CameraWorker._has_completion_frame(response):
                        # Trama final recibida pero es Error, no Completion.
                        self.signals.visca_error.emit(self.ip, cmd_type)
                        logger.warning(
                            "%s cam=%s VISCA error response [%s] %s",
                            cmd.cmd_id, self.ip, cmd_type, response.hex(),
                        )
                        break  # _succeeded permanece False

                    _succeeded = True
                    break

                except (socket.timeout, socket.error, OSError) as exc:
                    logger.warning("CameraWorker %s intento %d: %s", self.ip, attempt + 1, exc)
                    self._close_socket()

            # ── Latency log (#180) + completion ID (#160) ────────────────────
            if send_started_at and not _interrupted:
                now = time.monotonic()
                queue_wait_ms = round((send_started_at - cmd.queued_at) * 1000)
                send_ms       = round((now - send_started_at) * 1000)
                total_ms      = queue_wait_ms + send_ms
                cmd_type      = CameraWorker._classify_payload(cmd.payload)
                if _succeeded:
                    logger.debug("%s cam=%s completed in %dms", cmd.cmd_id, self.ip, send_ms)
                if total_ms >= VISCA_SLOW_CMD_MS:
                    logger.warning(
                        "[VISCA latency] %s cam=%s type=%s queue_wait=%dms send=%dms total=%dms ok=%s",
                        cmd.cmd_id, self.ip, cmd_type, queue_wait_ms, send_ms, total_ms, _succeeded,
                    )
                else:
                    logger.debug(
                        "[VISCA latency] %s cam=%s type=%s queue_wait=%dms send=%dms total=%dms ok=%s",
                        cmd.cmd_id, self.ip, cmd_type, queue_wait_ms, send_ms, total_ms, _succeeded,
                    )

            if _succeeded:
                if cmd.on_success:
                    try:
                        cmd.on_success()
                    except Exception as exc:
                        logger.exception("CameraWorker %s: on_success raised: %s", self.ip, exc)
            elif not _interrupted:
                if cmd.on_failure:
                    try:
                        cmd.on_failure()
                    except Exception as exc:
                        logger.exception("CameraWorker %s: on_failure raised: %s", self.ip, exc)
