#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/cli.py — hallptz command-line interface
#
# Entry point for all hallptz subcommands.
# Run locally:  python -m runtime.cli <command>
# After install: hallptz <command>
#
# Current commands:
#   hallptz version   — print app name and version
#   hallptz status    — print service readiness summary
#   hallptz doctor    — run diagnostic checks and report health
#   hallptz setup     — launch the graphical first-run setup wizard

from __future__ import annotations

import argparse
import os
import sys

from app_version import APP_NAME, read_version
from domain.runtime_mode import RuntimeMode, parse_mode


# ── Command handlers ──────────────────────────────────────────────────────────

def _resolve_mode(args) -> RuntimeMode:
    """Return RuntimeMode from --profile flag or HALLPTZ_PROFILE env var."""
    raw = getattr(args, "profile", None) or os.environ.get("HALLPTZ_PROFILE", "production")
    try:
        return parse_mode(raw)
    except ValueError:
        print(f"Unknown profile: {raw!r}. Using 'production'.", file=sys.stderr)
        return RuntimeMode.PRODUCTION


def _apply_demo_mode(mode: RuntimeMode):
    """Aplica el aislamiento demo si el modo lo requiere."""
    if mode in (RuntimeMode.DEMO, RuntimeMode.SIMULATION):
        from application.demo_guard import DemoGuard
        guard = DemoGuard(mode=mode)
        demo_dir = guard.apply()
        return guard, demo_dir
    return None, None


_demo_guard = None  # keeps DemoGuard alive for the duration of the process


def _prepare_runtime_mode(args) -> RuntimeMode:
    """Aplica el perfil runtime antes de crear servicios dependientes de rutas."""
    global _demo_guard
    mode = _resolve_mode(args)
    os.environ["HALLPTZ_PROFILE"] = mode.value
    guard, _ = _apply_demo_mode(mode)
    if guard is not None:
        _demo_guard = guard  # prevent premature GC of demo isolation
    return mode


def _make_cli_recorder():
    """
    Return a FlightRecorder for production CLI commands, or None in dev/test.

    Uses the same running_from_source guard as bootstrap._create_flight_recorder()
    so that CLI commands (backup, restore, doctor) write to the shared blackbox log
    on a real install.  Never raises.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        if resolver.running_from_source:
            return None
        from application.flight_recorder import FlightRecorder
        return FlightRecorder(events_file=resolver.blackbox_events_file)
    except Exception:
        return None


def cmd_version(args) -> int:
    _prepare_runtime_mode(args)
    from runtime.build_info import build_info
    info = build_info()
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "version": info.app_version,
            "build": info.git_commit,
            "python": sys.version.split()[0],
            "platform": sys.platform,
        }, indent=2))
        return 0
    print(info.version_line())
    return 0


def cmd_status(args) -> int:
    mode = _prepare_runtime_mode(args)
    from application.diagnostics_service import DiagnosticsService, Status
    svc = DiagnosticsService(mode=mode)
    report = svc.run()
    _STATUS_ICON = {Status.OK: "+", Status.WARNING: "!", Status.FAIL: "X"}
    if mode != RuntimeMode.PRODUCTION:
        print(f"  [MODE] {mode.value.upper()}")
    for check in report.checks:
        print(f"  {_STATUS_ICON[check.status]}  {check.name}: {check.message}")

    try:
        from runtime.path_resolver import RuntimePathResolver
        marker = RuntimePathResolver().session_marker_file
        if marker.exists():
            ts = marker.read_text(encoding="utf-8").strip()
            print(f"  [INFO]  Session: active since {ts}")
        else:
            print("  [INFO]  Session: none active")
    except Exception:
        pass

    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "show", "hallptz-control",
             "--property=ActiveEnterTimestamp,NRestarts"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            props: dict[str, str] = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    props[k.strip()] = v.strip()
            ts_raw = props.get("ActiveEnterTimestamp", "")
            nrestarts = props.get("NRestarts", "")
            if ts_raw and ts_raw not in ("", "n/a"):
                parts = ts_raw.split()
                if len(parts) >= 3:
                    date_str = parts[1]
                    time_str = parts[2][:5]
                    started = f"{time_str} on {date_str}"
                    restarts_part = f" | restarts: {nrestarts}" if nrestarts else ""
                    print(f"  [INFO]  Service: started {started}{restarts_part}")
    except Exception:
        pass

    return report.exit_code


def cmd_uptime(args) -> int:
    _prepare_runtime_mode(args)
    import subprocess
    import datetime

    def _fmt_duration(seconds: float) -> str:
        total = int(seconds)
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        return " ".join(parts)

    try:
        result = subprocess.run(
            ["systemctl", "show", "hallptz-control",
             "--property=ActiveEnterTimestamp"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("ActiveEnterTimestamp="):
                    ts_raw = line.split("=", 1)[1].strip()
                    if ts_raw and ts_raw not in ("", "n/a"):
                        parts = ts_raw.split()
                        if len(parts) >= 3:
                            dt_str = f"{parts[1]} {parts[2]}"
                            fmt = "%Y-%m-%d %H:%M:%S"
                            try:
                                dt = datetime.datetime.strptime(dt_str, fmt)
                            except ValueError:
                                dt_str2 = " ".join(parts[1:3])
                                dt = datetime.datetime.strptime(dt_str2, fmt)
                            now = datetime.datetime.now()
                            elapsed = (now - dt).total_seconds()
                            duration = _fmt_duration(elapsed)
                            started = dt.strftime("%Y-%m-%d %H:%M")
                            print(f"  [OK]   Service uptime: {duration} (started {started})")
                            return 0
    except Exception:
        pass

    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            seconds = float(fh.read().split()[0])
        duration = _fmt_duration(seconds)
        print(f"  [INFO]  System uptime: {duration}")
        return 0
    except Exception:
        pass

    print("  [INFO]  Uptime: not available")
    return 0


def cmd_cameras(args) -> int:
    _prepare_runtime_mode(args)
    import socket
    import time

    try:
        from runtime.path_resolver import RuntimePathResolver
        from config.loader import load_config
        config_path = RuntimePathResolver().config_dir / "config.yaml"
        if not config_path.exists():
            print("  [WARN]  Config not found — cannot list cameras")
            return 1
        settings = load_config(config_path)
    except Exception:
        print("  [WARN]  Config not found — cannot list cameras")
        return 1

    try:
        from config import VISCA_PORT
        port = VISCA_PORT
    except Exception:
        port = 5678

    for cam in settings.cameras:
        ip = cam.ip
        name = cam.id
        try:
            t0 = time.monotonic()
            with socket.create_connection((ip, port), timeout=1.0):
                pass
            latency_ms = int((time.monotonic() - t0) * 1000)
            print(f"  [OK]   Camera '{name}' ({ip}): reachable on port {port} ({latency_ms}ms)")
        except Exception:
            print(f"  [WARN]  Camera '{name}' ({ip}): unreachable")

    return 0


def cmd_migrate(args) -> int:
    _prepare_runtime_mode(args)
    from application.legacy_migration import migrate
    from pathlib import Path as _Path
    from runtime.path_resolver import RuntimePathResolver
    install_dir = _Path(__file__).parent.parent
    resolver = RuntimePathResolver()
    config_path = _Path(args.config) if args.config else resolver.config_dir / "config.yaml"
    dry_run = getattr(args, "dry_run", False)
    result = migrate(install_dir, config_path, overwrite=args.overwrite, dry_run=dry_run)
    print(result.summary())
    if dry_run:
        return 0  # dry-run always exits 0
    return 0 if result.config_written or not result.skipped_reason else 1


def cmd_doctor(args) -> int:
    mode = _prepare_runtime_mode(args)
    from application.diagnostics_service import DiagnosticsService, Status
    svc = DiagnosticsService(mode=mode, flight_recorder=_make_cli_recorder())
    report = svc.run()

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(report.to_json_dict(), indent=2))
        return report.exit_code

    _STATUS_LABEL = {Status.OK: "OK", Status.WARNING: "WARN", Status.FAIL: "FAIL"}
    _STATUS_ICON  = {Status.OK: "+", Status.WARNING: "!", Status.FAIL: "X"}
    print(f"{APP_NAME} -- diagnostics")
    if mode != RuntimeMode.PRODUCTION:
        print(f"  [MODE] {mode.value.upper()}")
    print("-" * 40)
    for check in report.checks:
        label = _STATUS_LABEL[check.status]
        icon  = _STATUS_ICON[check.status]
        hint = f" -> {check.suggested_action}" if check.suggested_action else ""
        print(f"  [{label:4}] {icon}  {check.name}: {check.message}{hint}")
        if check.evidence:
            for k, v in check.evidence.items():
                print(f"             {k}: {v}")
    print("-" * 40)
    # The outcome, not the raw worst status, is what tells an installer whether
    # the appliance is unusable, needs configuration, or is ready (#887).
    print(f"  Outcome: {report.outcome.value}")
    print(f"           {report.outcome_description}")
    actions = report.action_list()
    if actions:
        print("")
        print("  Next actions:")
        for i, action in enumerate(actions, 1):
            print(f"    {i}. {action}")
    return report.exit_code


def cmd_fingerprint(args) -> int:
    _prepare_runtime_mode(args)
    from application.fingerprint_service import FingerprintService
    svc = FingerprintService()
    fp = svc.generate()
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(fp.to_dict(), indent=2))
        return 0
    for line in fp.human_summary():
        print(line)
    return 0


def cmd_known_good(args) -> int:
    _prepare_runtime_mode(args)
    from application.known_good_state_service import KnownGoodStateService
    svc = KnownGoodStateService()
    sub = args.known_good_command

    if sub == "show":
        snap = svc.load()
        if snap is None:
            print("  No known-good state recorded.")
            print("  Run: hallptz known-good mark --after-doctor-pass")
            return 1
        if getattr(args, "json", False):
            import json as _json
            print(_json.dumps(snap.to_dict(), indent=2))
            return 0
        for line in snap.human_summary():
            print(line)
        return 0

    if sub == "mark":
        note = getattr(args, "note", "") or ""
        force = getattr(args, "force", False)
        result = svc.mark(note=note, force=force)
        print(result.summary())
        return 0 if result.success else 1

    if sub == "diff":
        diff = svc.diff()
        if getattr(args, "json", False):
            import json as _json
            print(_json.dumps(diff.to_dict(), indent=2))
            return 0 if diff.is_clean else 1
        for line in diff.human_summary():
            print(line)
        return 0 if diff.is_clean else 1

    print(f"Unknown known-good command: {sub!r}", file=sys.stderr)
    return 1


def cmd_maintenance(args) -> int:
    _prepare_runtime_mode(args)
    from application.maintenance_service import MaintenanceService
    svc = MaintenanceService()
    sub = args.maintenance_command

    if sub == "status":
        result = svc.status()
        if getattr(args, "json", False):
            import json as _json
            print(_json.dumps(result.to_dict(), indent=2))
            return 1 if result.overdue else 0
        for line in result.human_summary():
            print(line)
        return 1 if result.overdue else 0

    if sub == "mark-complete":
        completed_by = getattr(args, "by", "operator") or "operator"
        notes = getattr(args, "notes", "") or ""
        record = svc.mark_complete(completed_by=completed_by, notes=notes)
        print(f"  [OK]   Maintenance recorded at {record.completed_at}")
        return 0

    print(f"Unknown maintenance command: {sub!r}", file=sys.stderr)
    return 1


def cmd_installability(args) -> int:
    _prepare_runtime_mode(args)
    from application.maintenance_service import InstallabilityService
    svc = InstallabilityService()

    sub = args.installability_command

    if sub == "score":
        result = svc.assess(
            wired_network_available=_tribool(getattr(args, "wired_network", None)),
            static_ips_possible=_tribool(getattr(args, "static_ips", None)),
            customer_it_required=getattr(args, "customer_it", False),
            atem_present=getattr(args, "atem", False),
            unsupported_hardware=getattr(args, "unsupported_hw", False),
        )
        if getattr(args, "json", False):
            import json as _json
            print(_json.dumps(result.to_dict(), indent=2))
            return 0
        for line in result.human_summary():
            print(line)
        return 0

    if sub == "status":
        result = svc.assess()
        for line in result.human_summary():
            print(line)
        return 0

    print(f"Unknown installability command: {sub!r}", file=sys.stderr)
    return 1


def cmd_supportability(args) -> int:
    _prepare_runtime_mode(args)
    from application.supportability_service import SupportabilityService
    svc = SupportabilityService()
    summary = svc.generate()
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(summary.to_dict(), indent=2))
        return summary.doctor_exit_code
    for line in summary.human_summary():
        print(line)
    return summary.doctor_exit_code


def cmd_network_report(args) -> int:
    """Generate a network handover report for this installation."""
    _prepare_runtime_mode(args)
    from application.network_handover_report import NetworkHandoverReportService

    # Optionally run preflight if --with-preflight flag is set
    preflight_report = None
    if getattr(args, "with_preflight", False):
        from application.diagnostics_service import DiagnosticsService
        preflight_report = DiagnosticsService().run()

    svc = NetworkHandoverReportService()
    report = svc.generate(
        preflight_report=preflight_report,
        notes=getattr(args, "notes", "") or "",
    )

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps(report.to_dict(), indent=2))
        return 0
    for line in report.human_summary():
        print(line)
    return 0


def _tribool(value: str | None) -> bool | None:
    """Convert CLI string 'yes'/'no'/None to bool | None."""
    if value is None:
        return None
    return value.lower() in ("yes", "true", "1")


def cmd_backup(args) -> int:
    _prepare_runtime_mode(args)
    from application.backup_service import BackupService
    from pathlib import Path
    dest = Path(args.dest) if args.dest else None
    svc = BackupService(flight_recorder=_make_cli_recorder())
    try:
        result = svc.create_backup(dest=dest)
    except OSError as exc:
        print(f"  [FAIL] Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"  [OK]   Backup created: {result.path}")
    print(f"         Included ({len(result.included)}): {', '.join(result.included) or 'none'}")
    if result.skipped:
        print(f"         Skipped  ({len(result.skipped)}): {', '.join(result.skipped)}")
    return 0


def cmd_restore(args) -> int:
    _prepare_runtime_mode(args)
    from application.restore_service import RestoreService, RestoreError
    from pathlib import Path
    zip_path = Path(args.zip_path)
    dry_run = getattr(args, "dry_run", False)
    svc = RestoreService(flight_recorder=_make_cli_recorder())
    try:
        result = svc.restore(zip_path, dry_run=dry_run)
    except RestoreError as exc:
        print(f"  [FAIL] Restore aborted: {exc}", file=sys.stderr)
        return 1
    if dry_run:
        print(f"  [dry-run] would restore: {', '.join(result.restored) or 'none'}")
        if result.skipped:
            print(f"  [dry-run] would skip:    {', '.join(result.skipped)}")
        return 0
    print("  [OK]   Restore complete")
    print(result.summary())
    return 0 if not result.failed else 1


def cmd_support_bundle(args) -> int:
    _prepare_runtime_mode(args)
    from application.support_bundle_service import SupportBundleService
    app_version = "unknown"
    installation_id = "unknown"
    installation_profile = "unknown"
    try:
        from application.fingerprint_service import FingerprintService
        fp = FingerprintService().generate()
        app_version = fp.app_version
        installation_id = fp.installation_id
        installation_profile = fp.profile
    except Exception:
        pass
    try:
        from runtime.path_resolver import RuntimePathResolver
        incidents_dir = RuntimePathResolver().incidents_dir
    except Exception:
        incidents_dir = None
    svc = SupportBundleService(
        app_version=app_version,
        installation_id=installation_id,
        installation_profile=installation_profile,
        incidents_dir=incidents_dir,
        flight_recorder=_make_cli_recorder(),
    )
    path = svc.create()
    if path is None:
        print("[FAIL] Support bundle creation failed.", file=sys.stderr)
        return 1
    print(f"[OK]   Support bundle created: {path}")
    return 0


def _installed_gui_mode(resolver) -> str:
    """Return which launcher owns the GUI on this install: "system" or "user".

    Recorded as HALLPTZ_GUI_MODE by install.sh (#885). Installs predating the flag
    have no entry, and those were all system-mode — so that is the fallback.
    Diagnostics must respect it: in user mode hallptz-control.service is
    deliberately disabled, and telling the operator to start it would launch a
    second GUI competing for the same cameras.
    """
    from runtime.install_state import gui_mode

    return gui_mode(resolver)


def cmd_verify_install(args) -> int:
    """Post-install smoke check: verify product install health without touching hardware."""
    _prepare_runtime_mode(args)

    import importlib
    from pathlib import Path as _Path

    from runtime.path_resolver import RuntimePathResolver
    resolver = RuntimePathResolver()

    _PASS = "PASS"
    _WARN = "WARN"
    _FAIL = "FAIL"

    checks: list[dict] = []

    def _add(name: str, status: str, message: str, suggested_action: str = "") -> None:
        checks.append({
            "name": name,
            "status": status,
            "message": message,
            "suggested_action": suggested_action,
        })

    # App version
    try:
        from runtime.build_info import build_info
        info = build_info()
        _add("app_version", _PASS, f"App version: {info.version_line()}")
    except Exception as exc:
        _add("app_version", _FAIL, f"Could not read app version: {exc}",
             "Check VERSION file and runtime/build_info.py")

    # Config path
    config_path = resolver.config_dir / "config.yaml"
    if config_path.exists():
        try:
            from config.loader import load_config
            load_config(config_path)
            _add("config", _PASS, f"Config readable: {config_path}")
        except Exception as exc:
            _add("config", _WARN, f"Config parse error: {exc}",
                 f"Edit {config_path} to fix YAML/schema errors")
    else:
        _add("config", _WARN, f"Config not found: {config_path}",
             f"Copy config/defaults/starter.yaml to {config_path} and edit")

    # Writable runtime paths
    for label, path in [
        ("data_dir",    resolver.data_dir),
        ("log_dir",     resolver.log_dir),
        ("backup_dir",  resolver.backup_dir),
    ]:
        if not path.exists():
            _add(label, _WARN, f"{label} does not exist: {path}",
                 "Run installer to create: sudo ./runtime/installer/install.sh")
        elif not os.access(path, os.W_OK):
            _add(label, _FAIL, f"{label} not writable: {path}",
                 "Check directory ownership (expected hallptz:hallptz, mode 0750)")
        else:
            _add(label, _PASS, f"{label} writable: {path}")

    # PyQt5
    try:
        importlib.import_module("PyQt5")
        _add("pyqt5", _PASS, "PyQt5 available")
    except ImportError:
        _add("pyqt5", _FAIL, "PyQt5 not available",
             "sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg")

    # Systemd unit
    service_path = _Path("/etc/systemd/system/hallptz-control.service")
    if service_path.exists():
        _add("systemd_unit", _PASS, f"Service unit exists: {service_path}")
        # Check user/group in service file
        svc_text = service_path.read_text(encoding="utf-8", errors="replace")
        if "User=hallptz" in svc_text and "Group=hallptz" in svc_text:
            _add("systemd_user", _PASS, "Service user/group: hallptz")
        else:
            _add("systemd_user", _WARN, "Service user/group may not be 'hallptz'",
                 "Re-run installer to regenerate the service file")
    else:
        if resolver.running_from_source:
            _add("systemd_unit", _WARN,
                 "Running from source - systemd unit not installed (expected in product installs)",
                 "sudo ./runtime/installer/install.sh")
        else:
            _add("systemd_unit", _FAIL, f"Service unit missing: {service_path}",
                 "sudo ./runtime/installer/install.sh")

    # Service active status (best-effort, non-fatal). What "healthy" means here
    # depends on which launcher owns the GUI (#885).
    gui_mode = _installed_gui_mode(resolver)
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "is-active", "hallptz-control"],
            capture_output=True, text=True, timeout=5,
        )
        active_state = result.stdout.strip()
        if gui_mode == "user":
            # The desktop session owns the GUI; the system service must stay
            # down. An active one means two GUIs driving the same cameras.
            if active_state == "active":
                _add("service_active", _FAIL,
                     "hallptz-control is running while the GUI is session-owned "
                     "(two GUIs would compete for the cameras)",
                     "sudo systemctl disable --now hallptz-control")
            else:
                _add("service_active", _PASS,
                     f"hallptz-control correctly {active_state or 'not running'} "
                     "(GUI mode: user — the desktop session owns it)")
        elif active_state == "active":
            _add("service_active", _PASS, "hallptz-control service: active")
        elif active_state == "inactive":
            _add("service_active", _WARN, "hallptz-control service: inactive",
                 "sudo systemctl start hallptz-control")
        else:
            _add("service_active", _WARN, f"hallptz-control service: {active_state or 'unknown'}",
                 "sudo systemctl status hallptz-control --no-pager")
    except Exception:
        _add("service_active", _WARN, "Could not query systemd service status",
             "Run: sudo systemctl status hallptz-control --no-pager")

    # Session-owned GUI assets — only meaningful in user mode.
    if gui_mode == "user":
        gui_unit = _Path("/etc/systemd/user/hallptz-gui.service")
        gui_helper = _Path("/usr/local/libexec/hallptz-gui-session")
        missing = [str(p) for p in (gui_unit, gui_helper) if not p.exists()]
        if missing:
            _add("session_gui", _FAIL,
                 "Session GUI launcher incomplete: " + ", ".join(missing),
                 "sudo bash install_hallptz_rpi.sh --wizard-user <user> --gui-mode user")
        else:
            _add("session_gui", _PASS, "Session GUI launcher installed")

    # Overall
    statuses = [c["status"] for c in checks]
    overall = _FAIL if _FAIL in statuses else (_WARN if _WARN in statuses else _PASS)
    exit_code = 0 if overall != _FAIL else 1

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "overall": overall,
            "checks": checks,
        }, indent=2))
        return exit_code

    _ICON = {_PASS: "+", _WARN: "!", _FAIL: "X"}
    print(f"{APP_NAME} -- install verification")
    print("-" * 40)
    for c in checks:
        icon = _ICON[c["status"]]
        hint = f" -> {c['suggested_action']}" if c["suggested_action"] else ""
        print(f"  [{c['status']:4}] {icon}  {c['name']}: {c['message']}{hint}")
    print("-" * 40)
    print(f"  Overall: {overall}")
    return exit_code


def cmd_setup(args) -> int:
    """Launch the graphical setup wizard, unless the install is already provisioned.

    Idempotent so the same entrypoint serves both the desktop menu launcher and
    the first-boot XDG autostart entry: once provisioned, it prints a note and
    exits 0 without opening a window. ``--force`` reopens it to reconfigure.
    """
    _prepare_runtime_mode(args)
    from runtime.path_resolver import RuntimePathResolver
    from runtime.setup_launcher import run_setup_wizard, setup_wizard_needed
    resolver = RuntimePathResolver()
    force = getattr(args, "force", False)
    if not setup_wizard_needed(resolver, force=force):
        print("  [INFO]  Already provisioned — setup wizard not needed.")
        print("          Re-run with --force to reconfigure this installation.")
        return 0

    # Past the guard we are either a fresh install or an explicit repair
    # (--force on a provisioned install). Pre-fill from any existing
    # config.yaml — not just when already provisioned: the installer writes
    # config.yaml (with a generated site.installation_id) before the wizard
    # ever runs, so a plain first-run `hallptz setup` must still pick that up or
    # apply_files() would overwrite the stable ID with a blank one.
    answers = None
    from application.provisioning_service import ProvisioningService
    config_exists = (resolver.config_dir / "config.yaml").exists()
    if config_exists:
        answers = ProvisioningService().load_existing_answers(resolver)

    # If the marker exists but config.yaml itself is missing (unusual, e.g.
    # manually deleted), there's nothing to lose — fall through and let the
    # wizard's defaults be the recovery path.
    provisioned = resolver.provisioned_marker_file.exists()
    if provisioned:
        if answers is not None:
            print("  [INFO]  Repair mode — editing the current configuration.")
        elif config_exists:
            # config.yaml exists but failed to load. Opening the wizard
            # anyway would pre-fill wizard defaults, and a save would
            # silently overwrite this install's real cameras, ATEM and
            # network settings — refuse rather than risk that.
            print("  [FAIL]  Repair mode — config.yaml exists but could not be loaded.")
            print("          Refusing to open the wizard: continuing would silently")
            print("          overwrite cameras, ATEM and network settings with")
            print("          wizard defaults on save.")
            print("          Run 'hallptz doctor' to diagnose, or fix config.yaml by hand.")
            return 1
    # Reconfiguring an already-provisioned install requires the current admin
    # password first — desktop-session access to the wizard user alone must
    # not be enough to change cameras/network or reset both passwords via the
    # password-free /run/hallptz channel. Not required on a fresh install: there
    # is nothing to protect yet, and no admin password may even be set.
    return run_setup_wizard(answers=answers, require_admin_auth=provisioned)


def cmd_demo(args) -> int:
    if args.demo_command == "reset":
        from application.demo_reset_service import DemoResetService
        mode = _resolve_mode(args)
        os.environ["HALLPTZ_PROFILE"] = mode.value
        guard, demo_dir = _apply_demo_mode(mode)
        if guard is not None and demo_dir is not None:
            svc = DemoResetService(
                demo_data_dir=demo_dir,
                production_data_dirs=[guard.production_data_dir],
            )
        else:
            svc = DemoResetService()
        result = svc.reset()
        print(result.summary())
        return 0 if result.success else 1
    print(f"Unknown demo command: {args.demo_command!r}", file=sys.stderr)
    return 1


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hallptz",
        description=f"{APP_NAME} command-line interface",
    )
    parser.add_argument(
        "--profile",
        metavar="MODE",
        default=None,
        help="Runtime mode: production (default), demo, simulation. "
             "Can also be set via HALLPTZ_PROFILE env var.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    version_p = sub.add_parser("version", help="Print app name and version")
    version_p.add_argument(
        "--json", action="store_true", default=False,
        help="Output structured JSON instead of human text",
    )
    sub.add_parser("status",  help="Print service readiness summary")
    sub.add_parser("uptime",  help="Show service or system uptime")
    sub.add_parser("cameras", help="List configured cameras and probe reachability")
    doctor_p = sub.add_parser("doctor",  help="Run diagnostic checks and report health")
    doctor_p.add_argument(
        "--json", action="store_true", default=False,
        help="Output structured JSON (DoctorCheckResult format) instead of human text",
    )

    fingerprint_p = sub.add_parser("fingerprint", help="Print installation fingerprint (safe state hash)")
    fingerprint_p.add_argument(
        "--json", action="store_true", default=False,
        help="Output structured JSON instead of human text",
    )

    kg_p = sub.add_parser("known-good", help="Show, mark or diff the known-good installation state")
    kg_sub = kg_p.add_subparsers(dest="known_good_command", metavar="<action>")
    kg_sub.required = True

    kg_show = kg_sub.add_parser("show", help="Show the stored known-good snapshot")
    kg_show.add_argument("--json", action="store_true", default=False,
                         help="Output JSON instead of human text")

    kg_mark = kg_sub.add_parser(
        "mark", help="Mark the current state as known-good (requires no blocking doctor checks)"
    )
    kg_mark.add_argument("--note", metavar="TEXT", default="",
                         help="Optional human note to attach to the snapshot")
    kg_mark.add_argument("--force", action="store_true", default=False,
                         help="Mark even if blocking doctor checks exist (use with care)")

    kg_diff = kg_sub.add_parser("diff", help="Diff current state against the known-good snapshot")
    kg_diff.add_argument("--json", action="store_true", default=False,
                         help="Output JSON diff instead of human text")

    maint_p = sub.add_parser("maintenance", help="Show or record monthly maintenance status")
    maint_sub = maint_p.add_subparsers(dest="maintenance_command", metavar="<action>")
    maint_sub.required = True
    maint_status = maint_sub.add_parser("status", help="Show maintenance due/overdue state")
    maint_status.add_argument("--json", action="store_true", default=False,
                              help="Output JSON instead of human text")
    maint_mark = maint_sub.add_parser("mark-complete", help="Record a maintenance completion")
    maint_mark.add_argument("--by", metavar="NAME", default="operator",
                            help="Name of the person who completed maintenance")
    maint_mark.add_argument("--notes", metavar="TEXT", default="",
                            help="Optional notes")

    inst_p = sub.add_parser("installability", help="Assess installation risk profile")
    inst_sub = inst_p.add_subparsers(dest="installability_command", metavar="<action>")
    inst_sub.required = True
    inst_sub.add_parser("status", help="Show current installability assessment (defaults only)")
    inst_score = inst_sub.add_parser("score", help="Compute deterministic risk score from flags")
    inst_score.add_argument("--wired-network", metavar="yes|no", default=None,
                            help="Wired network available at site")
    inst_score.add_argument("--static-ips", metavar="yes|no", default=None,
                            help="Static IP assignment possible")
    inst_score.add_argument("--customer-it", action="store_true", default=False,
                            help="Customer IT involvement required")
    inst_score.add_argument("--atem", action="store_true", default=False,
                            help="ATEM switcher integration required")
    inst_score.add_argument("--unsupported-hw", action="store_true", default=False,
                            help="Unsupported hardware present")
    inst_score.add_argument("--json", action="store_true", default=False,
                            help="Output JSON instead of human text")

    supp_p = sub.add_parser(
        "supportability", help="Show combined supportability summary (doctor + known-good + warranty)"
    )
    supp_p.add_argument("--json", action="store_true", default=False,
                        help="Output structured JSON instead of human text")

    migrate_p = sub.add_parser("migrate", help="Migrate legacy .txt config files to config.yaml")
    migrate_p.add_argument("--config", metavar="PATH", default=None,
                           help="Override destination config.yaml path")
    migrate_p.add_argument("--overwrite", action="store_true",
                           help="Overwrite existing config.yaml (creates a .bak backup first)")
    migrate_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                           help="Report what would be migrated without writing any files")

    sub.add_parser("support-bundle", help="Create a sanitized support bundle ZIP (blackbox events + incidents)")

    verify_p = sub.add_parser(
        "verify-install",
        help="Post-install smoke check: verify product install health without touching hardware",
    )
    verify_p.add_argument("--json", action="store_true", default=False,
                          help="Output structured JSON instead of human text")

    backup_p = sub.add_parser("backup", help="Create a manifest-based ZIP backup")
    backup_p.add_argument("--dest", metavar="PATH", default=None,
                          help="Destination path (optional — omit for auto-named timestamped backup)")

    restore_p = sub.add_parser("restore", help="Restore from a manifest-based ZIP backup")
    restore_p.add_argument("zip_path", metavar="BACKUP.ZIP",
                           help="Path to the backup ZIP to restore")
    restore_p.add_argument(
        "--dry-run", action="store_true", dest="dry_run", default=False,
        help="Preview what would be restored without writing any files",
    )

    net_report_p = sub.add_parser(
        "network-report",
        help="Generate network handover report for customer installations",
    )
    net_report_p.add_argument(
        "--json", action="store_true", default=False,
        help="Output structured JSON instead of human text",
    )
    net_report_p.add_argument(
        "--with-preflight", action="store_true", default=False,
        help="Run doctor preflight checks and include results in the report",
    )
    net_report_p.add_argument(
        "--notes", metavar="TEXT", default="",
        help="Optional installer/customer notes to include in the report",
    )

    setup_p = sub.add_parser("setup", help="Launch the graphical first-run setup wizard")
    setup_p.add_argument(
        "--force", action="store_true", default=False,
        help="Repair: reopen the wizard on an already-provisioned install, "
             "pre-filled with the current configuration",
    )

    demo_p = sub.add_parser("demo", help="Demo mode utilities")
    demo_sub = demo_p.add_subparsers(dest="demo_command", metavar="<action>")
    demo_sub.required = True
    demo_sub.add_parser("reset", help="Reset demo data to clean bundled templates")

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

_COMMANDS = {
    "version":         cmd_version,
    "status":          cmd_status,
    "uptime":          cmd_uptime,
    "cameras":         cmd_cameras,
    "doctor":          cmd_doctor,
    "fingerprint":     cmd_fingerprint,
    "known-good":      cmd_known_good,
    "maintenance":     cmd_maintenance,
    "installability":  cmd_installability,
    "supportability":  cmd_supportability,
    "support-bundle":  cmd_support_bundle,
    "verify-install":  cmd_verify_install,
    "migrate":         cmd_migrate,
    "backup":      cmd_backup,
    "restore":     cmd_restore,
    "setup":           cmd_setup,
    "demo":            cmd_demo,
    "network-report":  cmd_network_report,
}


#: Commands the desktop user runs interactively. These must never require write
#: access to service-owned production paths such as /var/log/hallptz (#884).
_INTERACTIVE_COMMANDS = frozenset({"setup", "demo"})


def _cli_log_dir(command: str | None, resolver):
    """Pick a log directory the *current* user can actually write to.

    Interactive commands log under the desktop user's state directory by
    design. Everything else prefers the production log directory but falls back
    to the user's own rather than emitting permission warnings — a CLI command
    must not fail or nag merely because it cannot open a log file (#884).
    """
    from runtime.console import user_state_dir, writable_log_dir
    if command in _INTERACTIVE_COMMANDS:
        return writable_log_dir(user_state_dir() / "logs")
    return writable_log_dir(resolver.log_dir)


def main(argv: list[str] | None = None) -> int:
    # Before any output: a legacy terminal locale must not be able to abort a
    # command part-way through printing (#884).
    from runtime.console import configure_console_encoding
    configure_console_encoding()

    parser = build_parser()
    args = parser.parse_args(argv)

    from runtime.path_resolver import RuntimePathResolver
    resolver = RuntimePathResolver()
    if not resolver.running_from_source:
        from runtime.logging_setup import setup_logging, log_startup_summary
        from runtime.build_info import build_info
        info = build_info(data_dir=resolver.data_dir)
        log_dir = _cli_log_dir(getattr(args, "command", None), resolver)
        setup_logging(log_dir=log_dir, version_line=info.version_line())
        log_startup_summary(resolver, mode=info.runtime_profile)

    from application.crash_reporter import install_crash_reporter
    install_crash_reporter(
        version=read_version(),
        mode=os.environ.get("HALLPTZ_PROFILE", "production"),
        log_dir=_cli_log_dir(getattr(args, "command", None), resolver),
    )
    handler = _COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    tracked_env = ("HALLPTZ_PROFILE", "HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR")
    previous_env = {name: os.environ.get(name) for name in tracked_env}
    try:
        return handler(args)
    finally:
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    sys.exit(main())
