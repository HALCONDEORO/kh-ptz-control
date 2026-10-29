#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""application/provision_handoff.py — the wizard side of the provisioning channel.

The setup wizard runs unprivileged in the desktop session; the OS-mutating work
(write /etc/khptz, install + enable the systemd service) runs as root in
runtime/provision.py. They never share a process. This module is the bridge the
wizard uses: it drops a request file the privileged ``khptz-provision`` path-unit
reacts to, then polls for the result file that unit writes back.

It is deliberately Qt-free and path-agnostic — the request/result paths are
injected — so it can be unit-tested without a screen, a Pi or systemd, and so the
UI layer only ever calls a service (it never persists JSON itself).

Split for a non-blocking GUI:
  - begin()  writes the request and arms the deadline (one shot).
  - poll()   returns None until the result lands or the deadline passes.
  - submit() = begin() + a blocking poll loop, for headless/CLI use and tests.

Security note: the request carries both plaintext passwords. In production the
request path is on tmpfs (/run/khptz) and the privileged side shreds it after
applying; this module writes it 0600 so it is never world-readable even briefly.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from core.atomic_write import write_text_atomic

from application.provisioning_service import ProvisioningAnswers


@dataclass(frozen=True)
class HandoffResult:
    """Outcome of a provisioning request, as seen by the wizard.

    ``ok`` mirrors the privileged side's result. ``issues`` carries validation
    problems (field/message) when the answers were rejected; ``error`` carries an
    unexpected failure; ``timed_out`` means no result appeared before the
    deadline (the wizard should let the operator retry).
    """
    ok: bool
    timed_out: bool = False
    error: str = ""
    issues: List[dict] = field(default_factory=list)
    written: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line human summary for the Installing/Done screens."""
        if self.ok:
            return "Setup complete — the room is installed and the service is enabled."
        if self.timed_out:
            return "Setup did not finish in time. Check the device and try again."
        if self.issues:
            joined = "; ".join(i.get("message", "") for i in self.issues)
            return f"Setup could not start: {joined}"
        return f"Setup failed: {self.error or 'unknown error'}"


def build_request_payload(answers: ProvisioningAnswers) -> dict:
    """Serialise answers (incl. plaintext passwords) for the privileged side.

    This is the exact shape ``runtime.provision.answers_from_dict`` parses.
    """
    return asdict(answers)


class ProvisionHandoff:
    """Drops a provisioning request and waits for the privileged side's result."""

    def __init__(
        self,
        request_path: Path,
        result_path: Path,
        *,
        timeout_s: float = 120.0,
        poll_interval_s: float = 0.5,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._request_path = Path(request_path)
        self._result_path = Path(result_path)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._monotonic = monotonic
        self._sleep = sleep
        self._deadline: Optional[float] = None

    @property
    def poll_interval_s(self) -> float:
        return self._poll_interval_s

    def begin(self, answers: ProvisioningAnswers) -> None:
        """Write the request (0600) and arm the deadline. Clears any stale result.

        Idempotent enough to retry: a fresh begin() overwrites the request and
        removes a leftover result so poll() does not read a previous run's answer.
        """
        try:
            self._result_path.unlink()
        except FileNotFoundError:
            pass
        self._request_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(build_request_payload(answers))
        write_text_atomic(self._request_path, payload, mode=0o600)
        self._deadline = self._monotonic() + self._timeout_s

    def poll(self) -> Optional[HandoffResult]:
        """Return the result once available, a timed-out result past the deadline,
        or None while still waiting. Safe to call repeatedly from a Qt timer."""
        if self._result_path.exists():
            return self._read_result()
        if self._deadline is not None and self._monotonic() >= self._deadline:
            return HandoffResult(ok=False, timed_out=True)
        return None

    def submit(self, answers: ProvisioningAnswers) -> HandoffResult:
        """Blocking begin()+poll loop. For headless/CLI use and tests.

        The injected ``sleep`` is the hook tests use to satisfy the request (e.g.
        write the result file) between polls without real wall-clock waiting.
        """
        self.begin(answers)
        while True:
            result = self.poll()
            if result is not None:
                return result
            self._sleep(self._poll_interval_s)

    def _read_result(self) -> HandoffResult:
        try:
            data = json.loads(self._result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return HandoffResult(ok=False, error=f"unreadable result: {exc}")
        if data.get("ok"):
            return HandoffResult(ok=True, written=list(data.get("written", [])))
        return HandoffResult(
            ok=False,
            error=str(data.get("error", "")),
            issues=list(data.get("issues", [])),
        )
