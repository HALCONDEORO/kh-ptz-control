# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for VISCA response validation (ptz.visca.parser.validate_visca_response)."""
from __future__ import annotations

from ptz.visca.parser import contains_final_response, validate_visca_response


# ── contains_final_response ───────────────────────────────────────────────────

class TestContainsFinalResponse:
    def test_empty_buffer_is_not_final(self):
        assert contains_final_response(b"") is False

    def test_ack_only_is_not_final(self):
        # ACK (9x 4y FF) must NOT count as terminal — Completion/Error follows.
        assert contains_final_response(bytes([0x90, 0x41, 0xFF])) is False

    def test_completion_is_final(self):
        assert contains_final_response(bytes([0x90, 0x51, 0xFF])) is True

    def test_error_is_final(self):
        assert contains_final_response(bytes([0x90, 0x60, 0x02, 0xFF])) is True

    def test_ack_then_completion_is_final(self):
        assert contains_final_response(bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])) is True

    def test_ack_then_error_is_final(self):
        assert contains_final_response(bytes([0x90, 0x41, 0xFF, 0x90, 0x61, 0x04, 0xFF])) is True

    def test_partial_completion_without_terminator_is_not_final(self):
        # Completion byte present but FF not yet received → keep reading.
        assert contains_final_response(bytes([0x90, 0x51])) is False

    def test_worker_alias_matches_direct_call(self):
        # CameraWorker._has_final_visca_frame must be the same function as
        # contains_final_response (no diverging duplicates).
        from ptz.visca.worker import CameraWorker
        data_ack  = bytes([0x90, 0x41, 0xFF])
        data_comp = bytes([0x90, 0x51, 0xFF])
        for buf in (data_ack, data_comp):
            assert CameraWorker._has_final_visca_frame(buf) == contains_final_response(buf)


# ── contains_completion ───────────────────────────────────────────────────────

class TestContainsCompletion:
    def test_completion_frame_returns_true(self):
        from ptz.visca.parser import contains_completion
        assert contains_completion(bytes([0x90, 0x51, 0xFF])) is True

    def test_error_frame_returns_false(self):
        from ptz.visca.parser import contains_completion
        assert contains_completion(bytes([0x90, 0x61, 0x04, 0xFF])) is False

    def test_ack_only_returns_false(self):
        from ptz.visca.parser import contains_completion
        assert contains_completion(bytes([0x90, 0x41, 0xFF])) is False

    def test_ack_then_completion_returns_true(self):
        from ptz.visca.parser import contains_completion
        assert contains_completion(bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])) is True

    def test_worker_alias_matches_direct_call(self):
        from ptz.visca.parser import contains_completion
        from ptz.visca.worker import CameraWorker
        for buf in (bytes([0x90, 0x51, 0xFF]), bytes([0x90, 0x61, 0x04, 0xFF])):
            assert CameraWorker._has_completion_frame(buf) == contains_completion(buf)


# ── validate_visca_response ───────────────────────────────────────────────────

class TestValidateViscaResponse:

    # Empty / EOF
    def test_empty_response_is_rejected(self):
        ok, reason = validate_visca_response(b"")
        assert not ok
        assert "empty" in reason.lower()

    # Completion frames
    def test_ack_only_is_not_success(self):
        # ACK (9x 4y FF) means the camera accepted the command but it has not
        # completed yet. With _recv_visca_response looping until a terminal
        # frame, receiving ACK-only means the camera never sent Completion/Error
        # (timeout or premature EOF). That must be a failure, not success.
        ok, reason = validate_visca_response(bytes([0x90, 0x41, 0xFF]))
        assert not ok
        assert "ack" in reason.lower()

    def test_completion_only_is_accepted(self):
        # Completion: 90 51 FF
        ok, _ = validate_visca_response(bytes([0x90, 0x51, 0xFF]))
        assert ok

    def test_ack_plus_completion_is_accepted(self):
        # Typical camera reply: ACK then Completion in one buffer
        response = bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])
        ok, _ = validate_visca_response(response)
        assert ok

    def test_ack_with_different_socket_numbers_is_not_success(self):
        # ACK uses socket 0-7 (byte 0x40-0x47). In all cases ACK-only is not
        # success — the camera accepted but has not confirmed completion.
        for socket_num in range(8):
            ack = bytes([0x90, 0x40 | socket_num, 0xFF])
            ok, _ = validate_visca_response(ack)
            assert not ok, f"ACK-only with socket {socket_num} must not be success"

    def test_completion_with_different_socket_accepted(self):
        for socket_num in range(8):
            comp = bytes([0x90, 0x50 | socket_num, 0xFF])
            ok, _ = validate_visca_response(comp)
            assert ok, f"Completion with socket {socket_num} should be accepted"

    # Error frames
    def test_error_frame_is_rejected(self):
        # Error: 90 60 02 FF (syntax error)
        ok, reason = validate_visca_response(bytes([0x90, 0x60, 0x02, 0xFF]))
        assert not ok
        assert "error" in reason.lower()

    def test_error_frame_41_is_rejected(self):
        # VISCA error code 0x41 = command not executable
        ok, reason = validate_visca_response(bytes([0x90, 0x61, 0x41, 0xFF]))
        assert not ok

    def test_ack_followed_by_error_is_rejected(self):
        # Camera sends ACK then Error (command cancelled)
        response = bytes([0x90, 0x41, 0xFF, 0x90, 0x61, 0x04, 0xFF])
        ok, reason = validate_visca_response(response)
        assert not ok
        assert "error" in reason.lower()

    def test_error_frame_reports_type_and_code(self):
        ok, reason = validate_visca_response(bytes([0x90, 0x60, 0x02, 0xFF]))
        assert "0x60" in reason
        assert "0x02" in reason

    # No valid frames
    def test_no_valid_frame_in_response_is_rejected(self):
        # Random garbage that doesn't contain ACK or Completion
        ok, reason = validate_visca_response(bytes([0xAA, 0xBB, 0xCC]))
        assert not ok

    def test_only_ff_bytes_is_rejected(self):
        ok, _ = validate_visca_response(bytes([0xFF, 0xFF, 0xFF]))
        assert not ok

