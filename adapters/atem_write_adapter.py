#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/atem_write_adapter.py — Production AtemWritePort using PyATEMMax
#
# ATEMWriteAdapter opens a dedicated TCP connection to the ATEM for manual
# commands (set_preview, CUT, AUTO, set_pip_enabled).  It is separate from
# ATEMMonitor's polling connection — ATEM switchers support multiple clients.
#
# Thread-safety:
#   connect() is designed to run in a daemon thread (_connect_async).
#   All other public methods (commands + reads) must be called from the
#   Qt main thread only.  The Lock serialises connect() against itself
#   (no concurrent connects) and protects _atem/_connected writes.
#   Main-thread reads of _connected are GIL-safe in CPython.
#
# Non-blocking design:
#   _require_connection() NEVER calls connect() — it returns None immediately
#   if not connected.  Commands fail fast with DISCONNECTED.  The caller
#   (e.g. _toggle_atem_panel) starts connect() in a daemon thread; the
#   panel's 1 s refresh shows "Disconnected" until the thread finishes.
#
# Safety contract — CUT / AUTO:
#   cut() and auto() MUST NOT be retried automatically.
#   Each call is a deliberate operator action.

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from domain.ports import AtemCommandResult, SwitcherStatus

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 3   # seconds — used by the daemon connect thread


class ATEMWriteAdapter:
    """Production AtemWritePort — dedicated PyATEMMax connection for manual commands.

    AtemDiagnosticsService and AtemCommandService both accept this adapter
    because it satisfies AtemWritePort (which extends AtemReadPort).

    Typical lifecycle::

        adapter = ATEMWriteAdapter(ip="192.168.1.240")
        adapter.connect_async()    # non-blocking; main thread stays responsive
        result = adapter.cut()     # fails fast with DISCONNECTED if not ready
        adapter.disconnect()       # call when panel closes
    """

    def __init__(self, ip: str) -> None:
        self._ip = ip.strip()
        self._atem = None          # PyATEMMax.ATEMMax instance when connected
        self._pyatemmax = None     # PyATEMMax module reference (cached after first import)
        self._connected = False
        self._connecting = False   # True while daemon connect thread is running
        self._last_error: str = ""
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────────

    @property
    def ip(self) -> str:
        """Current target IP."""
        with self._lock:
            return self._ip

    def set_ip(self, ip: str) -> None:
        """Point the adapter at a new ATEM IP, dropping any existing connection.

        Call from the Qt main thread. The next connect_async()/connect() targets
        the new IP. Needed because the adapter is created once at startup; when
        the operator edits the ATEM IP in Settings the old connection would
        otherwise keep failing against the previous address.
        """
        new_ip = ip.strip()
        with self._lock:
            if new_ip == self._ip and self._connected:
                return
        self.disconnect()
        with self._lock:
            self._ip = new_ip
            self._last_error = ""

    def connect_async(self) -> None:
        """Start a daemon thread to connect.  Returns immediately.

        Guards against spawning multiple concurrent connect threads.
        The panel's 1 s refresh loop will see _connected=True after success.
        """
        with self._lock:
            if self._connected or self._connecting:
                return
            self._connecting = True

        t = threading.Thread(target=self._connect_thread, daemon=True)
        t.start()

    def connect(self, timeout: int = _CONNECT_TIMEOUT) -> bool:
        """Blocking connect.  Returns True when connected.

        Safe to call from a background thread.  Uses _lock to prevent
        concurrent connect attempts.
        """
        with self._lock:
            if self._connected and self._atem is not None:
                return True
            if not self._ip:
                self._last_error = "ATEM IP not configured"
                logger.warning("[ATEM-write] %s", self._last_error)
                return False

        try:
            import PyATEMMax
        except ImportError:
            with self._lock:
                self._last_error = "PyATEMMax not installed"
            logger.warning("[ATEM-write] PyATEMMax not installed")
            return False

        atem = None
        try:
            atem = PyATEMMax.ATEMMax()
            atem.connect(self._ip)
            if not atem.waitForConnection(timeout=timeout):
                err = f"No response from {self._ip} (timeout={timeout}s)"
                logger.warning("[ATEM-write] %s", err)
                with self._lock:
                    self._last_error = err
                return False
            with self._lock:
                self._atem = atem
                self._pyatemmax = PyATEMMax   # cache for use in commands
                self._connected = True
                self._last_error = ""
            logger.info("[ATEM-write] Connected to %s", self._ip)
            return True
        except Exception as exc:
            logger.warning("[ATEM-write] connect error: %s", exc)
            with self._lock:
                self._last_error = str(exc)
            return False
        finally:
            # Close the local atem object only if the connection was not stored.
            with self._lock:
                stored = self._connected
            if not stored and atem is not None:
                self._safe_close(atem)

    def disconnect(self) -> None:
        """Close the PyATEMMax connection (call from Qt main thread)."""
        with self._lock:
            atem = self._atem
            self._atem = None
            self._connected = False
        if atem is not None:
            self._safe_close(atem)
        logger.info("[ATEM-write] Disconnected")

    # ── AtemReadPort ──────────────────────────────────────────────────────────

    def get_program_input(self) -> Optional[int]:
        atem = self._require_connection()
        if atem is None:
            return None
        try:
            return int(atem.programInput[0].videoSource)
        except Exception as exc:
            # Transient read error — do NOT disconnect; connection may be fine.
            logger.debug("[ATEM-write] get_program_input transient error: %s", exc)
            return None

    def get_preview_input(self) -> Optional[int]:
        atem = self._require_connection()
        if atem is None:
            return None
        try:
            return int(atem.previewInput[0].videoSource)
        except Exception as exc:
            logger.debug("[ATEM-write] get_preview_input transient error: %s", exc)
            return None

    def test_connection(self) -> AtemCommandResult:
        t0 = time.monotonic()
        atem = self._require_connection()
        if atem is None:
            return AtemCommandResult(
                ok=False,
                command="test_connection",
                error_code="DISCONNECTED",
                message=self._last_error,
            )
        try:
            _ = int(atem.programInput[0].videoSource)
            return AtemCommandResult.success(
                "test_connection",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self._mark_disconnected()
            return AtemCommandResult(
                ok=False,
                command="test_connection",
                error_code="ERROR",
                message=str(exc),
            )

    def get_status(self) -> SwitcherStatus:
        with self._lock:
            connected = self._connected and self._atem is not None
        program = self.get_program_input() if connected else None
        preview = self.get_preview_input() if connected else None
        return SwitcherStatus(
            adapter_type="atem",
            connected=connected,
            program_input=program,
            preview_input=preview,
            last_error=self._last_error,
        )

    # ── AtemWritePort ─────────────────────────────────────────────────────────

    def set_preview_input(self, input_id: int) -> AtemCommandResult:
        t0 = time.monotonic()
        atem = self._require_connection()
        if atem is None:
            return AtemCommandResult(
                ok=False, command="set_preview_input",
                error_code="DISCONNECTED", message=self._last_error,
                target=input_id,
            )
        try:
            PyATEMMax = self._pyatemmax
            atem.setPreviewInputVideoSource(0, PyATEMMax.ATEMVideoSources(input_id))
            logger.info("[ATEM-write] set_preview_input → %d", input_id)
            return AtemCommandResult.success(
                "set_preview_input", target=input_id,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except OSError as exc:
            self._mark_disconnected()
            logger.warning("[ATEM-write] set_preview_input network error: %s", exc)
            return AtemCommandResult(
                ok=False, command="set_preview_input",
                error_code="NETWORK_ERROR", message=str(exc),
                target=input_id,
            )
        except Exception as exc:
            logger.warning("[ATEM-write] set_preview_input unexpected error: %s", exc)
            return AtemCommandResult(
                ok=False, command="set_preview_input",
                error_code="ERROR", message=str(exc),
                target=input_id,
            )

    def cut(self) -> AtemCommandResult:
        """CUT transition. No automatic retry — deliberate operator action only."""
        t0 = time.monotonic()
        atem = self._require_connection()
        if atem is None:
            return AtemCommandResult(
                ok=False, command="cut",
                error_code="DISCONNECTED", message=self._last_error,
            )
        try:
            atem.execCutME(0)
            logger.info("[ATEM-write] CUT executed")
            return AtemCommandResult.success(
                "cut", duration_ms=(time.monotonic() - t0) * 1000,
            )
        except OSError as exc:
            self._mark_disconnected()
            logger.warning("[ATEM-write] cut network error: %s", exc)
            return AtemCommandResult(
                ok=False, command="cut",
                error_code="NETWORK_ERROR", message=str(exc),
            )
        except Exception as exc:
            logger.warning("[ATEM-write] cut unexpected error: %s", exc)
            return AtemCommandResult(
                ok=False, command="cut",
                error_code="ERROR", message=str(exc),
            )

    def auto(self) -> AtemCommandResult:
        """AUTO transition. No automatic retry — deliberate operator action only."""
        t0 = time.monotonic()
        atem = self._require_connection()
        if atem is None:
            return AtemCommandResult(
                ok=False, command="auto",
                error_code="DISCONNECTED", message=self._last_error,
            )
        try:
            atem.execAutoME(0)
            logger.info("[ATEM-write] AUTO executed")
            return AtemCommandResult.success(
                "auto", duration_ms=(time.monotonic() - t0) * 1000,
            )
        except OSError as exc:
            self._mark_disconnected()
            logger.warning("[ATEM-write] auto network error: %s", exc)
            return AtemCommandResult(
                ok=False, command="auto",
                error_code="NETWORK_ERROR", message=str(exc),
            )
        except Exception as exc:
            logger.warning("[ATEM-write] auto unexpected error: %s", exc)
            return AtemCommandResult(
                ok=False, command="auto",
                error_code="ERROR", message=str(exc),
            )

    def set_pip_enabled(self, enabled: bool) -> AtemCommandResult:
        """Enable or disable Picture-in-Picture on ME1. No automatic retry."""
        t0 = time.monotonic()
        atem = self._require_connection()
        if atem is None:
            return AtemCommandResult(
                ok=False, command="set_pip_enabled",
                error_code="DISCONNECTED", message=self._last_error,
            )
        try:
            # PyATEMMax PiP write API name varies by library version.
            if hasattr(atem, "setPIPEnabled"):
                atem.setPIPEnabled(0, enabled)
            elif hasattr(atem, "setPictureInPictureEnabled"):
                atem.setPictureInPictureEnabled(0, enabled)
            else:
                raise AttributeError(
                    "PyATEMMax: no PiP write method found"
                    " (tried setPIPEnabled, setPictureInPictureEnabled)"
                )
            logger.info("[ATEM-write] PiP %s", "ON" if enabled else "OFF")
            return AtemCommandResult.success(
                "set_pip_enabled",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except AttributeError as exc:
            # Missing PiP API in this PyATEMMax version — don't tear down connection.
            logger.warning("[ATEM-write] set_pip_enabled API not found: %s", exc)
            return AtemCommandResult(
                ok=False, command="set_pip_enabled",
                error_code="API_NOT_FOUND", message=str(exc),
            )
        except Exception as exc:
            self._mark_disconnected()
            logger.warning("[ATEM-write] set_pip_enabled error: %s", exc)
            return AtemCommandResult(
                ok=False, command="set_pip_enabled",
                error_code="ERROR", message=str(exc),
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _connect_thread(self) -> None:
        """Run by connect_async() daemon thread.  Clears _connecting on exit."""
        try:
            self.connect()
        finally:
            with self._lock:
                self._connecting = False

    def _require_connection(self):
        """Return the PyATEMMax instance if connected, else None.

        Never blocks or calls connect() — callers must use connect_async() first.
        """
        with self._lock:
            return self._atem if self._connected else None

    def _mark_disconnected(self) -> None:
        with self._lock:
            atem = self._atem
            self._atem = None
            self._connected = False
        if atem is not None:
            self._safe_close(atem)

    def _safe_close(self, atem) -> None:
        for method_name in ("disconnect", "close", "stop"):
            method = getattr(atem, method_name, None)
            if callable(method):
                try:
                    method()
                    return
                except Exception:
                    pass
