#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_logging_group_access.py — both identities can write app.log (#885)
#
# Under --gui-mode user two identities log to /var/log/hallptz: the GUI runs as the
# desktop user, while `hallptz doctor`, `hallptz backup` and the support bundle run as
# `hallptz`. Python opens log files at the default mode (0644 after a typical
# umask), so whichever creates app.log first owns it and the other gets
# read-only access — its file logging then degrades silently to console.
#
# Production logs are precisely what is needed when an appliance misbehaves, and
# a support bundle collected afterwards would be missing one side of the story.
# Rotation matters too: doRollover creates the next file, so ownership could
# flip mid-life and reintroduce the problem.

from __future__ import annotations

import logging
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from runtime import logging_setup


class TestHandlerAppliesTheSharedPolicy:
    def _chmod_modes(self, tmp_path: Path, dir_is_shared: bool) -> list[int]:
        handler = None
        try:
            with patch.object(
                logging_setup, "_GroupSharedRotatingFileHandler",
                logging_setup._GroupSharedRotatingFileHandler,
            ):
                with patch(
                    "core.atomic_write.group_shared_mode",
                    return_value=(0o660 if dir_is_shared else None),
                ):
                    with patch.object(logging_setup.os, "chmod") as chmod:
                        handler = logging_setup._GroupSharedRotatingFileHandler(
                            tmp_path / "app.log", maxBytes=1024, backupCount=1,
                            encoding="utf-8",
                        )
                        return [c.args[1] for c in chmod.call_args_list]
        finally:
            if handler is not None:
                handler.close()

    def test_shared_directory_makes_the_log_group_writable(self, tmp_path):
        assert self._chmod_modes(tmp_path, dir_is_shared=True) == [0o660]

    def test_private_directory_leaves_the_default(self, tmp_path):
        """System mode: only `hallptz` logs, so nothing is widened."""
        assert self._chmod_modes(tmp_path, dir_is_shared=False) == []

    def test_chmod_failure_never_breaks_logging(self, tmp_path):
        handler = None
        try:
            with patch("core.atomic_write.group_shared_mode", return_value=0o660):
                with patch.object(logging_setup.os, "chmod", side_effect=OSError("ro")):
                    handler = logging_setup._GroupSharedRotatingFileHandler(
                        tmp_path / "app.log", maxBytes=1024, backupCount=1,
                        encoding="utf-8",
                    )
                    handler.emit(logging.LogRecord(
                        "t", logging.INFO, __file__, 1, "hello", None, None
                    ))
            assert (tmp_path / "app.log").exists()
        finally:
            if handler is not None:
                handler.close()


class TestRotationKeepsTheAccess:
    def test_rollover_reapplies_the_mode(self, tmp_path):
        """doRollover opens the next file through _open, so the policy must be
        re-applied — otherwise the fix lasts only until the first rotation."""
        handler = None
        try:
            with patch("core.atomic_write.group_shared_mode", return_value=0o660):
                with patch.object(logging_setup.os, "chmod") as chmod:
                    handler = logging_setup._GroupSharedRotatingFileHandler(
                        tmp_path / "app.log", maxBytes=1, backupCount=1,
                        encoding="utf-8",
                    )
                    handler.setFormatter(logging.Formatter("%(message)s"))
                    record = logging.LogRecord(
                        "t", logging.INFO, __file__, 1, "x" * 200, None, None
                    )
                    # The first emit fills the (empty) file; rollover happens on
                    # the next one, once the size limit is already exceeded.
                    handler.emit(record)
                    before = len(chmod.call_args_list)
                    assert handler.shouldRollover(record), "test did not reach a rollover"
                    handler.emit(record)
                    assert len(chmod.call_args_list) > before, (
                        "rotation did not re-apply the group mode"
                    )
        finally:
            if handler is not None:
                handler.close()


class TestWiring:
    def test_setup_uses_the_group_aware_handler(self, tmp_path):
        source = Path(logging_setup.__file__).read_text(encoding="utf-8")
        assert "_GroupSharedRotatingFileHandler(" in source
        # The plain handler must not be constructed directly any more.
        constructed = [
            line for line in source.splitlines()
            if "logging.handlers.RotatingFileHandler(" in line
            and not line.lstrip().startswith(("#", "class"))
        ]
        assert not constructed, f"plain handler still constructed: {constructed}"

    def test_still_subclasses_rotating_handler(self):
        """`_has_file_handler` detects the handler by isinstance."""
        assert issubclass(
            logging_setup._GroupSharedRotatingFileHandler,
            logging.handlers.RotatingFileHandler,
        )

    def test_file_handler_detection_still_works(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logging_setup, "_configured", False)
        monkeypatch.setattr(logging_setup, "_added_handlers", [])
        root = logging.getLogger()
        existing = list(root.handlers)
        try:
            assert logging_setup.setup_logging(log_dir=tmp_path) is True
            assert logging_setup._has_file_handler(root) is True
        finally:
            for h in list(root.handlers):
                if h not in existing:
                    root.removeHandler(h)
                    h.close()


class TestPolicyIsShared:
    def test_uses_the_same_helper_as_data_writes(self):
        source = Path(logging_setup.__file__).read_text(encoding="utf-8")
        assert "group_shared_mode" in source

    @pytest.mark.parametrize("dir_mode,expected", [
        (0o42770, 0o660),
        (0o40750, None),
        (0o40750 | stat.S_IRGRP, None),
    ])
    def test_helper_decision_matches(self, dir_mode, expected):
        from core.atomic_write import group_shared_mode

        class _Dir:
            def stat(self):
                return SimpleNamespace(st_mode=dir_mode)

        assert group_shared_mode(_Dir()) == expected
