#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# application/preset_sources.py — Build PresetTestItem lists from configured data.
#
# Replaceable by layout-editor-derived sources in future without touching the runner.
#
# Verification key convention: "{seat_id}:{camera_role}"
# e.g. "seat_004:comments", "seat_001:main"
# Matches what PresetVerificationService.mark() expects from installer tools.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from application.preset_test_models import PresetTestItem

logger = logging.getLogger(__name__)


def build_items_from_config(
    verifications_path: Optional[Path] = None,
) -> list[PresetTestItem]:
    """
    Builds one PresetTestItem per entry in SEAT_POSITIONS.

    Routing matches _resolve_preset: presets 1-3 → CAM1 (main),
    all others → CAM2 (comments). All SEAT_POSITIONS seats are >= 4,
    so they all route to the comments camera.

    Items whose preset number is missing from PRESET_MAP are returned
    with enabled=False so the runner marks them SKIPPED without crashing.

    has_verified_ptz is populated from PresetVerificationService when a record
    with key "{seat_id}:{camera_role}" exists and its status is OK; None otherwise.
    """
    from config import SEAT_POSITIONS, PRESET_MAP
    from application.preset_verification_service import PresetVerificationService

    verifications = PresetVerificationService(verifications_path).load_all()

    items: list[PresetTestItem] = []
    for seat_number in sorted(SEAT_POSITIONS):
        in_map = seat_number in PRESET_MAP
        camera_role = "main" if seat_number <= 3 else "comments"
        camera_index = 1 if seat_number <= 3 else 2
        seat_id = f"seat_{seat_number:03d}"
        v = verifications.get(f"{seat_id}:{camera_role}")
        items.append(PresetTestItem(
            item_id=seat_id,
            label=str(seat_number),
            camera_role=camera_role,
            camera_index=camera_index,
            preset=seat_number if in_map else None,
            enabled=in_map,
            has_verified_ptz=v.is_verified if v is not None else None,
        ))
    return items


def build_items_from_assigned_names(
    verifications_path: Optional[Path] = None,
) -> list[PresetTestItem]:
    """
    Builds one PresetTestItem per seat that currently has a non-empty assigned name.

    Uses load_names_data()["seats"] as the authoritative source.  Empty/whitespace
    names and non-numeric seat keys are silently skipped so invalid assignment data
    cannot crash the test panel.

    Items whose preset number is missing from PRESET_MAP are returned with
    enabled=False so the runner marks them SKIPPED without sending a command.

    has_verified_ptz is populated from PresetVerificationService when a record
    with key "{seat_id}:{camera_role}" exists and its status is OK; None otherwise.
    """
    from config import PRESET_MAP, load_names_data
    from application.preset_verification_service import PresetVerificationService

    data = load_names_data()
    seat_assignments: dict = data.get("seats", {})
    verifications = PresetVerificationService(verifications_path).load_all()

    named_seats: list[tuple[int, str]] = []
    for raw_key, name in seat_assignments.items():
        if not isinstance(name, str) or not name.strip():
            continue
        try:
            seat_number = int(raw_key)
        except (ValueError, TypeError):
            logger.warning("preset_sources: invalid seat key %r — skipped", raw_key)
            continue
        named_seats.append((seat_number, name.strip()))

    items: list[PresetTestItem] = []
    for seat_number, name in sorted(named_seats):
        in_map = seat_number in PRESET_MAP
        camera_role = "main" if seat_number <= 3 else "comments"
        camera_index = 1 if seat_number <= 3 else 2
        seat_id = f"seat_{seat_number:03d}"
        v = verifications.get(f"{seat_id}:{camera_role}")
        items.append(PresetTestItem(
            item_id=seat_id,
            label=str(seat_number),
            camera_role=camera_role,
            camera_index=camera_index,
            preset=seat_number if in_map else None,
            enabled=in_map,
            assigned_name=name,
            has_verified_ptz=v.is_verified if v is not None else None,
        ))
    return items
