#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.

from __future__ import annotations


from application.inquiry_policy import (
    INQUIRY_TIMEOUT_S,
    POLLING_INTERVAL_S,
    InquiryPriority,
)


# ── InquiryPriority ordering ──────────────────────────────────────────────────

def test_emergency_stop_has_highest_priority():
    assert InquiryPriority.EMERGENCY_STOP == min(InquiryPriority)


def test_diagnostics_has_lowest_priority():
    assert InquiryPriority.DIAGNOSTICS == max(InquiryPriority)


def test_status_inquiry_lower_than_preset():
    assert InquiryPriority.STATUS_INQUIRY > InquiryPriority.PRESET


def test_movement_lower_than_stop():
    assert InquiryPriority.MOVEMENT > InquiryPriority.EMERGENCY_STOP


def test_session_safety_lower_than_preset():
    assert InquiryPriority.SESSION_SAFETY > InquiryPriority.PRESET


def test_inquiry_timeout_positive():
    assert INQUIRY_TIMEOUT_S > 0


def test_polling_interval_positive():
    assert POLLING_INTERVAL_S > 0


# ── CameraManager inflight guards ─────────────────────────────────────────────

def _make_manager():
    from config import CameraConfig
    from ptz.visca.manager import CameraManager
    cam1 = CameraConfig(ip="127.0.0.1", cam_id="81")
    cam2 = CameraConfig(ip="127.0.0.2", cam_id="82")
    return CameraManager(cam1, cam2)


def test_zoom_query_try_acquire_returns_true_when_free():
    mgr = _make_manager()
    assert mgr.zoom_query_try_acquire("127.0.0.1") is True


def test_zoom_query_try_acquire_returns_false_when_inflight():
    mgr = _make_manager()
    mgr.zoom_query_try_acquire("127.0.0.1")
    assert mgr.zoom_query_try_acquire("127.0.0.1") is False


def test_zoom_query_release_allows_reacquire():
    mgr = _make_manager()
    mgr.zoom_query_try_acquire("127.0.0.1")
    mgr.zoom_query_release("127.0.0.1")
    assert mgr.zoom_query_try_acquire("127.0.0.1") is True


def test_ae_query_try_acquire_returns_true_when_free():
    mgr = _make_manager()
    assert mgr.ae_query_try_acquire("127.0.0.1") is True


def test_ae_query_try_acquire_returns_false_when_inflight():
    mgr = _make_manager()
    mgr.ae_query_try_acquire("127.0.0.1")
    assert mgr.ae_query_try_acquire("127.0.0.1") is False


def test_ae_query_release_allows_reacquire():
    mgr = _make_manager()
    mgr.ae_query_try_acquire("127.0.0.1")
    mgr.ae_query_release("127.0.0.1")
    assert mgr.ae_query_try_acquire("127.0.0.1") is True


def test_two_cameras_have_independent_inquiry_slots():
    mgr = _make_manager()
    mgr.zoom_query_try_acquire("127.0.0.1")
    assert mgr.zoom_query_try_acquire("127.0.0.2") is True


# ── cancel_polls on session end ───────────────────────────────────────────────

def test_cancel_polls_called_on_session_end():
    from adapters.fake_camera_port import FakeCameraPort
    from application.session_service import SessionService

    port = FakeCameraPort()
    svc = SessionService(port, camera_ids=["cam1", "cam2"])
    svc.end()

    assert "cancel_polls:cam1" in port.calls
    assert "cancel_polls:cam2" in port.calls


# ── send_priority drains queue ────────────────────────────────────────────────

def test_stop_priority_bypasses_queued_inquiry():
    from ptz.visca.worker import CameraWorker, ViscaCommand

    worker = CameraWorker.__new__(CameraWorker)

    import queue
    import threading

    worker.ip = "127.0.0.1"
    worker.port = 5678
    worker._queue = queue.Queue(maxsize=20)
    worker._sock = None
    worker._lock = threading.Lock()
    worker._interrupt = threading.Event()
    worker._shutdown = threading.Event()
    worker._is_connected = False

    from domain.camera_state import CameraConnectionState
    worker._connection_state = CameraConnectionState.UNKNOWN

    dummy_payload = bytes.fromhex("8101060100000303FF")
    for _ in range(3):
        worker._queue.put_nowait(ViscaCommand(camera=1, payload=dummy_payload))

    stop_payload = bytes.fromhex("8101060100000303FF")
    worker.send_priority(ViscaCommand(camera=1, payload=stop_payload))

    assert worker._queue.qsize() == 1
