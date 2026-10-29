#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""application/provisioning_service.py — headless engine behind the setup wizard.

The graphical wizard only collects answers and shows results; this service is
the single place that turns those answers into a validated configuration and
the local files a working install needs. It is deliberately Qt-free and
hardware-free so it can be tested exhaustively without a screen or a Pi.

Responsibilities split by privilege:
  - to_app_settings / validate / plan — pure, always safe to call.
  - apply_files — writes config.yaml + the two password secrets into the paths
    from RuntimePathResolver. In production those dirs are root-owned, so this
    runs inside the privileged provisioning step; in tests the paths are env
    overrides pointing at a temp dir.

OS-level steps (create the khptz user, chown, copy /opt, install + enable the
systemd unit) are NOT here — they require root and live in the installer
(runtime/installer) driven by the same answers. plan() lists them so the
Review screen can show exactly what the privileged step will do.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from config.loader import ConfigError, build_settings
from config.settings import (
    AppSettings,
    ATEMSettings,
    CameraSettings,
    FeaturesSettings,
    NetworkSettings,
    RuntimeSettings,
    SiteSettings,
)
from config.writer import write_full_config
from domain.installation_profile import derive_installation_profile
from domain.network_validation import is_valid_ipv4
from runtime import secret_manager
from runtime.path_resolver import RuntimePathResolver


# ── Answer model (what the wizard collects) ───────────────────────────────────

@dataclass
class CameraAnswer:
    """One camera as entered in the wizard. `name` is the editable label."""
    id: str
    role: str
    ip: str
    visca_id: str
    name: str = ""


def _default_cameras() -> List[CameraAnswer]:
    return [
        CameraAnswer(id="platform", role="platform", ip="172.16.1.11",
                     visca_id="81", name="Main Platform"),
        CameraAnswer(id="comments", role="comments", ip="172.16.1.12",
                     visca_id="82", name="Comments Desk"),
    ]


@dataclass
class ProvisioningAnswers:
    """Everything the wizard gathers. Defaults are valid out of the box, so a
    technician can accept every screen and still produce a working install
    (passwords excepted — they are required and have no default)."""
    site_name: str = "My Venue"
    site_contact: str = "IT Support"
    installation_id: str = ""
    # Empty means "derive from the camera count". Only an explicit demo /
    # professional / custom choice is carried through verbatim (#886).
    installation_profile: str = ""
    cameras: List[CameraAnswer] = field(default_factory=_default_cameras)
    atem_enabled: bool = False
    atem_ip: str = "172.16.1.50"
    network_profile: str = "flat_lan"
    entry_password: str = ""
    admin_password: str = ""
    # Repair only: the CURRENT admin password, entered to prove authorization
    # to reconfigure an already-provisioned install — distinct from
    # admin_password above, which is the NEW admin password being set.
    # Verified by the privileged runtime.provision.run_provision(), never in
    # the wizard's own (unprivileged, desktop-session) process — that process
    # cannot reliably read the khptz:khptz-owned encrypted secret to check it
    # itself. See PR #867 review.
    current_admin_password: str = ""


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProvisioningIssue:
    field_path: str
    message: str
    remediation: str = ""


@dataclass(frozen=True)
class PlannedArtifact:
    kind: str        # "user" | "directory" | "config" | "secret" | "service" | "marker"
    target: str
    detail: str
    privileged: bool = True


@dataclass(frozen=True)
class ProvisioningPlan:
    artifacts: List[PlannedArtifact]


@dataclass(frozen=True)
class ApplyResult:
    ok: bool
    written: List[str]
    message: str = ""


def _default_camera_name(role: str) -> str:
    return role.strip().replace("_", " ").title() or "Camera"


# Roles the product understands. `platform` covers the first three seats and
# `comments` the rest (see application/preset_sources.py), so a real room needs
# both — the wizard must be able to reach a two-camera install even when the
# installer seeded the one-camera starter template.
KNOWN_CAMERA_ROLES = ("platform", "comments")


def next_camera_answer(existing: List[CameraAnswer]) -> CameraAnswer:
    """Build a valid, non-colliding CameraAnswer to append in the wizard.

    Kept out of the UI layer so the "what does an added camera look like"
    rule is testable without a screen (ADR-002: pages collect input only).
    Every field is chosen so ``validate()`` passes immediately: config.loader
    rejects duplicate id, duplicate IP, duplicate visca_id, a malformed IPv4
    and a visca_id that is not two hex digits, so an added camera that
    collided would leave the operator stuck on Review with no way to fix it
    from the Cameras screen.
    """
    used_roles = {c.role.strip() for c in existing}
    used_ids = {c.id.strip() for c in existing}
    used_visca = {c.visca_id.strip().upper() for c in existing}
    used_ips = {c.ip.strip() for c in existing}

    role = next(
        (r for r in KNOWN_CAMERA_ROLES if r not in used_roles),
        f"camera_{len(existing) + 1}",
    )

    cam_id = role
    suffix = 2
    while cam_id in used_ids:
        cam_id = f"{role}_{suffix}"
        suffix += 1

    # VISCA daisy-chain addresses start at 0x81; scan the whole byte range so
    # this never runs out before the UI does.
    visca_id = next(
        (f"{n:02X}" for n in list(range(0x81, 0x100)) + list(range(0x01, 0x81))
         if f"{n:02X}" not in used_visca),
        "81",
    )

    # Offer the next address on the same subnet as the last camera, so the
    # common case is a one-character edit rather than typing a full IP.
    ip = "172.16.1.11"
    if existing:
        parts = existing[-1].ip.strip().split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            base, last = ".".join(parts[:3]), int(parts[3])
            for step in range(1, 255):
                candidate = f"{base}.{(last + step) % 256}"
                if candidate not in used_ips and not candidate.endswith(".0"):
                    ip = candidate
                    break
    while ip in used_ips:
        ip = f"172.16.1.{(int(ip.rsplit('.', 1)[1]) + 1) % 256}"

    return CameraAnswer(id=cam_id, role=role, ip=ip, visca_id=visca_id,
                        name=_default_camera_name(role))


def _rescue_identity_fields(config_path: Path) -> tuple:
    """Best-effort raw-YAML read of site.installation_id/installation_profile.

    Used when the existing config.yaml fails strict schema validation
    (load_config) so apply_files() never silently stamps a blank
    installation_id over the stable one diagnostics/backup/licensing rely on
    — even when unrelated corruption elsewhere in the file breaks full
    parsing. Never raises; returns ("", "") if even this can't be read.
    """
    try:
        import yaml
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        site = raw.get("site") or {}
        return (
            str(site.get("installation_id") or ""),
            str(site.get("installation_profile") or ""),
        )
    except Exception:
        return "", ""


# ── Service ───────────────────────────────────────────────────────────────────

class ProvisioningService:
    """Turns wizard answers into validated settings and local files."""

    def to_app_settings(self, answers: ProvisioningAnswers) -> AppSettings:
        """Build the typed settings tree from answers (no validation)."""
        cameras = [
            CameraSettings(
                id=c.id, role=c.role, ip=c.ip, visca_id=c.visca_id,
                name=c.name.strip() or _default_camera_name(c.role),
            )
            for c in answers.cameras
        ]
        atem = ATEMSettings(
            ip=answers.atem_ip,
            installed=answers.atem_enabled,
            enabled=answers.atem_enabled,
        )
        return AppSettings(
            site=SiteSettings(
                name=answers.site_name,
                contact=answers.site_contact,
                installation_profile=derive_installation_profile(
                    len(cameras), answers.installation_profile,
                ).value,
                installation_id=answers.installation_id,
            ),
            cameras=cameras,
            atem=atem,
            runtime=RuntimeSettings(),
            features=FeaturesSettings(atem_enabled=answers.atem_enabled),
            network=NetworkSettings(profile=answers.network_profile),
        )

    def answers_from_settings(self, settings: AppSettings) -> ProvisioningAnswers:
        """Inverse of ``to_app_settings``: pre-fill wizard answers from settings.

        Used by Repair mode (``khptz setup --force`` on a provisioned install) so
        the operator edits the current values instead of re-entering everything.
        Passwords are NOT recoverable from the encrypted secrets, so they stay
        blank and must be re-confirmed on the Passwords screen.
        """
        return ProvisioningAnswers(
            site_name=settings.site.name,
            site_contact=settings.site.contact,
            installation_id=settings.site.installation_id,
            installation_profile=settings.site.installation_profile,
            cameras=[
                CameraAnswer(id=c.id, role=c.role, ip=c.ip,
                             visca_id=c.visca_id, name=c.name)
                for c in settings.cameras
            ],
            # ATEMSettings.enabled is the canonical flag (#550), but older
            # templates/legacy migrations only set features.atem_enabled —
            # OR both so Repair never pre-fills the checkbox unchecked for an
            # install where ATEM is actually on by either flag. Otherwise an
            # unnoticed save would round-trip that False back through
            # _merge_onto_existing() and silently disable ATEM diagnostics.
            atem_enabled=settings.atem.enabled or settings.features.atem_enabled,
            atem_ip=settings.atem.ip,
            network_profile=settings.network.profile,
        )

    def load_existing_answers(
        self,
        resolver: Optional[RuntimePathResolver] = None,
    ) -> Optional[ProvisioningAnswers]:
        """Load answers from the installed config.yaml, or None if absent/unreadable.

        Best-effort: a missing or malformed config returns None so Repair falls
        back to default answers rather than failing to open the wizard.
        """
        r = resolver or RuntimePathResolver()
        config_path = r.config_dir / "config.yaml"
        if not config_path.exists():
            return None
        try:
            from config.loader import load_config
            settings = load_config(config_path)
        except Exception:
            return None
        return self.answers_from_settings(settings)

    def validate(self, answers: ProvisioningAnswers) -> List[ProvisioningIssue]:
        """Return every problem that would stop a working install (empty if OK)."""
        issues: List[ProvisioningIssue] = []

        if not answers.cameras:
            issues.append(ProvisioningIssue(
                "cameras", "At least one camera is required",
                "Add a camera on the Cameras screen",
            ))
        if not answers.entry_password:
            issues.append(ProvisioningIssue(
                "entry_password", "The entry (operator) password is required",
                "Set an operator password on the Passwords screen",
            ))
        if not answers.admin_password:
            issues.append(ProvisioningIssue(
                "admin_password", "The administrator password is required",
                "Set an administrator password on the Passwords screen",
            ))
        # ATEM enabled without a usable address produced a permanent doctor
        # warning that the wizard itself had allowed the operator to create
        # (#886). Enabling the integration now requires an address for it.
        if answers.atem_enabled and not is_valid_ipv4(answers.atem_ip):
            detail = "is empty" if not answers.atem_ip.strip() else "is not a valid IPv4 address"
            issues.append(ProvisioningIssue(
                "atem_ip", f"ATEM is enabled but its IP address {detail}",
                "Enter the ATEM switcher IP on the Network screen, or disable ATEM",
            ))

        # Field-level validation (IP/VISCA format, duplicate ids/ips) reuses the
        # exact loader rules, in memory — never touches disk.
        if answers.cameras:
            try:
                build_settings(asdict(self.to_app_settings(answers)))
            except ConfigError as exc:
                issues.append(ProvisioningIssue(
                    exc.field_path or "config", str(exc), exc.remediation,
                ))
        return issues

    def advisories(self, answers: ProvisioningAnswers) -> List[ProvisioningIssue]:
        """Non-blocking deployment recommendations.

        Kept separate from validate() so the Review screen can distinguish
        "this will not work" from "this works, but consider hardening it"
        (#886). Advisories never stop provisioning.
        """
        notes: List[ProvisioningIssue] = []
        if answers.network_profile == "flat_lan":
            notes.append(ProvisioningIssue(
                "network_profile",
                "Cameras share the venue LAN (flat_lan)",
                "A dedicated camera VLAN is recommended for production sites",
            ))
        if not answers.atem_enabled:
            notes.append(ProvisioningIssue(
                "atem", "ATEM switcher integration is disabled",
                "Enable it on the Network screen if this venue has an ATEM",
            ))
        return notes

    def plan(
        self,
        answers: ProvisioningAnswers,
        resolver: Optional[RuntimePathResolver] = None,
    ) -> ProvisioningPlan:
        """List exactly what the privileged step will create (the Review screen)."""
        r = resolver or RuntimePathResolver()
        cam_count = len(answers.cameras)
        artifacts = [
            PlannedArtifact("user", "khptz", "dedicated service user"),
            PlannedArtifact("directory", str(r.config_dir), "site configuration"),
            PlannedArtifact("directory", str(r.data_dir), "runtime data"),
            PlannedArtifact("config", str(r.config_dir / "config.yaml"),
                            f"{cam_count} camera(s)"),
            PlannedArtifact("secret", str(secret_manager._secret_file(secret_manager.SECRET_ENTRY)),
                            "operator entry password"),
            PlannedArtifact("secret", str(secret_manager._secret_file(secret_manager.SECRET_ADMIN)),
                            "administrator password"),
            PlannedArtifact("service", "khptz-control", "systemd service (enabled)"),
            PlannedArtifact("marker", str(r.provisioned_marker_file),
                            "provisioned sentinel"),
        ]
        return ProvisioningPlan(artifacts=artifacts)

    def _merge_onto_existing(self, settings: AppSettings, existing: AppSettings) -> AppSettings:
        """Overlay wizard-editable fields onto the existing on-disk settings.

        ProvisioningAnswers only models a subset of AppSettings (site identity,
        cameras, ATEM ip/enabled, network profile). Without this, apply_files()
        would silently reset everything else it does NOT model — runtime.data_dir,
        network.av_subnet/notes, ATEM's PiP nudge/input labels, other feature
        flags — to dataclass defaults on every run, since it always wrote a
        settings tree built from scratch. Used on both a fresh install seeded by
        the installer's starter config and Repair (--force).

        installation_id is always taken from `existing`, never `settings`: no
        wizard page exposes it for editing, and this runs on the privileged
        (root) side, which can read config.yaml even when the unprivileged
        wizard process couldn't (e.g. the wizard user's `khptz` group
        membership not active yet on first boot — pre-relogin — leaving
        answers.installation_id blank). Silently keeping settings' blank value
        here would discard the stable id diagnostics/backup/licensing key off
        of.
        """
        from dataclasses import replace
        return replace(
            settings,
            site=replace(
                settings.site,
                installation_id=existing.site.installation_id,
                # installation_profile is deliberately NOT carried over from
                # `existing`: the installer seeds starter_1_camera before the
                # wizard runs, so preserving it left a two-camera install
                # permanently contradicting its own profile (#886). settings
                # already holds the derived value, which honours an explicit
                # demo/professional/custom choice.
            ),
            runtime=existing.runtime,
            atem=replace(
                existing.atem,
                ip=settings.atem.ip,
                installed=settings.atem.installed,
                enabled=settings.atem.enabled,
            ),
            features=replace(existing.features, atem_enabled=settings.features.atem_enabled),
            network=replace(existing.network, profile=settings.network.profile),
        )

    def apply_files(
        self,
        answers: ProvisioningAnswers,
        resolver: Optional[RuntimePathResolver] = None,
        *,
        config_mode: int = 0o640,
    ) -> ApplyResult:
        """Write config.yaml and both password secrets into the resolved paths.

        This is the file-writing half of provisioning — the part that does not
        need root once the directories exist. Secrets are written 0600 and
        config 0640 (so the service user can read it). Ownership (chown) is the
        installer's job since it needs privilege.
        """
        r = resolver or RuntimePathResolver()
        settings = self.to_app_settings(answers)
        written: List[str] = []

        config_path = r.config_dir / "config.yaml"
        if config_path.exists():
            try:
                from config.loader import load_config
                settings = self._merge_onto_existing(settings, load_config(config_path))
            except Exception:
                # Corrupt/unreadable existing config — can't merge the full
                # tree, but the identity fields (installation_id especially)
                # may still be readable via a lenient raw-YAML parse even
                # when strict schema validation fails elsewhere in the file.
                # Rescue those rather than silently blanking a stable ID that
                # diagnostics/backup/licensing rely on.
                rescued_id, rescued_profile = _rescue_identity_fields(config_path)
                if rescued_id or rescued_profile:
                    from dataclasses import replace
                    settings = replace(
                        settings,
                        site=replace(
                            settings.site,
                            installation_id=rescued_id or settings.site.installation_id,
                            installation_profile=(
                                rescued_profile or settings.site.installation_profile
                            ),
                        ),
                    )
        write_full_config(settings, config_path, mode=config_mode)
        written.append(str(config_path))

        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, answers.entry_password)
        written.append(str(secret_manager._secret_file(secret_manager.SECRET_ENTRY)))
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, answers.admin_password)
        written.append(str(secret_manager._secret_file(secret_manager.SECRET_ADMIN)))

        return ApplyResult(ok=True, written=written,
                           message="config.yaml and password secrets written")
