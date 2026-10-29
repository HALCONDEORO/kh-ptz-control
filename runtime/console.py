#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/console.py — Locale-independent console output for the khptz CLI (#884)
#
# The Raspberry Pi OS Bullseye desktop terminal may run under a non-UTF-8 locale
# (LANG=C / ANSI_X3.4-1968), and Windows consoles default to cp1252. CLI output
# contains typographic characters such as the em dash, so printing crashed with:
#
#   UnicodeEncodeError: 'charmap' codec can't encode character '—'
#
# That aborted `khptz setup` and truncated `khptz doctor` mid-run on a real
# install. Console encoding is a presentation concern and must never determine
# whether a command succeeds.
#
# Call configure_console_encoding() once, first thing in main().

from __future__ import annotations

import os
import sys
from pathlib import Path

# Characters we emit that are absent from legacy 8-bit codecs, and the plain
# ASCII fallback used when the stream genuinely cannot carry them.
_ASCII_FALLBACKS = {
    "—": "--",   # em dash
    "–": "-",    # en dash
    "‘": "'",    # left single quote
    "’": "'",    # right single quote
    "“": '"',    # left double quote
    "”": '"',    # right double quote
    "…": "...",  # ellipsis
    "→": "->",   # rightwards arrow
    "✓": "OK",   # check mark
    "✗": "X",    # ballot X
    "·": "*",    # middle dot
}


def configure_console_encoding() -> bool:
    """Make stdout/stderr tolerant of non-ASCII output. Never raises.

    Returns True if both streams are known to carry UTF-8 afterwards.

    Prefers reconfiguring the stream to UTF-8, which keeps the intended
    typography on the many terminals that render UTF-8 regardless of the
    declared locale. If that is not possible (stream already replaced, or a
    codec that cannot be switched), falls back to errors="replace" so output is
    degraded rather than fatal.
    """
    ok = True
    for stream in (sys.stdout, sys.stderr):
        if not _reconfigure(stream):
            ok = False
    return ok


def _reconfigure(stream) -> bool:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        # Not a TextIOWrapper (pytest capture, a StringIO, a pipe wrapper).
        # Nothing to do; safe_text() still protects individual writes.
        return _encoding_is_utf8(stream)
    try:
        reconfigure(encoding="utf-8", errors="replace")
        return True
    except Exception:
        pass
    try:
        # Keep the terminal's own encoding but stop it raising.
        reconfigure(errors="replace")
    except Exception:
        pass
    return _encoding_is_utf8(stream)


def _encoding_is_utf8(stream) -> bool:
    encoding = getattr(stream, "encoding", None) or ""
    return encoding.lower().replace("_", "-") in ("utf-8", "utf8")


def safe_text(text: str, stream=None) -> str:
    """Return *text* rendered so it can be written to *stream* without raising.

    Used for output that must survive a stream we could not reconfigure. If the
    target encoding can carry the text unchanged it is returned as-is, so the
    common UTF-8 case keeps its typography.
    """
    if stream is None:
        stream = sys.stdout
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return text
    try:
        text.encode(encoding)
        return text
    except (UnicodeEncodeError, LookupError):
        pass
    for fancy, plain in _ASCII_FALLBACKS.items():
        text = text.replace(fancy, plain)
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = text.encode("ascii", errors="replace").decode("ascii")
    return text


def safe_print(*args, **kwargs) -> None:
    """print() that degrades unencodable characters instead of raising."""
    stream = kwargs.get("file") or sys.stdout
    sep = kwargs.get("sep", " ")
    rendered = sep.join(safe_text(str(a), stream) for a in args)
    try:
        print(rendered, **kwargs)
    except UnicodeEncodeError:
        # Last resort: the stream lied about what it can encode.
        ascii_only = rendered.encode("ascii", errors="replace").decode("ascii")
        print(ascii_only, **kwargs)


def user_state_dir() -> Path:
    """Per-user writable state directory, for CLI runs that are not the service.

    Interactive commands (`khptz setup`, `khptz demo`) and any command run by the
    desktop user must not need write access to service-owned production paths
    such as /var/log/khptz (#884).
    """
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "khptz"
    return Path.home() / ".local" / "state" / "khptz"


def writable_log_dir(preferred: Path | None) -> Path | None:
    """Return *preferred* if we can write there, otherwise a user-owned fallback.

    Returns None if neither is usable, which callers must treat as
    console-only logging rather than an error.
    """
    for candidate in (preferred, user_state_dir() / "logs"):
        if candidate is None:
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".khptz-write-test"
            probe.touch()
            probe.unlink()
            return candidate
        except OSError:
            continue
    return None
