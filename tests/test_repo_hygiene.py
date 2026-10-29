# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from pathlib import Path

from scripts import check_repo_hygiene


def test_blocks_root_runtime_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "password.enc"
    artifact.write_text("secret", encoding="utf-8")

    assert check_repo_hygiene._is_blocked(artifact, tmp_path)


def test_blocks_secret_key_suffix(tmp_path: Path) -> None:
    artifact = tmp_path / "nested" / "support-key.pem"
    artifact.parent.mkdir()
    artifact.write_text("secret", encoding="utf-8")

    assert check_repo_hygiene._is_blocked(artifact, tmp_path)


def test_blocks_customer_config_directory(tmp_path: Path) -> None:
    artifact = tmp_path / "customer_config" / "site.yaml"
    artifact.parent.mkdir()
    artifact.write_text("site: real", encoding="utf-8")

    assert check_repo_hygiene._is_blocked(artifact, tmp_path)


def test_allows_safe_example_config(tmp_path: Path) -> None:
    artifact = tmp_path / "config.example" / "starter.yaml"
    artifact.parent.mkdir()
    artifact.write_text("site: Example", encoding="utf-8")

    assert not check_repo_hygiene._is_blocked(artifact, tmp_path)


def test_allows_docs_examples(tmp_path: Path) -> None:
    artifact = tmp_path / "docs" / "examples" / "sample_config.yaml"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("site: Example", encoding="utf-8")

    assert not check_repo_hygiene._is_blocked(artifact, tmp_path)
