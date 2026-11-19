# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts.check_secrets import _scan_content, _git_lines, _is_blocked_name


@pytest.mark.parametrize("directory", ["docs", "tests", "config/examples", "application"])
def test_no_directory_exempts_secret_content(tmp_path, directory):
    path = tmp_path / directory / "sample.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("-----" + "BEGIN RSA PRIVATE KEY-----\nsynthetic canary\n")
    findings = _scan_content(path, tmp_path)
    assert findings
    assert all("canary" not in f for f in findings)


@pytest.mark.parametrize("prefix,length", [("gh" + "p_", 36), ("github_" + "pat_", 70)])
def test_github_token_shapes_detected_without_reporting_value(tmp_path, prefix, length):
    path = tmp_path / "sample.txt"
    canary = prefix + "x" * length
    path.write_text(canary)
    assert _scan_content(path, tmp_path)
    assert all(canary not in f for f in _scan_content(path, tmp_path))


def test_read_failure_is_scan_failure_not_clean(tmp_path, monkeypatch):
    path = tmp_path / "sample.py"
    path.touch()
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=OSError("injected")))
    assert _scan_content(path, tmp_path) == ["unreadable file (scan incomplete)"]


def test_git_failure_not_empty_clean_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_secrets.subprocess.run",
                        Mock(return_value=Mock(returncode=128)))
    with pytest.raises(RuntimeError, match="enumerate"):
        _git_lines(tmp_path, "ls-files")


def test_secret_filename_in_docs_not_exempt(tmp_path):
    assert _is_blocked_name(tmp_path / "docs" / "password.enc", tmp_path)
