# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/demo_reset_service.py (#303)."""
from __future__ import annotations

import json
from pathlib import Path


from application.demo_reset_service import (
    DemoResetService,
    _PRODUCTION_PATH,
)


def _svc(tmp_path: Path, templates_dir: Path = None) -> DemoResetService:
    return DemoResetService(demo_data_dir=tmp_path / "demo", templates_dir=templates_dir)


def _make_templates(tmp_path: Path) -> Path:
    d = tmp_path / "templates"
    d.mkdir()
    for name in ("room_layout.json", "seat_names.json", "chairman_presets.json"):
        (d / name).write_text(json.dumps({"demo": True, "file": name}), encoding="utf-8")
    return d


# ── Safety checks ─────────────────────────────────────────────────────────────

class TestDemoResetSafety:
    def test_refuses_production_path(self):
        svc = DemoResetService(demo_data_dir=_PRODUCTION_PATH)
        result = svc.reset()
        assert not result.success
        assert "production" in result.error.lower()

    def test_refuses_child_of_production_path(self):
        svc = DemoResetService(demo_data_dir=_PRODUCTION_PATH / "subdir")
        result = svc.reset()
        assert not result.success
        assert "production" in result.error.lower()

    def test_refuses_khptz_data_dir_override(self, tmp_path, monkeypatch):
        """When KHPTZ_DATA_DIR is set, that path is also treated as production (#600)."""
        override = tmp_path / "legacy_prod"
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(override))
        svc = DemoResetService(demo_data_dir=override)
        result = svc.reset()
        assert not result.success
        assert "production" in result.error.lower()

    def test_allows_active_demo_dir_when_production_dirs_are_explicit(self, tmp_path, monkeypatch):
        templates = _make_templates(tmp_path)
        demo_dir = tmp_path / "demo"
        prod_dir = tmp_path / "prod"
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(demo_dir))
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(demo_dir))

        svc = DemoResetService(
            demo_data_dir=demo_dir,
            templates_dir=templates,
            production_data_dirs=[prod_dir],
        )
        result = svc.reset()

        assert result.success
        assert "room_layout.json" in result.restored

    def test_non_production_path_allowed(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = DemoResetService(demo_data_dir=tmp_path / "demo", templates_dir=templates)
        result = svc.reset()
        assert result.success

    def test_result_contains_reset_path(self, tmp_path):
        templates = _make_templates(tmp_path)
        demo_dir = tmp_path / "demo"
        svc = DemoResetService(demo_data_dir=demo_dir, templates_dir=templates)
        result = svc.reset()
        assert result.reset_path == demo_dir


# ── Reset behaviour ───────────────────────────────────────────────────────────

class TestDemoResetBehaviour:
    def test_creates_demo_dir(self, tmp_path):
        templates = _make_templates(tmp_path)
        demo_dir = tmp_path / "demo"
        assert not demo_dir.exists()
        svc = DemoResetService(demo_data_dir=demo_dir, templates_dir=templates)
        svc.reset()
        assert demo_dir.exists()

    def test_restores_all_template_files(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        result = svc.reset()
        assert set(result.restored) == {
            "room_layout.json", "seat_names.json", "chairman_presets.json"
        }

    def test_file_content_matches_template(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        svc.reset()
        demo_dir = tmp_path / "demo"
        data = json.loads((demo_dir / "room_layout.json").read_text(encoding="utf-8"))
        assert data["demo"] is True
        assert data["file"] == "room_layout.json"

    def test_overwrites_existing_data(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        demo_dir = tmp_path / "demo"
        demo_dir.mkdir()
        (demo_dir / "seat_names.json").write_text('{"names": ["real person"]}', encoding="utf-8")
        svc.reset()
        data = json.loads((demo_dir / "seat_names.json").read_text(encoding="utf-8"))
        assert "real person" not in str(data)

    def test_missing_template_file_is_skipped(self, tmp_path):
        templates = _make_templates(tmp_path)
        (templates / "chairman_presets.json").unlink()
        svc = _svc(tmp_path, templates)
        result = svc.reset()
        assert "chairman_presets.json" in result.skipped
        assert result.success

    def test_empty_templates_dir_returns_all_skipped(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        svc = DemoResetService(demo_data_dir=tmp_path / "demo", templates_dir=empty)
        result = svc.reset()
        assert result.success
        assert len(result.skipped) == 3
        assert len(result.restored) == 0

    def test_summary_includes_restored_and_skipped(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        result = svc.reset()
        summary = result.summary()
        assert "Restored" in summary

    def test_reset_success_property(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        result = svc.reset()
        assert result.success is True

    def test_reset_idempotent(self, tmp_path):
        templates = _make_templates(tmp_path)
        svc = _svc(tmp_path, templates)
        svc.reset()
        result = svc.reset()
        assert result.success
        assert len(result.restored) == 3


# ── Bundled demo templates exist ──────────────────────────────────────────────

class TestBundledDemoTemplates:
    def test_room_layout_template_exists(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        f = _DEMO_TEMPLATES_DIR / "room_layout.json"
        assert f.exists(), f"Bundled demo template missing: {f}"

    def test_seat_names_template_exists(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        f = _DEMO_TEMPLATES_DIR / "seat_names.json"
        assert f.exists(), f"Bundled demo template missing: {f}"

    def test_chairman_presets_template_exists(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        f = _DEMO_TEMPLATES_DIR / "chairman_presets.json"
        assert f.exists(), f"Bundled demo template missing: {f}"

    def test_room_layout_is_valid_json(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        content = (_DEMO_TEMPLATES_DIR / "room_layout.json").read_text(encoding="utf-8")
        data = json.loads(content)
        assert "seats" in data
        assert data.get("schema_version") == 1

    def test_seat_names_is_valid_json(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        content = (_DEMO_TEMPLATES_DIR / "seat_names.json").read_text(encoding="utf-8")
        data = json.loads(content)
        assert "names" in data

    def test_demo_layout_contains_no_real_ips(self):
        from application.demo_reset_service import _DEMO_TEMPLATES_DIR
        for f in _DEMO_TEMPLATES_DIR.glob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert "192.168." not in content, f"{f.name} contains production IP-like address"
            assert "10.0." not in content, f"{f.name} contains production IP-like address"

