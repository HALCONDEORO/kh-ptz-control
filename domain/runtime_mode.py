#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/runtime_mode.py — Runtime mode constants and helpers
#
# Three distinct modes, each with a different audience and risk profile:
#   production  — real customer hardware, real data, full VISCA/ATEM
#   demo        — sales/training, isolated data dir, fake adapters by default
#   simulation  — developer testing, may use fake adapters

from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):
    PRODUCTION = "production"
    DEMO       = "demo"
    SIMULATION = "simulation"


_VALID = {m.value for m in RuntimeMode}


def parse_mode(value: str) -> RuntimeMode:
    """Parse a string into RuntimeMode. Raises ValueError for unknown values."""
    if value not in _VALID:
        raise ValueError(
            f"Unknown runtime mode: {value!r}. "
            f"Valid values: {', '.join(sorted(_VALID))}"
        )
    return RuntimeMode(value)
