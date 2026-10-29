#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/atem_constants.py — Canonical ATEM input label definitions
#
# Single source of truth for human-readable ATEM input labels.
# Used by DemoAtemPanel, AtemAdminPanel, and any future UI that references inputs.

from __future__ import annotations

# Ordered mapping: input_id → display label.
# Key: 1-based integer matching the ATEM input bus numbering.
ATEM_INPUT_LABELS: dict[int, str] = {
    1: "PC",
    2: "Platform",
    3: "Comments",
    4: "None",
}

# Ordered list of (input_id, label) — for UI button rows that need a stable order.
ATEM_INPUT_LABELS_LIST: list[tuple[int, str]] = sorted(ATEM_INPUT_LABELS.items())

# Default ATEM action mapping — single source of truth for the dispatcher default.
# Key format: "A->B" (transition) or "N" (entry), value: action name.
ATEM_DEFAULT_MAPPING: dict[str, str] = {"3->2": "comments_home"}
