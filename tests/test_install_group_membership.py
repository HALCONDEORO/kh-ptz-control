#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_install_group_membership.py — group membership is a precondition (#885)
#
# App code is installed root:khptz 0750, so the desktop user needs membership of
# the khptz group to traverse /opt/khptz at all. Without it:
#
#   - `khptz setup` cannot read runtime/cli.py, so the wizard never opens;
#   - under --gui-mode user, khptz-gui.service cannot start — its
#     WorkingDirectory and ExecStart both live in /opt/khptz — leaving an
#     appliance with no GUI whatsoever.
#
# The usermod call used to be nested inside the wizard launcher's "both .desktop
# templates exist" branch, so a partially deployed or trimmed tree skipped a
# step the whole install depends on.

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "runtime" / "installer" / "install.sh"


@pytest.fixture(scope="module")
def text() -> str:
    return INSTALLER.read_text(encoding="utf-8")


class TestMembershipIsUnconditional:
    def test_usermod_is_present(self, text):
        assert "usermod -aG" in text

    def test_usermod_does_not_depend_on_the_desktop_templates(self, text):
        """The launcher templates are cosmetic; membership is not."""
        usermod = text.index("usermod -aG")
        templates = text.index("DESKTOP_TEMPLATE=")
        assert usermod < templates, (
            "usermod is inside the wizard-launcher branch; a missing .desktop "
            "template would skip group membership entirely"
        )

    def test_guarded_by_product_mode_only(self, text):
        """A developer install runs from the checkout as the developer, so no
        service group is involved."""
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert 'DEV_MODE}" == "false"' in block

    def test_skips_when_the_wizard_user_is_the_service_user(self, text):
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert 'WIZARD_USER}" != "${APP_USER}"' in block

    def test_is_idempotent(self, text):
        """Re-running must not churn or misreport an existing membership."""
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert "already in the" in block
        assert "id -nG" in block


class TestFailureIsActionable:
    def test_explains_both_consequences(self, text):
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert "setup wizard cannot read" in block
        assert "gui-mode user" in block

    def test_gives_the_manual_recovery_command(self, text):
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert re.search(r"sudo usermod -aG \$\{APP_USER\} \$\{WIZARD_USER\}", block)

    def test_does_not_abort_the_install(self, text):
        """A failed usermod is recoverable by hand; aborting would leave a
        half-installed appliance instead."""
        block = text[text.index("Desktop user group membership"):text.index("DESKTOP_TEMPLATE=")]
        assert "error " not in block.lower().replace("[error]", "")
