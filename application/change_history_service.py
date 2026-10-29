#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/change_history_service.py — Config change history recorder
#
# ChangeHistoryService writes ChangeEvents to change_history.json as newline-
# delimited JSON (one JSON object per line). This format lets the file grow
# without ever loading the entire history into memory.
#
# read_recent(n) parses only the last n lines — cheap even on large files.
# has_changes() returns True when any events exist.
#
# No passwords or personal speaker names are written; callers must sanitise
# old_value/new_value before passing them in.

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from domain.change_event import ChangeEvent

logger = logging.getLogger(__name__)

_MAX_LINES_DEFAULT = 10_000   # rotate at this many entries


class ChangeHistoryService:
    """
    Appends ChangeEvents to a newline-delimited JSON file and reads recent ones.

    Thread-safe for single-process use (file-level append is atomic on Linux/Win
    for single-writer scenarios; no cross-process locking implemented here).
    """

    def __init__(
        self,
        history_path: Optional[Path] = None,
        max_lines: int = _MAX_LINES_DEFAULT,
    ) -> None:
        if history_path is None:
            from runtime.path_resolver import RuntimePathResolver
            history_path = RuntimePathResolver().change_history_file
        self._path = history_path
        self._max_lines = max_lines

    def record(self, event: ChangeEvent) -> bool:
        """
        Append *event* to the history file.

        Returns True on success, False if the write fails (non-fatal — the
        caller should continue even if history cannot be recorded).
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            logger.debug("Change recorded: %s/%s on %s", event.area, event.action, event.target)
            return True
        except OSError as exc:
            logger.warning("Could not record change event: %s", exc)
            return False

    def read_recent(self, n: int = 10) -> List[ChangeEvent]:
        """
        Return the *n* most recent events, newest-last.

        Returns [] if the file does not exist or is empty.
        """
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            recent_lines = lines[-n:] if len(lines) > n else lines
            events = []
            for line in recent_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(ChangeEvent.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Skipping corrupt history line: %s", exc)
            return events
        except OSError as exc:
            logger.warning("Could not read change history: %s", exc)
            return []

    def has_changes(self) -> bool:
        """Return True if any events exist in the history file."""
        return bool(self.read_recent(1))

    def event_count(self) -> int:
        """Return the total number of recorded events."""
        if not self._path.exists():
            return 0
        try:
            count = 0
            with self._path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        count += 1
            return count
        except OSError:
            return 0

    def rotate_if_needed(self) -> bool:
        """
        Keep the history file under max_lines by discarding the oldest entries.

        Returns True if rotation was performed.
        """
        if not self._path.exists():
            return False
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= self._max_lines:
                return False
            keep = lines[-self._max_lines:]
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text("\n".join(keep) + "\n", encoding="utf-8")
            os.replace(tmp, self._path)
            logger.info("Change history rotated: kept %d/%d entries", len(keep), len(lines))
            return True
        except OSError as exc:
            logger.warning("Could not rotate change history: %s", exc)
            return False
