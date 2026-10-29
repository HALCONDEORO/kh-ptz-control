#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_install_state_reader.py — the Python side of the install-state reader
#
# runtime/install_state.py is consulted by the CLI and the provisioning entry
# point to answer one question: which process owns the GUI (#885). Getting it
# wrong is not cosmetic — a component that assumes the system service will
# enable khptz-control on a session-owned install leaves the appliance booting
# two full-screen GUIs against the same cameras.
#
# tests/test_gui_mode_consistency.py executes the *shell* reader and greps the
# scripts. This file drives the Python reader directly: its parsing rules, its
# failure modes (a caller must never see an exception over a missing install)
# and its agreement with the shell reader on the same file.

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from runtime import install_state

REPO_ROOT = Path(__file__).resolve().parent.parent
SHELL_LIB = REPO_ROOT / "scripts" / "lib" / "install_state.sh"


class _Resolver:
    """Stand-in for RuntimePathResolver — only config_dir is consulted."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def resolver(state_dir: Path) -> _Resolver:
    return _Resolver(state_dir)


def write_state(state_dir: Path, contents: str) -> Path:
    path = state_dir / install_state.STATE_FILENAME
    path.write_text(contents, encoding="utf-8")
    return path


class TestStateValueParsing:
    def test_reads_a_quoted_value(self, state_dir, resolver):
        write_state(state_dir, 'KHPTZ_WIZARD_USER="khptz"\n')
        assert install_state.state_value("KHPTZ_WIZARD_USER", resolver) == "khptz"

    def test_reads_an_unquoted_value(self, state_dir, resolver):
        write_state(state_dir, "KHPTZ_WIZARD_USER=khptz\n")
        assert install_state.state_value("KHPTZ_WIZARD_USER", resolver) == "khptz"

    def test_reads_a_single_quoted_value(self, state_dir, resolver):
        write_state(state_dir, "KHPTZ_WIZARD_USER='khptz'\n")
        assert install_state.state_value("KHPTZ_WIZARD_USER", resolver) == "khptz"

    def test_picks_the_key_out_of_a_full_state_file(self, state_dir, resolver):
        write_state(state_dir, "\n".join([
            'KHPTZ_INSTALL_MODE="product"',
            'KHPTZ_SOURCE_DIR="/home/khptz/Update2026"',
            'KHPTZ_WIZARD_USER="khptz"',
            'KHPTZ_GUI_MODE="user"',
            'KHPTZ_INSTALLED_AT="2026-07-26T00:00:00Z"',
        ]) + "\n")
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == "user"

    def test_last_occurrence_wins(self, state_dir, resolver):
        """install.sh rewrites the file on every deploy; a duplicated key means
        the newest line is the truth. The shell reader tails, so this must too."""
        write_state(state_dir, 'KHPTZ_GUI_MODE="system"\nKHPTZ_GUI_MODE="user"\n')
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == "user"

    def test_absent_key_is_empty(self, state_dir, resolver):
        write_state(state_dir, 'KHPTZ_WIZARD_USER="khptz"\n')
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == ""

    def test_key_match_is_exact(self, state_dir, resolver):
        """A prefix match would let KHPTZ_GUI_MODE_PREVIOUS answer for the live
        setting."""
        write_state(state_dir, 'KHPTZ_GUI_MODE_PREVIOUS="user"\n')
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == ""

    def test_value_whitespace_is_trimmed(self, state_dir, resolver):
        write_state(state_dir, "KHPTZ_GUI_MODE = user \n")
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == "user"

    def test_lines_without_a_separator_are_ignored(self, state_dir, resolver):
        write_state(state_dir, "# a comment\n\nKHPTZ_GUI_MODE=user\ngarbage\n")
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == "user"

    def test_empty_value_is_empty(self, state_dir, resolver):
        write_state(state_dir, 'KHPTZ_GUI_MODE=""\n')
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == ""

    def test_undecodable_bytes_do_not_raise(self, state_dir, resolver):
        """A truncated write can leave a partial multi-byte sequence behind."""
        path = state_dir / install_state.STATE_FILENAME
        path.write_bytes(b'KHPTZ_GUI_MODE="user"\nKHPTZ_NOTE="\xff\xfe"\n')
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == "user"

    def test_the_file_is_never_executed(self, state_dir, resolver):
        """It is parsed, not sourced: a command substitution stays inert text."""
        marker = state_dir / "pwned"
        write_state(
            state_dir,
            f'KHPTZ_GUI_MODE="$(touch {marker.as_posix()})"\n',
        )
        assert install_state.gui_mode(resolver) == install_state.GUI_MODE_SYSTEM
        assert not marker.exists()


class TestStateValueFailureModes:
    """A caller must never be handed an exception over install metadata."""

    def test_missing_file_is_empty(self, resolver):
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == ""

    def test_unreadable_path_is_empty(self, state_dir, resolver):
        # A directory where the file should be: read_text raises OSError.
        (state_dir / install_state.STATE_FILENAME).mkdir()
        assert install_state.state_value("KHPTZ_GUI_MODE", resolver) == ""

    def test_a_broken_resolver_is_empty(self):
        class Exploding:
            @property
            def config_dir(self):
                raise RuntimeError("no runtime paths on this box")

        assert install_state.state_value("KHPTZ_GUI_MODE", Exploding()) == ""

    def test_falls_back_to_the_real_resolver(self, tmp_path, monkeypatch):
        """Called with no resolver — the production call shape — it reads the
        configured config dir."""
        monkeypatch.setenv("KHPTZ_CONFIG_DIR", str(tmp_path))
        write_state(tmp_path, 'KHPTZ_GUI_MODE="user"\n')
        assert install_state.state_value("KHPTZ_GUI_MODE") == "user"


class TestGuiMode:
    @pytest.mark.parametrize("contents,expected", [
        ('KHPTZ_GUI_MODE="user"\n', "user"),
        ("KHPTZ_GUI_MODE=user\n", "user"),
        ('KHPTZ_GUI_MODE="system"\n', "system"),
        ('KHPTZ_GUI_MODE="banana"\n', "system"),      # unknown value
        ('KHPTZ_GUI_MODE=""\n', "system"),            # empty value
        ('KHPTZ_WIZARD_USER="khptz"\n', "system"),      # key absent
        ('KHPTZ_GUI_MODE="User"\n', "system"),        # case is not normalised
        # Padding *inside* the quotes is part of the value, so it is not the
        # recognised mode. The shell reader tr-deletes quotes and case-matches,
        # reaching the same answer — see TestParityWithTheShellReader.
        ('KHPTZ_GUI_MODE="user "\n', "system"),
        # Padding *outside* the quotes is trimmed. The shell reader is stricter
        # here (its sed matches "KEY=" literally), so a hand-edited file with
        # spaces around the separator is the one input where the two readers
        # can differ. install.sh only ever writes KEY="value", so no install
        # reaches that state — the parity cases below cover what it writes.
        ("KHPTZ_GUI_MODE= user\n", "user"),
    ])
    def test_mode(self, state_dir, resolver, contents, expected):
        write_state(state_dir, contents)
        assert install_state.gui_mode(resolver) == expected

    def test_missing_file_falls_back_to_system(self, resolver):
        """Installs predating the flag were all system mode, and guessing
        'user' would disable the only launcher such a machine has."""
        assert install_state.gui_mode(resolver) == install_state.GUI_MODE_SYSTEM

    def test_never_returns_anything_else(self, state_dir, resolver):
        for contents in ('KHPTZ_GUI_MODE="x"\n', "KHPTZ_GUI_MODE=\n", "junk\n"):
            write_state(state_dir, contents)
            assert install_state.gui_mode(resolver) in {
                install_state.GUI_MODE_SYSTEM, install_state.GUI_MODE_USER,
            }


class TestSessionOwnedPredicate:
    def test_true_only_in_user_mode(self, state_dir, resolver):
        write_state(state_dir, 'KHPTZ_GUI_MODE="user"\n')
        assert install_state.gui_is_session_owned(resolver) is True

    def test_false_in_system_mode(self, state_dir, resolver):
        write_state(state_dir, 'KHPTZ_GUI_MODE="system"\n')
        assert install_state.gui_is_session_owned(resolver) is False

    def test_false_without_an_install(self, resolver):
        assert install_state.gui_is_session_owned(resolver) is False


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="WSL bash cannot resolve a C:/ path; runs on Linux CI and the Pi",
)
class TestParityWithTheShellReader:
    """The two readers exist because the install path crosses languages. They
    are only safe while they answer identically — the shell library is what
    repair_rpi_runtime.sh and rollback.sh consult, the Python one is what the
    CLI consults, and a disagreement means two launchers."""

    def _shell_mode(self, path: Path) -> str:
        # `export` on its own statement: an assignment prefix to a special
        # builtin (`source`) does not persist past it in bash, so the library
        # would lose the path before the reader ran and answer "system" for
        # every input — a parity test that can only ever pass one way proves
        # nothing.
        result = subprocess.run(
            ["bash", "-c",
             f'export KHPTZ_INSTALL_STATE="{path.as_posix()}"; '
             f'source "{SHELL_LIB.as_posix()}"; khptz_gui_mode'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    @pytest.mark.parametrize("contents", [
        'KHPTZ_GUI_MODE="user"\n',
        "KHPTZ_GUI_MODE=user\n",
        'KHPTZ_GUI_MODE="system"\n',
        'KHPTZ_GUI_MODE="banana"\n',
        'KHPTZ_GUI_MODE=""\n',
        'KHPTZ_WIZARD_USER="khptz"\n',
        'KHPTZ_GUI_MODE="system"\nKHPTZ_GUI_MODE="user"\n',
        'KHPTZ_INSTALL_MODE="product"\nKHPTZ_GUI_MODE="user"\nKHPTZ_WIZARD_USER="khptz"\n',
    ])
    def test_both_readers_agree(self, state_dir, resolver, contents):
        path = write_state(state_dir, contents)
        assert install_state.gui_mode(resolver) == self._shell_mode(path)

    def test_both_readers_agree_without_a_state_file(self, state_dir, resolver):
        missing = state_dir / install_state.STATE_FILENAME
        assert install_state.gui_mode(resolver) == self._shell_mode(missing)
