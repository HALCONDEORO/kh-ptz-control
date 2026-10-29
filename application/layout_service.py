#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/layout_service.py — LayoutService: load, save and query room layout
#
# Responsibilities:
#   - Load room_layout.json from the persistent data directory.
#   - Run schema migration when a supported older version is found.
#   - Reject layouts with an unsupported future schema version.
#   - Validate layout before saving (no duplicate IDs, non-empty IDs).
#   - On corrupt/unreadable file: try .bak, then regenerate from legacy.
#   - Save using atomic JSON write (json_io.save_json).
#   - Generate a default layout from legacy SEAT_POSITIONS if no file exists.
#   - Expose helpers: visible_seats(), seat_by_id(), update_seat_position().
#
# No Qt, no network I/O.

from __future__ import annotations

import json
import logging
from pathlib import Path

from domain.room_layout import RoomLayout, SeatLayout, SCHEMA_VERSION
from domain.layout_scaling import offscreen_seats

logger = logging.getLogger(__name__)

_UNSET = object()

_DEFAULT_ROOM_ID     = "default"
_DEFAULT_ROOM_NAME   = "Main Chamber"
_DEFAULT_SCREEN_W    = 1440
_DEFAULT_SCREEN_H    = 1080
_DEFAULT_CAMERA_ROLE = "platform"

# Schema versions this code can read (current and any older supported versions).
_SUPPORTED_VERSIONS = frozenset({1})


class LayoutError(ValueError):
    """Raised when a layout file cannot be loaded or is invalid."""


class LayoutValidationError(LayoutError):
    """Raised when a layout fails pre-save validation."""


class LayoutService:
    """
    Loads and persists the room layout.

    Recovery order on corrupt primary file:
      1. Try loading ``room_layout.json``.
      2. If corrupt, try loading ``room_layout.json.bak``.
      3. If that also fails (or does not exist), regenerate from legacy/default.

    Parameters
    ----------
    layout_path:
        Path to room_layout.json.  Defaults to the data_paths constant.
    legacy_positions:
        Dict mapping seat number (int) → (x, y) used to generate the
        default layout when no file exists.  Pass None to skip legacy
        generation (results in an empty layout).
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def __init__(
        self,
        layout_path: Path | None = None,
        legacy_positions=_UNSET,
    ) -> None:
        if layout_path is None:
            from runtime.path_resolver import RuntimePathResolver
            layout_path = RuntimePathResolver().room_layout_file
        self._path = Path(layout_path)

        if legacy_positions is _UNSET:
            try:
                from config import SEAT_POSITIONS
                self._legacy = SEAT_POSITIONS
            except ImportError:
                self._legacy = {}
        else:
            self._legacy = legacy_positions or {}

        self._layout: RoomLayout | None = None
        self._recovery_used: bool = False

    def load(self) -> RoomLayout:
        """
        Load layout from file with automatic migration and safe recovery.

        Returns the loaded (or generated) layout.
        Sets ``recovery_used`` if .bak or default regeneration was needed.
        """
        self._recovery_used = False

        if not self._path.exists():
            logger.info("room_layout.json not found — generating default layout")
            layout = self._generate_default()
            self.save(layout)
            self._layout = layout
            return layout

        layout = self._try_load_file(self._path)
        if layout is not None:
            self._layout = layout
            return layout

        # Primary file failed — try .bak
        bak = self._path.with_suffix(".bak")
        if bak.exists():
            logger.warning("room_layout.json corrupt — attempting recovery from .bak")
            layout = self._try_load_file(bak)
            if layout is not None:
                logger.warning("Recovered from .bak — re-saving as primary file")
                self._recovery_used = True
                self.save(layout)
                self._layout = layout
                return layout

        # Both files unusable — regenerate
        logger.warning("room_layout.json and .bak both unusable — regenerating default layout")
        self._recovery_used = True
        layout = self._generate_default()
        self.save(layout)
        self._layout = layout
        return layout

    @property
    def recovery_used(self) -> bool:
        """True if the last load() fell back to .bak or default regeneration."""
        return self._recovery_used

    def save(self, layout: RoomLayout) -> bool:
        """Validate and persist layout atomically. Returns True on success."""
        self._validate(layout)
        from core.json_io import save_json
        data = self._serialize(layout)
        ok = save_json(self._path, data)
        if ok:
            self._layout = layout
        return ok

    @property
    def layout(self) -> RoomLayout | None:
        return self._layout

    def visible_seats(self) -> list[SeatLayout]:
        if self._layout is None:
            raise LayoutError("Layout not loaded — call load() first")
        return self._layout.visible_seats()

    def seat_by_id(self, seat_id: str) -> SeatLayout | None:
        if self._layout is None:
            raise LayoutError("Layout not loaded — call load() first")
        return self._layout.seat_by_id(seat_id)

    def offscreen_seat_ids(self) -> list[str]:
        """Return IDs of seats that fall outside the canonical boundary by more than the margin."""
        if self._layout is None:
            raise LayoutError("Layout not loaded — call load() first")
        return offscreen_seats(self._layout)

    def update_seat_position(self, seat_id: str, x: int, y: int) -> bool:
        """Update one seat's position in memory and persist. Returns False if seat not found."""
        if self._layout is None:
            raise LayoutError("Layout not loaded — call load() first")
        seat = self._layout.seat_by_id(seat_id)
        if seat is None:
            return False
        for i, s in enumerate(self._layout.seats):
            if s.id == seat_id:
                self._layout.seats[i] = SeatLayout(
                    id=s.id, label=s.label, preset=s.preset,
                    camera_role=s.camera_role, x=x, y=y,
                    row=s.row, column=s.column, type=s.type,
                    visible=s.visible, locked=s.locked, calibrated=s.calibrated,
                )
                self.save(self._layout)
                return True
        return False

    # ── Internal: load pipeline ───────────────────────────────────────────────

    def _try_load_file(self, path: Path) -> RoomLayout | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            logger.exception("Cannot read %s: %s", path.name, exc)
            return None

        try:
            return self._deserialize_with_migration(raw)
        except LayoutError as exc:
            logger.exception("Invalid layout in %s: %s", path.name, exc)
            return None

    def _deserialize_with_migration(self, raw: dict) -> RoomLayout:
        if not isinstance(raw, dict):
            raise LayoutError("room_layout.json must be a JSON object")

        version = raw.get("schema_version", 1)
        try:
            version = int(version)
        except (TypeError, ValueError) as exc:
            raise LayoutError(f"Invalid schema_version: {version!r}") from exc

        if version > SCHEMA_VERSION:
            raise LayoutError(
                f"Unsupported schema version {version} "
                f"(this version of HALLPTZ supports up to {SCHEMA_VERSION}). "
                "Upgrade Hall PTZ Control to read this layout."
            )
        if version not in _SUPPORTED_VERSIONS:
            raise LayoutError(f"Unknown schema version {version}")

        # Apply migrations in order (v1 is current — no migrations needed yet)
        migrated = raw
        if version < SCHEMA_VERSION:
            migrated = self._migrate(migrated, from_version=version)
            logger.info(
                "Migrated room_layout.json from schema v%d to v%d",
                version, SCHEMA_VERSION,
            )

        return self._deserialize(migrated)

    @staticmethod
    def _migrate(raw: dict, from_version: int) -> dict:
        """Apply schema migrations in order.  Add new steps as the schema evolves."""
        result = dict(raw)
        # Placeholder: when v2 is introduced, add:
        #   if from_version < 2:
        #       result = _migrate_v1_to_v2(result)
        result["schema_version"] = SCHEMA_VERSION
        return result

    # ── Internal: validation ──────────────────────────────────────────────────

    @staticmethod
    def _validate(layout: RoomLayout) -> None:
        seen_ids: set[str] = set()
        for seat in layout.seats:
            if not seat.id:
                raise LayoutValidationError("Seat has empty id — each seat must have a unique non-empty id")
            if seat.id in seen_ids:
                raise LayoutValidationError(f"Duplicate seat id: {seat.id!r}")
            seen_ids.add(seat.id)

    # ── Internal: default generation ──────────────────────────────────────────

    def _generate_default(self) -> RoomLayout:
        seats: list[SeatLayout] = []
        for number, (x, y) in sorted(self._legacy.items()):
            seats.append(SeatLayout(
                id=str(number),
                label=str(number),
                preset=number,
                camera_role=_DEFAULT_CAMERA_ROLE,
                x=x,
                y=y,
            ))
        return RoomLayout(
            schema_version=SCHEMA_VERSION,
            room_id=_DEFAULT_ROOM_ID,
            room_name=_DEFAULT_ROOM_NAME,
            screen_width=_DEFAULT_SCREEN_W,
            screen_height=_DEFAULT_SCREEN_H,
            seats=seats,
        )

    # ── Internal: serialization ───────────────────────────────────────────────

    @staticmethod
    def _serialize(layout: RoomLayout) -> dict:
        return {
            "schema_version": layout.schema_version,
            "room_id": layout.room_id,
            "room_name": layout.room_name,
            "screen_width": layout.screen_width,
            "screen_height": layout.screen_height,
            "seats": [
                {
                    "id": s.id,
                    "label": s.label,
                    "preset": s.preset,
                    "camera_role": s.camera_role,
                    "x": s.x,
                    "y": s.y,
                    "row": s.row,
                    "column": s.column,
                    "type": s.type,
                    "visible": s.visible,
                    "locked": s.locked,
                    "calibrated": s.calibrated,
                }
                for s in layout.seats
            ],
        }

    @staticmethod
    def _deserialize(raw: dict) -> RoomLayout:
        seats: list[SeatLayout] = []
        for item in raw.get("seats", []):
            if not isinstance(item, dict):
                raise LayoutError("Each seat must be a JSON object")
            seats.append(SeatLayout(
                id=str(item.get("id", "")),
                label=str(item.get("label", "")),
                preset=int(item.get("preset", 0)),
                camera_role=str(item.get("camera_role", _DEFAULT_CAMERA_ROLE)),
                x=int(item.get("x", 0)),
                y=int(item.get("y", 0)),
                row=item.get("row"),
                column=item.get("column"),
                type=str(item.get("type", "delegate")),
                visible=bool(item.get("visible", True)),
                locked=bool(item.get("locked", False)),
                calibrated=bool(item.get("calibrated", False)),
            ))

        return RoomLayout(
            schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
            room_id=str(raw.get("room_id", _DEFAULT_ROOM_ID)),
            room_name=str(raw.get("room_name", _DEFAULT_ROOM_NAME)),
            screen_width=int(raw.get("screen_width", _DEFAULT_SCREEN_W)),
            screen_height=int(raw.get("screen_height", _DEFAULT_SCREEN_H)),
            seats=seats,
        )
