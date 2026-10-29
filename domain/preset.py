#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/preset.py — Modelos y constantes del dominio de presets

PRESET_SLOT_MIN = 10   # primer slot reservado para chairman personal
PRESET_SLOT_MAX = 89   # último slot seguro (0x59 hex)

# Presets de plataforma fija (no cambian por persona)
PRESET_CHAIRMAN_GENERIC = 1
PRESET_LEFT             = 2
PRESET_RIGHT            = 3
PRESET_PLATFORM_2       = 132  # segunda plataforma opcional (feature flag)

PLATFORM_PRESETS = frozenset(
    {PRESET_CHAIRMAN_GENERIC, PRESET_LEFT, PRESET_RIGHT, PRESET_PLATFORM_2}
)

