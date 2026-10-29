#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/support_bundle_service.py — Sanitized support bundle export (#491)
#
# Creates a ZIP at <output_dir>/support-<timestamp>-<install_id>.zip containing:
#   manifest.json              — bundle metadata (never restore_capable)
#   version.txt                — hallptz version + build identity
#   doctor.txt                 — hallptz doctor output (structured, sanitized)
#   install_summary.json       — installation/profile/identity summary
#   config_summary.json        — sanitized config summary (no secret values)
#   blackbox/recent_events.jsonl — up to 500 recent FlightRecorder events
#   blackbox/incidents/        — up to 20 most recent incident snapshots
#   blackbox/README.txt        — description of black box data
#
# Safety contract:
#   - never raises into live operation
#   - redaction is applied before all content is written to the ZIP
#   - bundle is never restore_capable
#   - excluded files (secrets) are listed in the manifest
#   - missing black box data is reported as unavailable, not silent
#   - config summary excludes raw secret values (password, keys, tokens)

from __future__ import annotations

import json
import logging
import os
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

from domain.blackbox_event import redact_event_dict
from domain.redaction import SupportBundleManifest
from domain.time_utils import utc_now_compact as _utc_stamp, utc_now_iso as _utc_now_iso

_MAX_EVENTS     = 500
_MAX_INCIDENTS  = 20
_MAX_BUNDLES    = 5

_BLACKBOX_README = """\
Hall PTZ Control — Black Box Data
================================

recent_events.jsonl
  Operational event log from the last session (flight recorder).
  Records camera commands, session lifecycle events, backup/restore
  and diagnostics runs.  Secrets are redacted before writing.
  Format: one JSON object per line (JSONL).

incidents/
  Sanitized incident snapshots written when a critical failure occurs.
  Each file is a JSON object with: reason, severity, summary, last events,
  app version, installation profile and a redaction marker.
  Secrets are redacted before writing.

Both sources are read-only and do not contain passwords, private keys
or customer personally identifiable information beyond installation IDs.
""".strip()


class SupportBundleService:
    """
    Creates a sanitized support bundle ZIP for remote diagnosis.

    The bundle contains recent black box events and incident snapshots,
    both redacted.  It is never a restore backup.

    Parameters
    ----------
    output_dir:
        Where to write the ZIP. Defaults to <backup_dir>/support/.
    flight_recorder:
        Optional FlightRecorder for pulling recent events.
    incidents_dir:
        Directory containing incident JSON files written by IncidentService.
    app_version:
        Application version string for the bundle manifest.
    installation_id:
        Installation identifier for the bundle manifest.
    installation_profile:
        Profile name (e.g. starter_2_camera, standard_4_camera).
    max_events:
        Maximum number of events to include. Default: 500.
    max_incidents:
        Maximum number of incident snapshots to include. Default: 20.
    max_bundles:
        Number of support bundles to retain. Default: 5.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        flight_recorder=None,
        incidents_dir: Path | None = None,
        app_version: str = "unknown",
        installation_id: str = "unknown",
        installation_profile: str = "unknown",
        max_events: int = _MAX_EVENTS,
        max_incidents: int = _MAX_INCIDENTS,
        max_bundles: int = _MAX_BUNDLES,
    ) -> None:
        if output_dir is None:
            try:
                from runtime.path_resolver import RuntimePathResolver
                output_dir = RuntimePathResolver().support_bundle_dir
            except Exception:
                output_dir = Path.home() / ".config" / "hallptz" / "backups" / "support"
        self._output_dir        = Path(output_dir)
        self._recorder          = flight_recorder
        self._incidents_dir     = Path(incidents_dir) if incidents_dir else None
        self._app_version       = app_version
        self._installation_id   = installation_id
        self._installation_profile = installation_profile
        self._max_events        = max_events
        self._max_incidents     = max_incidents
        self._max_bundles       = max_bundles

    def create(self) -> Path | None:
        """
        Create a support bundle ZIP and return its path.

        Returns None on any error (never raises).
        """
        try:
            return self._create_inner()
        except Exception:
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _create_inner(self) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        stamp    = _utc_stamp()
        id_short = self._installation_id[:8] if len(self._installation_id) >= 8 \
                   else self._installation_id
        bundle_id = f"support-{stamp}-{id_short}"
        out_path  = self._output_dir / f"{bundle_id}.zip"

        events, events_status   = self._collect_events()
        incidents, inc_status   = self._collect_incidents()

        included: list[str] = []
        # Declared to whoever receives the bundle, so it must name every secret
        # the product actually has. admin.enc arrived with the operator/admin
        # password split and was missing here — the bundle never contained it
        # (content is assembled from an allow-list, nothing walks the data
        # directory), but the manifest under-reported what was protected.
        excluded: list[str] = [
            "password.enc",
            "admin.enc",
            "password.txt",
            "*.key",
            "config.yaml (raw)",
        ]
        warnings: list[str] = []

        if events_status != "ok":
            warnings.append(f"blackbox_events: {events_status}")
        if inc_status != "ok":
            warnings.append(f"incidents: {inc_status}")

        # Build all content before writing so manifest lists exact file set
        entries: list[tuple[str, str]] = []

        # version.txt
        version_txt, version_warn = self._collect_version()
        entries.append(("version.txt", version_txt))
        included.append("version.txt")
        if version_warn:
            warnings.append(f"version: {version_warn}")

        # doctor.txt
        doctor_txt, doctor_warn = self._collect_doctor()
        entries.append(("doctor.txt", doctor_txt))
        included.append("doctor.txt")
        if doctor_warn:
            warnings.append(f"doctor: {doctor_warn}")

        # install_summary.json
        install_summary, install_warn = self._collect_install_summary()
        entries.append(("install_summary.json", install_summary))
        included.append("install_summary.json")
        if install_warn:
            warnings.append(f"install_summary: {install_warn}")

        # config_summary.json
        config_summary, config_warn = self._collect_config_summary()
        entries.append(("config_summary.json", config_summary))
        included.append("config_summary.json")
        if config_warn:
            warnings.append(f"config_summary: {config_warn}")

        # blackbox events
        if events is not None:
            content = "\n".join(
                json.dumps(redact_event_dict(e), ensure_ascii=True) for e in events
            ) + "\n"
            entries.append(("blackbox/recent_events.jsonl", content))
            included.append("blackbox/recent_events.jsonl")

        for name, data in incidents:
            arc = f"blackbox/incidents/{name}"
            entries.append((arc, data))
            included.append(arc)

        entries.append(("blackbox/README.txt", _BLACKBOX_README))
        included.append("blackbox/README.txt")
        included.insert(0, "manifest.json")

        manifest = SupportBundleManifest(
            bundle_id=bundle_id,
            generated_at=_utc_now_iso(),
            installation_id=self._installation_id,
            app_version=self._app_version,
            profile=self._installation_profile,
            redaction_status="applied",
            included_files=tuple(included),
            excluded_files=tuple(excluded),
            redaction_warnings=tuple(warnings),
            restore_capable=False,
            bundle_purpose="support",
        )

        tmp_path = out_path.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json",
                            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=True) + "\n")
                for arc, data in entries:
                    zf.writestr(arc, data)
            os.replace(tmp_path, out_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        self._prune()
        return out_path

    def _collect_version(self) -> tuple[str, str]:
        try:
            from runtime.build_info import build_info
            info = build_info()
            lines = [
                info.version_line(),
                f"app_version: {info.app_version}",
                f"git_commit: {info.git_commit}",
                f"profile: {info.runtime_profile}",
                f"installation_id: {info.installation_id}",
                f"running_from_source: {info.running_from_source}",
            ]
            return "\n".join(lines) + "\n", ""
        except Exception as exc:
            return f"version: unavailable ({exc})\n", str(exc)

    def _collect_doctor(self) -> tuple[str, str]:
        try:
            from application.diagnostics_service import DiagnosticsService, Status
            svc = DiagnosticsService()
            report = svc.run()
            _label = {Status.OK: "OK  ", Status.WARNING: "WARN", Status.FAIL: "FAIL"}
            _icon  = {Status.OK: "+", Status.WARNING: "!", Status.FAIL: "X"}
            lines = ["Hall PTZ Control -- diagnostics (support bundle snapshot)"]
            for check in report.checks:
                hint = f" -> {check.suggested_action}" if check.suggested_action else ""
                lines.append(f"  [{_label[check.status]}] {_icon[check.status]}  {check.name}: {check.message}{hint}")
                if check.evidence:
                    for k, v in check.evidence.items():
                        lines.append(f"             {k}: {v}")
            lines.append(f"  Overall: {_label[report.overall]}")
            return "\n".join(lines) + "\n", ""
        except Exception as exc:
            return f"doctor: unavailable ({exc})\n", str(exc)

    def _collect_install_summary(self) -> tuple[str, str]:
        try:
            from runtime.build_info import build_info
            from runtime.path_resolver import RuntimePathResolver
            resolver = RuntimePathResolver()
            info = build_info(data_dir=resolver.data_dir)
            summary = {
                "installation_id": info.installation_id,
                "app_version": info.app_version,
                "git_commit": info.git_commit,
                "profile": info.runtime_profile,
                "running_from_source": info.running_from_source,
                "paths": resolver.to_dict(),
            }
            return json.dumps(summary, indent=2, ensure_ascii=True) + "\n", ""
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2) + "\n", str(exc)

    def _collect_config_summary(self) -> tuple[str, str]:
        """Return a redacted config summary — keys present, no raw secret values."""
        try:
            from application.fingerprint_service import FingerprintService
            fp = FingerprintService().generate()
            summary = {
                "config_hash": fp.config_hash,
                "layout_hash": fp.layout_hash,
                "cameras_count": len(fp.cameras),
                "atem_enabled": fp.atem_enabled,
                "atem_configured": fp.atem_configured,
                "fingerprint_hash": fp.fingerprint_hash(),
            }
            return json.dumps(summary, indent=2, ensure_ascii=True) + "\n", ""
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2) + "\n", str(exc)

    def _collect_events(self) -> tuple[list[dict] | None, str]:
        if self._recorder is None:
            return None, "no_recorder"
        try:
            events = self._recorder.export_for_support(self._max_events)
            return events, "ok"
        except Exception as exc:
            return None, f"error: {exc}"

    def _collect_incidents(self) -> tuple[list[tuple[str, str]], str]:
        if self._incidents_dir is None:
            return [], "no_incidents_dir"
        idir = self._incidents_dir
        if not idir.exists():
            return [], "unavailable"
        try:
            files = sorted(
                idir.glob("incident-*.json"),
                key=lambda p: (p.stat().st_mtime, p.name),
                reverse=True,
            )[: self._max_incidents]
            results: list[tuple[str, str]] = []
            parse_errors = 0
            for f in files:
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    redacted = redact_event_dict(raw)
                    results.append((f.name, json.dumps(redacted, indent=2, ensure_ascii=True) + "\n"))
                except Exception:
                    parse_errors += 1
            if parse_errors and not results:
                return [], f"all_{parse_errors}_files_corrupt"
            if parse_errors:
                return results, f"partial_{parse_errors}_corrupt"
            return results, "ok"
        except Exception as exc:
            return [], f"error: {exc}"

    def _prune(self) -> None:
        try:
            files = sorted(
                self._output_dir.glob("support-*.zip"),
                key=lambda p: p.stat().st_mtime,
            )
            for old in files[: max(0, len(files) - self._max_bundles)]:
                old.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_prune: could not remove old support bundles: %s", exc)
