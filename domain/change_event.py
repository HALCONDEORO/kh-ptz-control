#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/change_event.py — Config change history event model
#
# ChangeEvent records a single significant change to config, layout or presets.
# Events are written to change_history.json by ChangeHistoryService.
# No I/O, no Qt, pure data model.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Known area labels — use these when recording events
AREA_CONFIG  = "config"
AREA_LAYOUT  = "layout"
AREA_PRESETS = "presets"
AREA_BACKUP  = "backup"
AREA_SYSTEM  = "system"

# Known action labels — not exhaustive, callers may add domain-specific ones
ACTION_CAMERA_IP_CHANGED      = "camera_ip_changed"
ACTION_CAMERA_VISCA_CHANGED   = "camera_visca_id_changed"
ACTION_ATEM_IP_CHANGED        = "atem_ip_changed"
ACTION_PROFILE_CHANGED        = "installation_profile_changed"
ACTION_CONNECTIVITY_CHANGED   = "connectivity_mode_changed"
ACTION_INSTALLATION_ID_CHANGED = "installation_id_changed"
ACTION_LAYOUT_CHANGED         = "layout_changed"
ACTION_PRESET_OVERWRITTEN     = "preset_overwritten"
ACTION_BACKUP_RESTORED        = "backup_restored"
ACTION_CONFIG_MIGRATED        = "config_migrated_from_legacy"


@dataclass
class ChangeEvent:
    """A single recorded configuration/layout/preset change."""
    area: str               # AREA_* constant or free-form label
    action: str             # ACTION_* constant or free-form label
    target: str             # e.g. "camera:comments", "layout:room_a", "preset:7"
    timestamp: str = field(default_factory=lambda: _now_iso())
    actor: str = "system"   # "installer", "operator", "restore", "migration", …
    old_value: str | None = None   # sanitised — never passwords or personal data
    new_value: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "actor":     self.actor,
            "area":      self.area,
            "action":    self.action,
            "target":    self.target,
        }
        if self.old_value is not None:
            d["old_value"] = self.old_value
        if self.new_value is not None:
            d["new_value"] = self.new_value
        if self.note:
            d["note"] = self.note
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChangeEvent":
        return cls(
            area=data.get("area", ""),
            action=data.get("action", ""),
            target=data.get("target", ""),
            timestamp=data.get("timestamp", _now_iso()),
            actor=data.get("actor", "system"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            note=data.get("note", ""),
        )

    @classmethod
    def from_json(cls, raw: str) -> "ChangeEvent":
        return cls.from_dict(json.loads(raw))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
