#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/maintenance_service.py — MaintenanceService and InstallabilityService.
#
# MaintenanceStatus persistence, overdue detection, and installability risk scoring.
# Does not enforce payment or licence by itself.
#
# See docs/RUNTIME_PATH_CONTRACT.md.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domain.supportability import MaintenanceResult

logger = logging.getLogger(__name__)

# Default maintenance cycle: 30 days
_DEFAULT_CYCLE_DAYS = 30


# ── MaintenanceRecord ─────────────────────────────────────────────────────────

@dataclass
class MaintenanceRecord:
    """Persisted maintenance completion entry."""
    completed_at: str       # ISO-8601 UTC
    completed_by: str = "unknown"
    notes: str = ""
    result: str = MaintenanceResult.PASSED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_at": self.completed_at,
            "completed_by": self.completed_by,
            "notes": self.notes,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MaintenanceRecord:
        return cls(
            completed_at=data.get("completed_at", "unknown"),
            completed_by=data.get("completed_by", "unknown"),
            notes=data.get("notes", ""),
            result=data.get("result", MaintenanceResult.UNKNOWN.value),
        )


# ── MaintenanceStatusResult ───────────────────────────────────────────────────

@dataclass
class MaintenanceStatusResult:
    """Human/JSON result of a maintenance status query."""
    support_plan: str = "monthly"
    last_completed_at: str | None = None
    last_result: MaintenanceResult = MaintenanceResult.UNKNOWN
    next_due: str | None = None
    overdue: bool = False
    overdue_days: int = 0
    completed_by: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "support_plan": self.support_plan,
            "last_completed_at": self.last_completed_at,
            "last_result": self.last_result.value,
            "next_due": self.next_due,
            "overdue": self.overdue,
            "overdue_days": self.overdue_days,
            "completed_by": self.completed_by,
        }

    def human_summary(self) -> list[str]:
        lines = [f"  Support plan:      {self.support_plan}"]
        if self.last_completed_at:
            lines.append(f"  Last completed:    {self.last_completed_at}")
            lines.append(f"  Completed by:      {self.completed_by}")
            lines.append(f"  Last result:       {self.last_result.value}")
        else:
            lines.append("  Last completed:    never")
        if self.next_due:
            lines.append(f"  Next due:          {self.next_due}")
        if self.overdue:
            lines.append(f"  Status:            OVERDUE ({self.overdue_days} day(s))")
        else:
            lines.append("  Status:            current")
        return lines


# ── InstallabilityResult ──────────────────────────────────────────────────────

@dataclass
class InstallabilityResult:
    """Result of an installability profile assessment."""
    wired_network_available: bool | None = None
    static_ips_possible: bool | None = None
    customer_it_required: bool = False
    atem_present: bool = False
    unsupported_hardware: bool = False
    risk_score: int = 0
    estimated_install_hours: str = "unknown"
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wired_network_available": self.wired_network_available,
            "static_ips_possible": self.static_ips_possible,
            "customer_it_required": self.customer_it_required,
            "atem_present": self.atem_present,
            "unsupported_hardware": self.unsupported_hardware,
            "risk_score": self.risk_score,
            "estimated_install_hours": self.estimated_install_hours,
            "risk_flags": self.risk_flags,
        }

    def human_summary(self) -> list[str]:
        lines = [
            f"  Risk score:        {self.risk_score}",
            f"  Est. install time: {self.estimated_install_hours}",
            f"  ATEM present:      {'yes' if self.atem_present else 'no'}",
            f"  IT required:       {'yes' if self.customer_it_required else 'no'}",
        ]
        if self.risk_flags:
            lines.append("  Risk flags:")
            for flag in self.risk_flags:
                lines.append(f"    - {flag}")
        else:
            lines.append("  Risk flags:        none")
        return lines


# ── MaintenanceService ────────────────────────────────────────────────────────

class MaintenanceService:
    """
    Persist maintenance completion records and compute due/overdue state.

    Storage: <data_dir>/maintenance.json
    Does not enforce payment or licence by itself.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            data_dir = RuntimePathResolver().data_dir
        self._data_dir = data_dir
        self._state_file = data_dir / "maintenance.json"

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self, cycle_days: int = _DEFAULT_CYCLE_DAYS) -> MaintenanceStatusResult:
        """Return the current maintenance status."""
        record = self._load()
        now = datetime.now(timezone.utc)

        if record is None:
            return MaintenanceStatusResult(
                last_completed_at=None,
                overdue=True,
                overdue_days=0,
                next_due=None,
            )

        try:
            last_dt = datetime.fromisoformat(record.completed_at)
            from datetime import timedelta
            next_dt = last_dt + timedelta(days=cycle_days)
            overdue = now > next_dt
            overdue_days = max(0, (now - next_dt).days) if overdue else 0
            return MaintenanceStatusResult(
                last_completed_at=record.completed_at,
                last_result=MaintenanceResult(record.result)
                if record.result in {m.value for m in MaintenanceResult}
                else MaintenanceResult.UNKNOWN,
                next_due=next_dt.isoformat(timespec="seconds"),
                overdue=overdue,
                overdue_days=overdue_days,
                completed_by=record.completed_by,
            )
        except Exception as exc:
            logger.warning("Could not parse maintenance record: %s", exc)
            return MaintenanceStatusResult(overdue=True)

    # ── Mark complete ─────────────────────────────────────────────────────────

    def mark_complete(
        self,
        *,
        completed_by: str = "operator",
        notes: str = "",
        result: MaintenanceResult = MaintenanceResult.PASSED,
    ) -> MaintenanceRecord:
        """Record a maintenance completion at the current UTC time."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = MaintenanceRecord(
            completed_at=now,
            completed_by=completed_by,
            notes=notes,
            result=result.value,
        )
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(record.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.exception("Could not write maintenance record: %s", exc)
        return record

    # ── Private ───────────────────────────────────────────────────────────────

    def _load(self) -> MaintenanceRecord | None:
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return MaintenanceRecord.from_dict(data)
        except Exception as exc:
            logger.warning("Could not read maintenance file: %s", exc)
            return None


# ── InstallabilityService ─────────────────────────────────────────────────────

# Risk score table
_RISK_WEIGHTS = {
    "no_wired_network": 3,
    "no_static_ips": 2,
    "customer_it_required": 2,
    "atem_present": 1,
    "unsupported_hardware": 5,
}

_INSTALL_HOURS_BANDS = [
    (0, "unknown"),
    (1, "1–2 h"),
    (3, "2–3 h"),
    (6, "3–5 h"),
    (10, "5–8 h"),
]


def _install_hours(score: int) -> str:
    result = "8+ h"
    for threshold, label in _INSTALL_HOURS_BANDS:
        if score <= threshold:
            result = label
            break
    return result


class InstallabilityService:
    """
    Assess the installation risk profile from config-driven flags.

    Risk score and install hours estimate are deterministic from the input flags.
    Does not perform network probing or hardware detection by itself.
    """

    def assess(
        self,
        *,
        wired_network_available: bool | None = None,
        static_ips_possible: bool | None = None,
        customer_it_required: bool = False,
        atem_present: bool = False,
        unsupported_hardware: bool = False,
        extra_risk_flags: list[str] | None = None,
    ) -> InstallabilityResult:
        """
        Compute a deterministic installability risk profile.

        Parameters reflect site survey answers — pass None for unknown.
        """
        risk_score = 0
        risk_flags: list[str] = list(extra_risk_flags or [])

        if wired_network_available is False:
            risk_score += _RISK_WEIGHTS["no_wired_network"]
            risk_flags.append("No wired network available")

        if static_ips_possible is False:
            risk_score += _RISK_WEIGHTS["no_static_ips"]
            risk_flags.append("Static IP assignment not possible")

        if customer_it_required:
            risk_score += _RISK_WEIGHTS["customer_it_required"]
            risk_flags.append("Customer IT involvement required")

        if atem_present:
            risk_score += _RISK_WEIGHTS["atem_present"]
            risk_flags.append("ATEM switcher integration required")

        if unsupported_hardware:
            risk_score += _RISK_WEIGHTS["unsupported_hardware"]
            risk_flags.append("Unsupported hardware detected")

        if wired_network_available is None:
            risk_flags.append("Wired network availability unknown")

        if static_ips_possible is None:
            risk_flags.append("Static IP availability unknown")

        return InstallabilityResult(
            wired_network_available=wired_network_available,
            static_ips_possible=static_ips_possible,
            customer_it_required=customer_it_required,
            atem_present=atem_present,
            unsupported_hardware=unsupported_hardware,
            risk_score=risk_score,
            estimated_install_hours=_install_hours(risk_score),
            risk_flags=risk_flags,
        )
