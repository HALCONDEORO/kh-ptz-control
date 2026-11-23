"""Offline layout-edit transactions. No camera or operator-runtime access."""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from application.layout_service import LayoutService
from core.atomic_write import write_bytes_atomic


@dataclass
class EditorError(Exception):
    code: str
    status: int = 409


def validate_document(document: dict) -> dict:
    """Accept only the current layout schema, never silently coerce bad fields."""
    root_fields = {"schema_version", "room_id", "room_name", "screen_width", "screen_height", "seats"}
    seat_fields = {"id", "label", "preset", "camera_role", "x", "y", "row", "column",
                   "type", "visible", "locked", "calibrated"}
    if not isinstance(document, dict) or set(document) != root_fields:
        raise EditorError("invalid_document", 422)
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise EditorError("unsupported_schema", 422)
    for key in ("room_id", "room_name"):
        if not isinstance(document[key], str) or not 1 <= len(document[key]) <= 120:
            raise EditorError("invalid_room", 422)
    for key in ("screen_width", "screen_height"):
        if type(document[key]) is not int or not 100 <= document[key] <= 10000:
            raise EditorError("invalid_dimensions", 422)
    seats = document["seats"]
    if not isinstance(seats, list) or len(seats) > 1000:
        raise EditorError("invalid_seats", 422)
    seen = set()
    bindings = set()
    for seat in seats:
        if not isinstance(seat, dict) or set(seat) - seat_fields or seat_fields - set(seat) - {"row", "column"}:
            raise EditorError("invalid_seat", 422)
        for key in ("id", "label", "camera_role", "type"):
            if not isinstance(seat[key], str) or not 1 <= len(seat[key]) <= 120:
                raise EditorError("invalid_seat_text", 422)
        if seat["id"] in seen:
            raise EditorError("duplicate_id", 422)
        seen.add(seat["id"])
        for key in ("visible", "locked", "calibrated"):
            if type(seat[key]) is not bool:
                raise EditorError("invalid_seat_flag", 422)
        for key in ("x", "y"):
            if type(seat[key]) not in (int, float) or not math.isfinite(seat[key]):
                raise EditorError("invalid_position", 422)
            limit = document["screen_width" if key == "x" else "screen_height"]
            if not 0 <= seat[key] <= limit - 40:
                raise EditorError("outside_layout", 422)
        for key in ("row", "column"):
            value = seat.get(key)
            if value is not None and (type(value) is not int or not 1 <= value <= 1000):
                raise EditorError("invalid_row_column", 422)
        preset = seat["preset"]
        if type(preset) is not int or not 0 <= preset <= 132:
            raise EditorError("invalid_preset", 422)
        if preset:
            binding = (seat["camera_role"], preset)
            if binding in bindings:
                raise EditorError("duplicate_binding", 422)
            bindings.add(binding)
        # New geometry intentionally has no camera memory attached.
        if preset == 0 and seat["calibrated"]:
            raise EditorError("unassigned_calibration", 422)
    return document


class WebLayoutEditor:
    """One writer lease, stale-read checks and immutable pre-save snapshots.

    The runtime adapter must own an OS process lock for the entire lifetime.
    Phase 1 operates exclusively on a separate, synthetic workspace.
    """
    def __init__(self, workspace: Path, *, clock=time.monotonic, lease_seconds=90):
        self.path = workspace / "room_layout.json"
        self.backups = workspace / "history"
        self.clock = clock
        self.lease_seconds = lease_seconds
        self._mutex = threading.Lock()
        self._owner = None
        self._deadline = 0
        self._service = LayoutService(self.path, legacy_positions={})

    def initialize(self):
        if not self.path.exists():
            raw = {"schema_version": 1, "room_id": "editor-sandbox", "room_name": "Test hall",
                   "screen_width": 1200, "screen_height": 800, "seats": []}
            if not self._service.save(self._service._deserialize(raw)):
                raise EditorError("save_failed", 500)
        self.read("initial-check")

    def _current(self):
        # No automatic default recovery: a corrupt master must be surfaced.
        content = self.path.read_bytes()
        document = validate_document(json.loads(content))
        return document, hashlib.sha256(content).hexdigest()

    def _owns(self, session):
        return self._owner == session and self.clock() < self._deadline

    def read(self, session):
        with self._mutex:
            document, revision = self._current()
            active = self._owner is not None and self.clock() < self._deadline
            return {"document": document, "revision": revision,
                    "lease": "mine" if self._owns(session) else "busy" if active else "free"}

    def acquire(self, session):
        with self._mutex:
            if self._owner is not None and self.clock() < self._deadline and self._owner != session:
                raise EditorError("editor_busy", 423)
            self._owner = session
            self._deadline = self.clock() + self.lease_seconds
            return {"lease": "mine", "expires_in": self.lease_seconds}

    def release(self, session):
        with self._mutex:
            if self._owns(session):
                self._owner = None
                self._deadline = 0
            return {"released": True}

    def save(self, session, revision, document):
        with self._mutex:
            if not self._owns(session):
                raise EditorError("lease_required", 423)
            _, current = self._current()
            if not isinstance(revision, str) or not secrets.compare_digest(current, revision):
                raise EditorError("revision_conflict")
            validate_document(document)
            # Preserve exact previous bytes before publication. Never overwrite history.
            self.backups.mkdir(exist_ok=True)
            backup = self.backups / (current + ".json")
            old_bytes = self.path.read_bytes()
            if not backup.exists():
                write_bytes_atomic(backup, old_bytes)
            elif backup.read_bytes() != old_bytes:
                raise EditorError("backup_mismatch", 500)
            layout = self._service._deserialize(document)
            if not self._service.save(layout):
                raise EditorError("save_failed", 500)
            _, saved = self._current()
            self._deadline = self.clock() + self.lease_seconds
            return {"revision": saved, "backup": backup.name, "saved": True}
