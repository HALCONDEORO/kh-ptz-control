#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_writer.py — patch_config_yaml unit tests

from __future__ import annotations

import pytest
import yaml

from config.writer import patch_config_yaml


_MINIMAL_YAML = """\
site:
  name: Test Site
cameras:
- id: platform
  role: platform
  ip: 192.168.1.10
  visca_id: '81'
- id: comments
  role: comments
  ip: 192.168.1.11
  visca_id: '82'
atem:
  ip: 192.168.1.200
"""


def _write(tmp_path, content=_MINIMAL_YAML):
    p = tmp_path / "config.yaml"
    p.write_text(content, encoding="utf-8")
    return p


# ── Camera IP ────────────────────────────────────────────────────────────────

def test_patch_cam1_ip(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=0, cam_ip="10.0.0.5")
    raw = yaml.safe_load(p.read_text())
    assert raw["cameras"][0]["ip"] == "10.0.0.5"
    assert raw["cameras"][1]["ip"] == "192.168.1.11"  # unchanged


def test_patch_cam2_ip(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=1, cam_ip="10.0.0.6")
    raw = yaml.safe_load(p.read_text())
    assert raw["cameras"][1]["ip"] == "10.0.0.6"
    assert raw["cameras"][0]["ip"] == "192.168.1.10"  # unchanged


# ── Camera VISCA ID ──────────────────────────────────────────────────────────

def test_patch_cam1_visca_id(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=0, cam_visca_id="83")
    raw = yaml.safe_load(p.read_text())
    assert raw["cameras"][0]["visca_id"] == "83"
    assert raw["cameras"][1]["visca_id"] == "82"  # unchanged


def test_patch_cam_ip_and_visca_id_together(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=0, cam_ip="10.0.1.1", cam_visca_id="84")
    raw = yaml.safe_load(p.read_text())
    assert raw["cameras"][0]["ip"] == "10.0.1.1"
    assert raw["cameras"][0]["visca_id"] == "84"


# ── ATEM IP ──────────────────────────────────────────────────────────────────

def test_patch_atem_ip(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, atem_ip="10.0.0.99")
    raw = yaml.safe_load(p.read_text())
    assert raw["atem"]["ip"] == "10.0.0.99"
    assert raw["cameras"][0]["ip"] == "192.168.1.10"  # unchanged


def test_patch_atem_ip_creates_atem_section_if_missing(tmp_path):
    content = """\
cameras:
- id: platform
  role: platform
  ip: 192.168.1.10
  visca_id: '81'
"""
    p = _write(tmp_path, content)
    patch_config_yaml(p, atem_ip="10.0.0.50")
    raw = yaml.safe_load(p.read_text())
    assert raw["atem"]["ip"] == "10.0.0.50"


# ── Preservation of unrelated sections ───────────────────────────────────────

def test_patch_preserves_site_section(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=0, cam_ip="10.0.0.5")
    raw = yaml.safe_load(p.read_text())
    assert raw["site"]["name"] == "Test Site"


def test_patch_preserves_second_camera_when_patching_first(tmp_path):
    p = _write(tmp_path)
    patch_config_yaml(p, cam_index=0, cam_ip="10.0.0.5")
    raw = yaml.safe_load(p.read_text())
    assert raw["cameras"][1]["id"] == "comments"
    assert raw["cameras"][1]["ip"] == "192.168.1.11"


# ── Error cases ───────────────────────────────────────────────────────────────

def test_patch_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        patch_config_yaml(tmp_path / "missing.yaml", cam_index=0, cam_ip="1.2.3.4")


def test_patch_raises_index_error_for_out_of_range_camera(tmp_path):
    p = _write(tmp_path)
    with pytest.raises(IndexError):
        patch_config_yaml(p, cam_index=5, cam_ip="1.2.3.4")


def test_patch_raises_value_error_without_cam_index(tmp_path):
    p = _write(tmp_path)
    with pytest.raises(ValueError):
        patch_config_yaml(p, cam_ip="1.2.3.4")


def test_patch_noop_when_no_kwargs_given(tmp_path):
    p = _write(tmp_path)
    original = p.read_text()
    patch_config_yaml(p)
    # File is rewritten but content is semantically identical
    raw = yaml.safe_load(p.read_text())
    original_raw = yaml.safe_load(original)
    assert raw == original_raw
