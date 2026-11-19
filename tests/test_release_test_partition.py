# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from pathlib import Path
from scripts.run_release_tests import partition


def test_full_partition_covers_nested_tests_once(tmp_path):
    names = ["test_json_io.py", "test_main_window_smoke.py", "test_config_pages_camera.py",
             "ux_focused/test_controller_launchers.py", "nested/test_other.py"]
    for name in names:
        p = tmp_path / "tests" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    forked, plain = partition(tmp_path, full=True)
    assert len(forked + plain) == len(names)
    assert len(set(forked + plain)) == len(names)
    assert {p.name for p in plain} == {"test_main_window_smoke.py", "test_config_pages_camera.py"}


def test_focused_includes_persistence_and_restore_not_hardware(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ["test_persistence_cut.py", "test_restore_schema.py", "test_main_startup.py",
                 "test_hardware_real.py"]:
        (tests / name).touch()
    forked, plain = partition(tmp_path)
    assert {p.name for p in forked + plain} == {
        "test_persistence_cut.py", "test_restore_schema.py", "test_main_startup.py"}


def test_manual_gate_retained_and_no_monolithic_pytest():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/release-check.yml").read_text()
    assert "python scripts/run_release_tests.py --full" in workflow
    assert "check_release_readiness.py" in workflow
    assert "NOT_TESTED never counts as pass" in workflow
