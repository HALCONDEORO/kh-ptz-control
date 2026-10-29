# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for PresetTestModels and PresetTestSummary counts."""
import pytest
from application.preset_test_models import (
    PresetTestItem,
    PresetTestResult,
    PresetTestSummary,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_SKIPPED,
    STATUS_WARNING,
    STATUS_CANCELLED,
)


def _item(label="1", preset=1, enabled=True, assigned_name=None, has_verified_ptz=None):
    return PresetTestItem(
        item_id=f"seat_{label}",
        label=label,
        camera_role="comments",
        camera_index=2,
        preset=preset,
        enabled=enabled,
        assigned_name=assigned_name,
        has_verified_ptz=has_verified_ptz,
    )


def test_item_frozen():
    item = _item()
    with pytest.raises(Exception):
        item.label = "x"  # type: ignore[misc]


def test_result_frozen():
    result = PresetTestResult(item=_item(), status=STATUS_OK, message="ok")
    with pytest.raises(Exception):
        result.status = STATUS_ERROR  # type: ignore[misc]


def test_summary_counts():
    items = [_item(str(i)) for i in range(6)]
    results = [
        PresetTestResult(item=items[0], status=STATUS_OK, message=""),
        PresetTestResult(item=items[1], status=STATUS_OK, message=""),
        PresetTestResult(item=items[2], status=STATUS_ERROR, message="timeout"),
        PresetTestResult(item=items[3], status=STATUS_SKIPPED, message="no preset"),
        PresetTestResult(item=items[4], status=STATUS_WARNING, message="slow"),
        PresetTestResult(item=items[5], status=STATUS_CANCELLED, message="user"),
    ]
    summary = PresetTestSummary(
        total=6, ok=2, warning=1, error=1, skipped=1, cancelled=False, results=results
    )
    assert summary.ok == 2
    assert summary.error == 1
    assert summary.warning == 1
    assert summary.skipped == 1
    assert summary.total == 6
    assert not summary.cancelled


def test_summary_cancelled_flag():
    summary = PresetTestSummary(
        total=0, ok=0, warning=0, error=0, skipped=0, cancelled=True
    )
    assert summary.cancelled


def test_item_assigned_name_default_none():
    item = _item()
    assert item.assigned_name is None


def test_item_assigned_name_preserved():
    item = _item(assigned_name="PersonA")
    assert item.assigned_name == "PersonA"


def test_item_has_verified_ptz_default_none():
    item = _item()
    assert item.has_verified_ptz is None


def test_item_has_verified_ptz_true():
    item = _item(has_verified_ptz=True)
    assert item.has_verified_ptz is True


def test_item_has_verified_ptz_false():
    item = _item(has_verified_ptz=False)
    assert item.has_verified_ptz is False
