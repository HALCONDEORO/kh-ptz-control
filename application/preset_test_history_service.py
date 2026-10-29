#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.json_io import load_json, save_json

MAX_HISTORY_ENTRIES = 50


class PresetTestHistoryService:
    def __init__(self, history_file: Path | None = None) -> None:
        if history_file is None:
            from runtime.path_resolver import RuntimePathResolver
            history_file = RuntimePathResolver().data_dir / "preset_test_history.json"
        self._file = history_file

    def record(self, total: int, ok: int, warning: int, error: int, skipped: int, cancelled: bool) -> None:
        entries = load_json(self._file, default=[])
        if not isinstance(entries, list):
            entries = []
        entries.append({
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "total": total,
            "ok": ok,
            "warning": warning,
            "error": error,
            "skipped": skipped,
            "cancelled": cancelled,
        })
        if len(entries) > MAX_HISTORY_ENTRIES:
            entries = entries[-MAX_HISTORY_ENTRIES:]
        save_json(self._file, entries)

    def last_entry(self) -> dict | None:
        entries = load_json(self._file, default=[])
        if isinstance(entries, list) and entries:
            return entries[-1]
        return None

    def summary_line(self) -> str:
        entry = self.last_entry()
        if entry is None:
            return "No test runs yet"
        ts = entry.get("timestamp", "")
        total = entry.get("total", 0)
        ok = entry.get("ok", 0)
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(ts).astimezone()
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = ts[:16] if len(ts) >= 16 else ts
        cancelled = " (cancelled)" if entry.get("cancelled") else ""
        return f"Last test: {date_str} | {ok}/{total} OK{cancelled}"
