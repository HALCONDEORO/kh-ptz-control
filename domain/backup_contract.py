#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/backup_contract.py — the one definition of what a backup contains.
#
# Pure domain module — no I/O, no Qt, no path resolution.
#
# WHY THIS EXISTS
# BackupService decided what to put in the ZIP and RestoreService kept its own
# allow-list of what it would accept out of one. They drifted: backup started
# including preset_brightness.json, restore never learned about it, and because
# restore treats an unlisted member as a tampering signal it aborted the WHOLE
# archive — config.yaml, presets, layout and all. Any appliance where an
# operator had adjusted preset brightness could no longer be recovered from its
# own backup, and the failure only appeared during a recovery, which is the
# worst possible moment to discover it.
#
# Two lists that must agree are one list. Adding a file here adds it to both
# sides at once; there is no way to add it to only one.

from __future__ import annotations

from typing import Final, FrozenSet, Tuple

#: The site configuration file. Lives in config_dir, not data_dir, so both
#: services special-case its destination — it is named here so the archive
#: member name itself has a single definition.
CONFIG_ARCHIVE_NAME: Final[str] = "config.yaml"

#: Customer/runtime data files, in archive order. Every entry resolves against
#: data_dir on both the backup and the restore side.
#:
#: Order is stable and meaningful: it is the order files appear in the ZIP and
#: in `hallptz backup` output, so a changed order shows up as a diff in review
#: rather than as silent churn in customer-visible output.
DATA_ARCHIVE_NAMES: Final[Tuple[str, ...]] = (
    "chairman_presets.json",
    "seat_names.json",
    "schedule.json",
    "room_layout.json",
    "change_history.json",
    "preset_brightness.json",
    # Moved out of /etc/hallptz, which the service cannot write (see
    # adapters/atem_dispatcher.py). It is customer configuration of installed
    # hardware, so a restore that omitted it would silently drop the ATEM
    # action mapping and the PiP-automation setting.
    "atem_mapping.json",
)

#: Every archive member a valid backup may contain, including the manifest.
#: RestoreService rejects anything outside this set — an unexpected path in an
#: archive is treated as tampering, not as a new feature.
MANIFEST_ARCHIVE_NAME: Final[str] = "manifest.json"

RESTORABLE_ARCHIVE_NAMES: Final[FrozenSet[str]] = frozenset(
    (CONFIG_ARCHIVE_NAME,) + DATA_ARCHIVE_NAMES
)


def is_restorable(archive_name: str) -> bool:
    """True when *archive_name* is a member a backup is allowed to carry."""
    return archive_name in RESTORABLE_ARCHIVE_NAMES
