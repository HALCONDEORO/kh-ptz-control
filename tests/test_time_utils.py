#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# tests/test_time_utils.py — Contract for the canonical UTC timestamp helpers.
"""Locks the timestamp format so log/event/incident/bundle records cannot drift apart again."""

import re
from datetime import datetime

from domain.time_utils import utc_now_compact, utc_now_iso


def test_utc_now_iso_has_millis_and_z_suffix():
    ts = utc_now_iso()
    assert ts.endswith("Z")
    # YYYY-MM-DDTHH:MM:SS.mmm Z  (exactly 3 millisecond digits)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts), ts


def test_utc_now_iso_is_parseable():
    ts = utc_now_iso()
    # Must round-trip through fromisoformat once the Z is normalised.
    datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_utc_now_compact_is_filename_safe():
    stamp = utc_now_compact()
    assert re.fullmatch(r"\d{8}-\d{6}", stamp), stamp
    # No separators that are illegal in filenames.
    assert ":" not in stamp and "/" not in stamp
