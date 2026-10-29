# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for preset_sources — build_items_from_config and build_items_from_assigned_names."""
from unittest.mock import patch

from application.preset_sources import build_items_from_assigned_names
from application.preset_test_models import PresetTestItem
from application.preset_verification_service import PresetVerificationService
from domain.preset_verification import VerificationStatus


# ── build_items_from_config ────────────────────────────────────────────────

def test_build_items_from_config_returns_items():
    from application.preset_sources import build_items_from_config
    items = build_items_from_config()
    assert isinstance(items, list)
    assert all(isinstance(i, PresetTestItem) for i in items)


def test_build_items_from_config_sorted():
    from application.preset_sources import build_items_from_config
    items = build_items_from_config()
    presets = [i.preset for i in items if i.preset is not None]
    assert presets == sorted(presets)


# ── helpers ────────────────────────────────────────────────────────────────

def _run_named(seats: dict, preset_map: dict) -> list[PresetTestItem]:
    """Run build_items_from_assigned_names with patched config."""
    with patch("config.load_names_data", return_value={"names": [], "seats": seats}):
        with patch("config.PRESET_MAP", preset_map):
            return build_items_from_assigned_names()


# ── build_items_from_assigned_names ───────────────────────────────────────

def test_named_empty_seats_returns_empty():
    assert _run_named({}, {}) == []


def test_named_skips_empty_strings():
    items = _run_named({"4": "", "5": "   ", "6": "PersonA"}, {4: "0x04", 6: "0x06"})
    assert len(items) == 1
    assert items[0].assigned_name == "PersonA"
    assert items[0].label == "6"


def test_named_strips_whitespace():
    items = _run_named({"4": "  PersonB  "}, {4: "0x04"})
    assert items[0].assigned_name == "PersonB"


def test_named_invalid_key_skipped():
    items = _run_named({"abc": "PersonA", "4": "PersonB"}, {4: "0x04"})
    assert len(items) == 1
    assert items[0].assigned_name == "PersonB"


def test_named_sorted_by_seat_number():
    items = _run_named(
        {"10": "PersonC", "4": "PersonA", "7": "PersonB"},
        {4: "0x04", 7: "0x07", 10: "0x10"},
    )
    assert [i.label for i in items] == ["4", "7", "10"]


def test_named_missing_preset_map_entry_is_disabled():
    items = _run_named({"4": "PersonA", "5": "PersonB"}, {4: "0x04"})
    seat4 = next(i for i in items if i.label == "4")
    seat5 = next(i for i in items if i.label == "5")
    assert seat4.enabled is True
    assert seat5.enabled is False
    assert seat5.preset is None


def test_named_camera_routing():
    items = _run_named({"1": "Main", "4": "Comments"}, {1: "0x01", 4: "0x04"})
    main_item = next(i for i in items if i.label == "1")
    comments_item = next(i for i in items if i.label == "4")
    assert main_item.camera_role == "main"
    assert main_item.camera_index == 1
    assert comments_item.camera_role == "comments"
    assert comments_item.camera_index == 2


def test_named_assigned_name_in_item():
    items = _run_named({"4": "Mary Smith"}, {4: "0x04"})
    assert items[0].assigned_name == "Mary Smith"


# ── has_verified_ptz population ───────────────────────────────────────────────


def _mark_ok(svc: PresetVerificationService, seat_id: str, camera_role: str, preset: int):
    svc.mark(seat_id, camera_role, preset, VerificationStatus.OK)


# build_items_from_config


def test_config_source_no_verification_data_gives_none(tmp_path):
    from application.preset_sources import build_items_from_config
    items = build_items_from_config(verifications_path=tmp_path / "v.json")
    assert all(i.has_verified_ptz is None for i in items)


def test_config_source_verified_ok_gives_true(tmp_path):
    from application.preset_sources import build_items_from_config
    from config import SEAT_POSITIONS
    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    seat_numbers = sorted(SEAT_POSITIONS)
    target = seat_numbers[0]
    camera_role = "main" if target <= 3 else "comments"
    _mark_ok(svc, f"seat_{target:03d}", camera_role, target)

    items = build_items_from_config(verifications_path=vpath)
    target_item = next(i for i in items if i.preset == target)
    assert target_item.has_verified_ptz is True


def test_config_source_unverified_seat_gives_none_when_other_is_verified(tmp_path):
    from application.preset_sources import build_items_from_config
    from config import SEAT_POSITIONS
    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    seat_numbers = sorted(SEAT_POSITIONS)
    target = seat_numbers[0]
    camera_role = "main" if target <= 3 else "comments"
    _mark_ok(svc, f"seat_{target:03d}", camera_role, target)

    items = build_items_from_config(verifications_path=vpath)
    unverified = [i for i in items if i.preset != target]
    assert all(i.has_verified_ptz is None for i in unverified)


def test_config_source_failed_verification_gives_false(tmp_path):
    from application.preset_sources import build_items_from_config
    from config import SEAT_POSITIONS
    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    seat_numbers = sorted(SEAT_POSITIONS)
    target = seat_numbers[0]
    camera_role = "main" if target <= 3 else "comments"
    svc.mark(f"seat_{target:03d}", camera_role, target, VerificationStatus.FAILED)

    items = build_items_from_config(verifications_path=vpath)
    target_item = next(i for i in items if i.preset == target)
    assert target_item.has_verified_ptz is False


# build_items_from_assigned_names


def _run_named_with_verifications(seats, preset_map, vpath):
    with patch("config.load_names_data", return_value={"names": [], "seats": seats}):
        with patch("config.PRESET_MAP", preset_map):
            return build_items_from_assigned_names(verifications_path=vpath)


def test_named_source_no_verification_gives_none(tmp_path):
    items = _run_named_with_verifications({"4": "PersonA"}, {4: "0x04"}, tmp_path / "v.json")
    assert items[0].has_verified_ptz is None


def test_named_source_verified_ok_gives_true(tmp_path):
    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    _mark_ok(svc, "seat_004", "comments", 4)
    items = _run_named_with_verifications({"4": "PersonA"}, {4: "0x04"}, vpath)
    assert items[0].has_verified_ptz is True


def test_named_source_failed_verification_gives_false(tmp_path):
    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    svc.mark("seat_004", "comments", 4, VerificationStatus.FAILED)
    items = _run_named_with_verifications({"4": "PersonA"}, {4: "0x04"}, vpath)
    assert items[0].has_verified_ptz is False


# End-to-end: source → runner → STATUS_OK


def test_verified_item_produces_status_ok_in_runner(tmp_path):
    """Full path: verified record → has_verified_ptz=True → runner → STATUS_OK."""
    import threading
    from application.preset_test_runner import PresetTestRunner
    from application.preset_test_models import STATUS_OK

    vpath = tmp_path / "v.json"
    svc = PresetVerificationService(vpath)
    _mark_ok(svc, "seat_004", "comments", 4)

    items = _run_named_with_verifications({"4": "PersonA"}, {4: "0x04"}, vpath)
    assert items[0].has_verified_ptz is True

    done = threading.Event()
    results = []

    def on_result(r):
        results.append(r)

    def on_finished(s):
        done.set()

    runner = PresetTestRunner(
        items,
        send_fn=lambda ip, cam_id, preset_hex: True,
        resolve_fn=lambda preset: ("127.0.0.1", "82"),
    )
    runner.on_item_result = on_result
    runner.on_finished = on_finished
    runner.start()
    done.wait(timeout=3.0)

    assert len(results) == 1
    assert results[0].status == STATUS_OK


def test_unverified_item_produces_status_warning_in_runner(tmp_path):
    """No verification record → has_verified_ptz=None → STATUS_WARNING."""
    import threading
    from application.preset_test_runner import PresetTestRunner
    from application.preset_test_models import STATUS_WARNING

    items = _run_named_with_verifications(
        {"4": "PersonA"}, {4: "0x04"}, tmp_path / "v.json"
    )
    assert items[0].has_verified_ptz is None

    done = threading.Event()
    results = []

    def on_result(r):
        results.append(r)

    def on_finished(s):
        done.set()

    runner = PresetTestRunner(
        items,
        send_fn=lambda ip, cam_id, preset_hex: True,
        resolve_fn=lambda preset: ("127.0.0.1", "82"),
    )
    runner.on_item_result = on_result
    runner.on_finished = on_finished
    runner.start()
    done.wait(timeout=3.0)

    assert len(results) == 1
    assert results[0].status == STATUS_WARNING
