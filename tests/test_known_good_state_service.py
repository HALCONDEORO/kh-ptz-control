#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_known_good_state_service.py — Tests for KnownGoodStateService and StateDiffService (#564).

Covers:
- KnownGoodSnapshot: defaults, to_dict, from_dict, human_summary
- KnownGoodStateService.load(): None when absent, returns snapshot when present
- KnownGoodStateService.mark(): writes file, backs up previous, returns MarkResult
- mark() refused when blocking doctor checks exist
- mark() allowed with force=True even when blocking checks exist
- KnownGoodStateService.diff(): StateDiff when no known-good (has_known_good=False)
- diff() is_clean when no changes
- diff() detects config_hash, layout_hash, fingerprint_hash changes
- diff() detects camera changes
- to_dict() is JSON-serializable
- khptz known-good show exits 1 when no snapshot
- khptz known-good mark exits 0 and writes state file
- khptz known-good diff exits 0 when clean, 1 when changes
- khptz known-good show --json produces valid JSON
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from application.known_good_state_service import (
    FieldDiff,
    KnownGoodSnapshot,
    KnownGoodStateService,
    MarkResult,
    StateDiff,
)


# ── KnownGoodSnapshot ─────────────────────────────────────────────────────────

class TestKnownGoodSnapshot:

    def test_defaults_are_unknown(self):
        snap = KnownGoodSnapshot()
        assert snap.marked_at == "unknown"
        assert snap.installation_id == "unknown"
        assert snap.app_version == "unknown"
        assert snap.config_hash == "unknown"
        assert snap.fingerprint_hash == "unknown"

    def test_cameras_default_is_empty_list(self):
        assert KnownGoodSnapshot().cameras == []

    def test_to_dict_is_json_serializable(self):
        snap = KnownGoodSnapshot(
            marked_at="2026-05-01T12:00:00+00:00",
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
            cameras=[{"role": "cam1", "configured": "yes"}],
        )
        d = snap.to_dict()
        json.dumps(d)  # must not raise

    def test_from_dict_roundtrip(self):
        original = KnownGoodSnapshot(
            marked_at="2026-05-01T12:00:00+00:00",
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
            git_commit="abc1234",
            config_hash="deadbeef",
        )
        recovered = KnownGoodSnapshot.from_dict(original.to_dict())
        assert recovered.installation_id == "khptz-2026-0042"
        assert recovered.app_version == "3.18.0"
        assert recovered.config_hash == "deadbeef"

    def test_from_dict_ignores_unknown_keys(self):
        data = {
            "installation_id": "khptz-2026-0042",
            "future_field": "ignored",
        }
        snap = KnownGoodSnapshot.from_dict(data)
        assert snap.installation_id == "khptz-2026-0042"

    def test_human_summary_returns_list_of_strings(self):
        snap = KnownGoodSnapshot(
            marked_at="2026-05-01T12:00:00+00:00",
            installation_id="khptz-2026-0042",
        )
        lines = snap.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_human_summary_contains_installation_id(self):
        snap = KnownGoodSnapshot(installation_id="khptz-2026-0042")
        summary = "\n".join(snap.human_summary())
        assert "khptz-2026-0042" in summary

    def test_human_summary_truncates_long_hashes(self):
        snap = KnownGoodSnapshot(config_hash="a" * 64, fingerprint_hash="b" * 64)
        summary = "\n".join(snap.human_summary())
        assert "a" * 64 not in summary
        assert "…" in summary

    def test_human_summary_shows_note_when_set(self):
        snap = KnownGoodSnapshot(mark_note="post-commissioning check")
        summary = "\n".join(snap.human_summary())
        assert "post-commissioning check" in summary

    def test_human_summary_omits_note_when_empty(self):
        snap = KnownGoodSnapshot(mark_note="")
        lines = snap.human_summary()
        assert not any("Note:" in l for l in lines)


# ── StateDiff ─────────────────────────────────────────────────────────────────

class TestStateDiff:

    def test_no_known_good_is_not_clean(self):
        diff = StateDiff(has_known_good=False, no_known_good_reason="none recorded")
        assert not diff.is_clean

    def test_clean_diff_is_clean(self):
        diff = StateDiff(has_known_good=True, changes=[], unchanged_fields=["config_hash"])
        assert diff.is_clean

    def test_dirty_diff_is_not_clean(self):
        diff = StateDiff(
            has_known_good=True,
            changes=[FieldDiff("config_hash", "old", "new")],
        )
        assert not diff.is_clean

    def test_to_dict_is_json_serializable(self):
        diff = StateDiff(
            has_known_good=True,
            changes=[FieldDiff("config_hash", "old", "new")],
            unchanged_fields=["layout_hash"],
        )
        d = diff.to_dict()
        json.dumps(d)  # must not raise

    def test_to_dict_has_required_keys(self):
        diff = StateDiff(has_known_good=True)
        d = diff.to_dict()
        for key in ("has_known_good", "is_clean", "changes", "unchanged_fields"):
            assert key in d

    def test_human_summary_no_known_good(self):
        diff = StateDiff(has_known_good=False, no_known_good_reason="none recorded")
        lines = diff.human_summary()
        assert any("none recorded" in l for l in lines)

    def test_human_summary_clean(self):
        diff = StateDiff(has_known_good=True, changes=[])
        lines = diff.human_summary()
        assert any("no changes" in l.lower() for l in lines)

    def test_human_summary_dirty_shows_field_name(self):
        diff = StateDiff(
            has_known_good=True,
            changes=[FieldDiff("config_hash", "aaa", "bbb")],
        )
        summary = "\n".join(diff.human_summary())
        assert "config_hash" in summary


# ── KnownGoodStateService ─────────────────────────────────────────────────────

def _make_paths(tmp_path: Path):
    mock = MagicMock()
    mock.data_dir = tmp_path / "data"
    state_file = tmp_path / "data" / "known_good_state.json"
    mock.known_good_state_file = state_file
    return mock


def _fake_fp(
    installation_id="khptz-test",
    app_version="3.18.0",
    git_commit="abc1234",
    runtime_profile="production",
    config_hash="cfg_hash_aaa",
    layout_hash="lay_hash_bbb",
    cameras=None,
    atem_enabled="unknown",
    atem_configured="no",
):
    from application.fingerprint_service import InstallationFingerprint
    fp = InstallationFingerprint(
        installation_id=installation_id,
        app_version=app_version,
        git_commit=git_commit,
        profile=runtime_profile,
        config_hash=config_hash,
        layout_hash=layout_hash,
        cameras=cameras or [],
        atem_enabled=atem_enabled,
        atem_configured=atem_configured,
    )
    return fp


class TestKnownGoodStateServiceLoad:

    def test_load_returns_none_when_file_absent(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        assert svc.load() is None

    def test_load_returns_snapshot_when_file_present(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        snap = KnownGoodSnapshot(installation_id="khptz-2026-0042", app_version="3.18.0")
        paths.known_good_state_file.write_text(
            json.dumps(snap.to_dict()), encoding="utf-8"
        )
        svc = KnownGoodStateService(paths=paths)
        loaded = svc.load()
        assert loaded is not None
        assert loaded.installation_id == "khptz-2026-0042"

    def test_load_returns_none_on_corrupt_file(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        paths.known_good_state_file.write_text("not valid json{{", encoding="utf-8")
        svc = KnownGoodStateService(paths=paths)
        assert svc.load() is None


class TestKnownGoodStateServiceMark:

    def test_mark_writes_state_file(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            result = svc.mark()
        assert result.success
        assert paths.known_good_state_file.exists()

    def test_mark_state_file_is_valid_json(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            svc.mark()
        data = json.loads(paths.known_good_state_file.read_text(encoding="utf-8"))
        assert "installation_id" in data
        assert "marked_at" in data

    def test_mark_stores_fingerprint_fields(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp(installation_id="khptz-2026-0042", app_version="3.18.0")
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            svc.mark()
        loaded = svc.load()
        assert loaded.installation_id == "khptz-2026-0042"
        assert loaded.app_version == "3.18.0"

    def test_mark_backs_up_previous_snapshot(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        # Write a previous snapshot
        old_snap = KnownGoodSnapshot(marked_at="2026-01-01T00:00:00+00:00")
        paths.known_good_state_file.write_text(
            json.dumps(old_snap.to_dict()), encoding="utf-8"
        )
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            result = svc.mark()
        assert result.previous_backed_up
        # Backup file should exist
        backups = list(paths.known_good_state_file.parent.glob("known_good_state.*.bak.json"))
        assert len(backups) == 1

    def test_mark_refused_when_blocking_checks(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers",
                   return_value=["data_dir"]):
            result = svc.mark()
        assert not result.success
        assert "data_dir" in result.blocked_by

    def test_mark_allowed_with_force_despite_blockers(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers",
                   return_value=["data_dir"]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            result = svc.mark(force=True)
        assert result.success

    def test_mark_attaches_note(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            svc.mark(note="post-install validation")
        loaded = svc.load()
        assert loaded.mark_note == "post-install validation"

    def test_mark_result_summary_is_string(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.known_good_state_service.KnownGoodStateService._find_blockers", return_value=[]), \
             patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            result = svc.mark()
        assert isinstance(result.summary(), str)


class TestKnownGoodStateServiceDiff:

    def test_diff_no_known_good(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            diff = svc.diff()
        assert not diff.has_known_good

    def test_diff_clean_when_no_changes(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        fp = _fake_fp()
        # Store a snapshot that matches the fp
        snap = KnownGoodSnapshot(
            installation_id=fp.installation_id,
            app_version=fp.app_version,
            git_commit=fp.git_commit,
            profile=fp.profile,
            config_hash=fp.config_hash,
            layout_hash=fp.layout_hash,
            fingerprint_hash=fp.fingerprint_hash(),
            cameras=fp.cameras,
            atem_enabled=fp.atem_enabled,
            atem_configured=fp.atem_configured,
        )
        paths.known_good_state_file.write_text(
            json.dumps(snap.to_dict()), encoding="utf-8"
        )
        svc = KnownGoodStateService(paths=paths)
        with patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            diff = svc.diff()
        assert diff.has_known_good
        assert diff.is_clean

    def test_diff_detects_config_hash_change(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        fp_old = _fake_fp(config_hash="old_cfg_hash")
        snap = KnownGoodSnapshot(
            installation_id=fp_old.installation_id,
            app_version=fp_old.app_version,
            git_commit=fp_old.git_commit,
            profile=fp_old.profile,
            config_hash=fp_old.config_hash,
            layout_hash=fp_old.layout_hash,
            fingerprint_hash=fp_old.fingerprint_hash(),
            cameras=fp_old.cameras,
            atem_enabled=fp_old.atem_enabled,
            atem_configured=fp_old.atem_configured,
        )
        paths.known_good_state_file.write_text(
            json.dumps(snap.to_dict()), encoding="utf-8"
        )
        svc = KnownGoodStateService(paths=paths)
        fp_new = _fake_fp(config_hash="new_cfg_hash")
        with patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp_new
            diff = svc.diff()
        assert diff.has_known_good
        assert not diff.is_clean
        changed_fields = [c.field for c in diff.changes]
        assert "config_hash" in changed_fields

    def test_diff_detects_camera_change(self, tmp_path):
        paths = _make_paths(tmp_path)
        paths.known_good_state_file.parent.mkdir(parents=True, exist_ok=True)
        fp_old = _fake_fp(cameras=[{"role": "cam1", "configured": "yes"}])
        snap = KnownGoodSnapshot(
            installation_id=fp_old.installation_id,
            app_version=fp_old.app_version,
            git_commit=fp_old.git_commit,
            profile=fp_old.profile,
            config_hash=fp_old.config_hash,
            layout_hash=fp_old.layout_hash,
            fingerprint_hash=fp_old.fingerprint_hash(),
            cameras=fp_old.cameras,
            atem_enabled=fp_old.atem_enabled,
            atem_configured=fp_old.atem_configured,
        )
        paths.known_good_state_file.write_text(
            json.dumps(snap.to_dict()), encoding="utf-8"
        )
        svc = KnownGoodStateService(paths=paths)
        fp_new = _fake_fp(cameras=[])  # camera removed
        with patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp_new
            diff = svc.diff()
        assert "cameras" in [c.field for c in diff.changes]

    def test_diff_to_dict_is_json_serializable(self, tmp_path):
        paths = _make_paths(tmp_path)
        svc = KnownGoodStateService(paths=paths)
        fp = _fake_fp()
        with patch("application.fingerprint_service.FingerprintService") as mock_svc:
            mock_svc.return_value.generate.return_value = fp
            diff = svc.diff()
        json.dumps(diff.to_dict())  # must not raise


# ── CLI integration ───────────────────────────────────────────────────────────

class TestKnownGoodCLI:

    def test_show_exits_one_when_no_snapshot(self, tmp_path):
        from runtime.cli import main
        with patch("application.known_good_state_service.KnownGoodStateService.load",
                   return_value=None):
            rc = main(["known-good", "show"])
        assert rc == 1

    def test_show_exits_zero_when_snapshot_present(self, tmp_path, capsys):
        from runtime.cli import main
        snap = KnownGoodSnapshot(
            installation_id="khptz-2026-0042",
            marked_at="2026-05-01T12:00:00+00:00",
        )
        with patch("application.known_good_state_service.KnownGoodStateService.load",
                   return_value=snap):
            rc = main(["known-good", "show"])
        assert rc == 0

    def test_show_json_produces_valid_json(self, capsys):
        from runtime.cli import main
        snap = KnownGoodSnapshot(installation_id="khptz-2026-0042")
        with patch("application.known_good_state_service.KnownGoodStateService.load",
                   return_value=snap):
            rc = main(["known-good", "show", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["installation_id"] == "khptz-2026-0042"

    def test_mark_exits_zero_on_success(self, tmp_path):
        from runtime.cli import main
        result = MarkResult(success=True, message="Marked OK")
        with patch("application.known_good_state_service.KnownGoodStateService.mark",
                   return_value=result):
            rc = main(["known-good", "mark"])
        assert rc == 0

    def test_mark_exits_one_on_failure(self, tmp_path):
        from runtime.cli import main
        result = MarkResult(
            success=False,
            message="Refused",
            blocked_by=["data_dir"],
        )
        with patch("application.known_good_state_service.KnownGoodStateService.mark",
                   return_value=result):
            rc = main(["known-good", "mark"])
        assert rc == 1

    def test_diff_exits_zero_when_clean(self, capsys):
        from runtime.cli import main
        diff = StateDiff(has_known_good=True, changes=[], unchanged_fields=["config_hash"])
        with patch("application.known_good_state_service.KnownGoodStateService.diff",
                   return_value=diff):
            rc = main(["known-good", "diff"])
        assert rc == 0

    def test_diff_exits_one_when_dirty(self, capsys):
        from runtime.cli import main
        diff = StateDiff(
            has_known_good=True,
            changes=[FieldDiff("config_hash", "old", "new")],
        )
        with patch("application.known_good_state_service.KnownGoodStateService.diff",
                   return_value=diff):
            rc = main(["known-good", "diff"])
        assert rc == 1

    def test_diff_json_produces_valid_json(self, capsys):
        from runtime.cli import main
        diff = StateDiff(has_known_good=True, changes=[])
        with patch("application.known_good_state_service.KnownGoodStateService.diff",
                   return_value=diff):
            main(["known-good", "diff", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "has_known_good" in data
        assert "is_clean" in data

