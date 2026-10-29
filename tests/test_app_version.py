# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

from app_version import APP_NAME, app_version_label, read_version


def test_read_version_from_file(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")

    assert read_version(version_file) == "1.2.3"


def test_read_version_unknown_when_missing(tmp_path):
    assert read_version(tmp_path / "MISSING") == "unknown"


def test_read_version_unknown_when_empty(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("\n", encoding="utf-8")

    assert read_version(version_file) == "unknown"


def test_app_version_label_uses_app_name(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("2.0.0", encoding="utf-8")

    assert app_version_label(version_file) == f"{APP_NAME} 2.0.0"
