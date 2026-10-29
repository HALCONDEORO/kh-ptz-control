#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_bump_version.py — Tests for scripts/bump_version.py

from __future__ import annotations


from scripts.bump_version import bump, detect_bump


# ═══════════════════════════════════════════════════════════════════════════════
# detect_bump — major triggers
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectBumpMajor:
    def test_breaking_change_keyword(self):
        assert detect_bump("BREAKING CHANGE: removed old API") == "major"

    def test_breaking_change_hyphen(self):
        assert detect_bump("BREAKING-CHANGE: removed API") == "major"

    def test_breaking_prefix(self):
        assert detect_bump("breaking: drop Python 3.9 support") == "major"

    def test_major_prefix(self):
        assert detect_bump("major: new architecture") == "major"

    def test_feat_bang(self):
        assert detect_bump("feat!: new incompatible format") == "major"

    def test_fix_bang(self):
        assert detect_bump("fix!: rewrite error handling") == "major"

    def test_refactor_bang(self):
        assert detect_bump("refactor!: restructure module layout") == "major"

    def test_perf_bang(self):
        assert detect_bump("perf!: change return type") == "major"

    def test_chore_bang(self):
        assert detect_bump("chore!: migrate config format") == "major"

    def test_docs_bang(self):
        assert detect_bump("docs!: rewrite public API docs") == "major"

    def test_scoped_feat_bang(self):
        assert detect_bump("feat(ui)!: remove legacy panel") == "major"

    def test_scoped_fix_bang(self):
        assert detect_bump("fix(api)!: change response shape") == "major"

    def test_breaking_change_in_body(self):
        assert detect_bump("feat: add thing\n\nBREAKING CHANGE: old arg removed") == "major"

    def test_breaking_keyword_case_insensitive(self):
        assert detect_bump("breaking change: old api") == "major"


# ═══════════════════════════════════════════════════════════════════════════════
# detect_bump — minor triggers
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectBumpMinor:
    def test_feat_prefix(self):
        assert detect_bump("feat: add new button") == "minor"

    def test_feature_prefix(self):
        assert detect_bump("feature: extended camera support") == "minor"

    def test_minor_prefix(self):
        assert detect_bump("minor: small enhancement") == "minor"

    def test_feat_scoped(self):
        assert detect_bump("feat(ui): new dialog") == "minor"

    def test_feature_scoped(self):
        assert detect_bump("feature(camera): multi-cam support") == "minor"

    def test_feat_case_insensitive(self):
        assert detect_bump("Feat: new preset panel") == "minor"

    def test_feature_case_insensitive(self):
        assert detect_bump("FEATURE: big new thing") == "minor"


# ═══════════════════════════════════════════════════════════════════════════════
# detect_bump — patch triggers
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectBumpPatch:
    def test_fix_prefix(self):
        assert detect_bump("fix: resolve preset off-by-one") == "patch"

    def test_docs_prefix(self):
        assert detect_bump("docs: update README") == "patch"

    def test_chore_prefix(self):
        assert detect_bump("chore: update dependencies") == "patch"

    def test_test_prefix(self):
        assert detect_bump("test: add coverage for session") == "patch"

    def test_refactor_prefix(self):
        assert detect_bump("refactor: extract helper method") == "patch"

    def test_perf_prefix(self):
        assert detect_bump("perf: reduce startup time") == "patch"

    def test_style_prefix(self):
        assert detect_bump("style: reformat module") == "patch"

    def test_build_prefix(self):
        assert detect_bump("build: update CI workflow") == "patch"

    def test_ci_prefix(self):
        assert detect_bump("ci: fix linting step") == "patch"

    def test_no_prefix(self):
        assert detect_bump("just a plain commit message") == "patch"

    def test_empty_message(self):
        assert detect_bump("") == "patch"

    def test_fix_scoped(self):
        assert detect_bump("fix(camera): handle timeout correctly") == "patch"


# ═══════════════════════════════════════════════════════════════════════════════
# detect_bump — precedence (major wins over minor/patch)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectBumpPrecedence:
    def test_major_wins_over_minor_prefix(self):
        # Message starts with feat: (minor) but body has BREAKING CHANGE (major)
        assert detect_bump("feat: new thing\n\nBREAKING CHANGE: old removed") == "major"

    def test_bang_wins_over_feat(self):
        # feat!: is major, not minor
        assert detect_bump("feat!: something") == "major"

    def test_non_bang_feat_is_minor_not_patch(self):
        assert detect_bump("feat: add feature") == "minor"


# ═══════════════════════════════════════════════════════════════════════════════
# bump — version arithmetic
# ═══════════════════════════════════════════════════════════════════════════════

class TestBump:
    def test_major_increments_major_resets_minor_patch(self):
        assert bump("1.2.3", "major") == "2.0.0"

    def test_minor_increments_minor_resets_patch(self):
        assert bump("1.2.3", "minor") == "1.3.0"

    def test_patch_increments_patch_only(self):
        assert bump("1.2.3", "patch") == "1.2.4"

    def test_major_from_zero(self):
        assert bump("0.0.0", "major") == "1.0.0"

    def test_minor_from_zero(self):
        assert bump("0.0.0", "minor") == "0.1.0"

    def test_patch_from_zero(self):
        assert bump("0.0.0", "patch") == "0.0.1"

    def test_major_with_large_numbers(self):
        assert bump("10.20.30", "major") == "11.0.0"

    def test_minor_with_large_numbers(self):
        assert bump("10.20.30", "minor") == "10.21.0"

    def test_patch_with_large_numbers(self):
        assert bump("10.20.30", "patch") == "10.20.31"

    def test_major_resets_double_digit_minor(self):
        assert bump("1.99.99", "major") == "2.0.0"

    def test_result_is_string(self):
        assert isinstance(bump("1.0.0", "patch"), str)

    def test_result_has_three_parts(self):
        result = bump("1.2.3", "minor")
        assert len(result.split(".")) == 3

    def test_all_parts_are_numeric(self):
        result = bump("1.2.3", "major")
        for part in result.split("."):
            assert part.isdigit()
