#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""ui/setup_wizard/pages.py — QWizardPage screens for the touchscreen setup wizard.

Each page reads the shared ProvisioningAnswers held by the wizard, lets the
operator edit it, and writes it back in collect() (called from validatePage so
edits are captured whenever Next/Finish is pressed). Validation errors are shown
inline (no modal dialogs) so the flow stays touch-friendly and unit-testable.

All product use cases live in application.ProvisioningService — these pages only
collect input and display results; they never write files or touch hardware.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from domain.network_validation import is_valid_ipv4
from ui.styles import SECONDARY, SUCCESS, error_label_qss


class _BasePage(QWizardPage):
    """Shared base: exposes the wizard's answers and a collect() hook."""

    def __init__(self, wizard):
        super().__init__()
        self._wiz = wizard

    @property
    def answers(self):
        return self._wiz.answers

    def collect(self) -> None:
        """Write this page's widget state into the shared answers. Override."""

    def validatePage(self) -> bool:  # QWizard hook — fires on Next/Finish
        self.collect()
        return True


class AdminAuthPage(_BasePage):
    """Collect the current admin password before Repair proceeds.

    Shown ONLY when re-opening an already-provisioned install (``hallptz setup
    --force``): without it, anyone with access to the wizard user's desktop
    session could open the menu icon and reconfigure cameras/network, or reset
    both passwords, via the password-free /run/hallptz provisioning channel —
    with no proof they know the current admin password.

    The password is NOT verified here. This page's process (the wizard
    user's desktop session) has no reliable way to read the hallptz:hallptz-owned
    encrypted admin secret to check it itself — verifying client-side would
    either always reject a correct password on a real install, or give false
    confidence. It is collected into ``answers.current_admin_password`` and
    verified by the privileged provisioning oneshot
    (``runtime.provision.run_provision``), which can actually decrypt the
    secret; a wrong password surfaces as a failure on the Installing page.
    """

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Administrator sign-in")
        self.setSubTitle("Enter the administrator password to reconfigure this room")

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        form.addRow("Administrator password", self._password)
        lay.addLayout(form)
        lay.addStretch()

    def collect(self) -> None:
        self.answers.current_admin_password = self._password.text()


class WelcomePage(_BasePage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Welcome")
        self.setSubTitle("Set up this room")
        lay = QVBoxLayout(self)
        msg = QLabel(
            "This assistant gets the room ready in a few minutes.\n"
            "Every screen is pre-filled — you can just tap Next."
        )
        msg.setWordWrap(True)
        lay.addWidget(msg)
        lay.addStretch()


class DeviceCheckPage(_BasePage):
    """Readiness gate: blocks Next while any preflight check is blocking."""

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Device check")
        self.setSubTitle("Making sure the device is ready")
        lay = QVBoxLayout(self)
        self._results = QLabel("")
        self._results.setWordWrap(True)
        self._results.setTextFormat(Qt.PlainText)
        lay.addWidget(self._results)
        lay.addStretch()
        self._checks = []

    def initializePage(self) -> None:
        from application.preflight import run_preflight
        self._checks = run_preflight()
        lines = []
        for c in self._checks:
            mark = "OK" if c.ok else ("WARN" if c.warn_only else "FAIL")
            lines.append(f"[{mark}] {c.label}: {c.detail}")
        self._results.setText("\n".join(lines))
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        from application.preflight import has_blocking
        return not has_blocking(self._checks)


class RoomDetailsPage(_BasePage):
    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Room details")
        self.setSubTitle("Identify this installation")
        form = QFormLayout(self)
        self.name = QLineEdit(self.answers.site_name)
        self.contact = QLineEdit(self.answers.site_contact)
        form.addRow("Room name", self.name)
        form.addRow("Support contact", self.contact)

    def collect(self) -> None:
        self.answers.site_name = self.name.text().strip() or "My Venue"
        self.answers.site_contact = self.contact.text().strip() or "IT Support"


class CamerasPage(_BasePage):
    """One editable group per camera: name, IP and VISCA id.

    Cameras can be added and removed here. Without that, the wizard could only
    ever configure the cameras that were already in config.yaml — and the
    installer seeds the one-camera starter template, so a two-camera room (the
    product's normal shape: `platform` for the first seats, `comments` for the
    rest) was unreachable through setup or repair, and /etc/hallptz is not
    editable from the desktop session either.
    """

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Cameras")
        self.setSubTitle("Add one entry per camera in the room")

        lay = QVBoxLayout(self)
        self._rows = []
        self._boxes = []

        # The camera boxes live inside a scroll area so adding several cameras
        # keeps them stacked and scrollable instead of overflowing the page
        # (previously they piled up with no way to reach the lower ones or the
        # Next button on the fixed-height touchscreen).
        self._cameras_area = QVBoxLayout()
        self._cameras_area.setContentsMargins(0, 0, 0, 0)
        # Trailing stretch keeps the camera boxes packed at the top of the
        # scroll viewport; new boxes are inserted just before it in _rebuild.
        self._cameras_area.addStretch()
        cams_container = QWidget()
        cams_container.setLayout(self._cameras_area)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(cams_container)
        lay.addWidget(scroll, stretch=1)

        self._add_button = QPushButton("Add camera")
        self._add_button.clicked.connect(self._on_add)
        lay.addWidget(self._add_button)

        self._error = QLabel("")
        self._error.setStyleSheet(error_label_qss())
        self._error.setWordWrap(True)
        lay.addWidget(self._error)

        self._rebuild()

    # ── rendering ────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        """Redraw one group box per camera in the shared answers."""
        for box in self._boxes:
            self._cameras_area.removeWidget(box)
            box.setParent(None)
            box.deleteLater()
        self._boxes = []
        self._rows = []

        removable = len(self.answers.cameras) > 1
        for index, cam in enumerate(self.answers.cameras):
            box = QGroupBox(cam.name.strip() or cam.role.replace("_", " ").title())
            form = QFormLayout(box)
            name = QLineEdit(cam.name)
            ip = QLineEdit(cam.ip)
            visca = QLineEdit(cam.visca_id)
            form.addRow("Name", name)
            form.addRow("IP address", ip)
            form.addRow("VISCA id", visca)
            if removable:
                remove = QPushButton("Remove this camera")
                # default=index binds the current value, not the loop variable.
                remove.clicked.connect(lambda _checked=False, i=index: self._on_remove(i))
                form.addRow(remove)
            # Insert before the trailing stretch so boxes stay top-aligned.
            self._cameras_area.insertWidget(self._cameras_area.count() - 1, box)
            self._boxes.append(box)
            self._rows.append((cam, name, ip, visca))

    # ── add / remove ─────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        # Capture in-progress edits first — rebuilding replaces the widgets, so
        # anything typed and not yet collected would otherwise be discarded.
        self.collect()
        from application.provisioning_service import next_camera_answer
        self.answers.cameras.append(next_camera_answer(self.answers.cameras))
        self._error.setText("")
        self._rebuild()
        self.completeChanged.emit()

    def _on_remove(self, index: int) -> None:
        self.collect()
        if len(self.answers.cameras) <= 1:
            # Belt and braces: the button is not rendered in this case, and
            # ProvisioningService.validate() rejects an empty camera list.
            self._error.setText("At least one camera is required.")
            return
        if 0 <= index < len(self.answers.cameras):
            del self.answers.cameras[index]
        self._error.setText("")
        self._rebuild()
        self.completeChanged.emit()

    # ── collection ───────────────────────────────────────────────────────────

    def collect(self) -> None:
        for cam, name, ip, visca in self._rows:
            cam.name = name.text().strip()
            cam.ip = ip.text().strip()
            cam.visca_id = visca.text().strip()


class OptionalPage(_BasePage):
    """Optional hardware and network — safe to leave at the defaults."""

    _PROFILES = [
        ("flat_lan", "Flat LAN — fits most installs"),
        ("isolated_av_vlan", "Isolated AV VLAN"),
        ("unknown", "Not sure — decide later"),
    ]

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Optional hardware & network")
        self.setSubTitle("Both are optional — defaults work fine")
        lay = QVBoxLayout(self)

        atem_box = QGroupBox("ATEM video switcher")
        atem_form = QFormLayout(atem_box)
        self.atem_enabled = QCheckBox("Use an ATEM switcher")
        self.atem_enabled.setChecked(self.answers.atem_enabled)
        self.atem_ip = QLineEdit(self.answers.atem_ip)
        atem_form.addRow(self.atem_enabled)
        atem_form.addRow("ATEM IP", self.atem_ip)
        lay.addWidget(atem_box)

        net_box = QGroupBox("Network profile")
        net_form = QFormLayout(net_box)
        self.profile = QComboBox()
        for value, label in self._PROFILES:
            self.profile.addItem(label, value)
        self._select_profile(self.answers.network_profile)
        net_form.addRow("Profile", self.profile)
        lay.addWidget(net_box)

        self._error = QLabel("")
        self._error.setStyleSheet(error_label_qss())
        self._error.setWordWrap(True)
        lay.addWidget(self._error)
        lay.addStretch()

    def _select_profile(self, value: str) -> None:
        idx = self.profile.findData(value)
        self.profile.setCurrentIndex(idx if idx >= 0 else 0)

    def collect(self) -> None:
        self.answers.atem_enabled = self.atem_enabled.isChecked()
        # Assigned verbatim: falling back to the previous value when the field
        # is cleared made "ATEM on, IP blank" invisible to validation (#886).
        self.answers.atem_ip = self.atem_ip.text().strip()
        self.answers.network_profile = self.profile.currentData()

    def error_text(self) -> str:
        return self._error.text()

    def validatePage(self) -> bool:
        """Block Next when ATEM is on but unreachable by configuration."""
        self.collect()
        if self.answers.atem_enabled and not is_valid_ipv4(self.answers.atem_ip):
            detail = "Enter the ATEM switcher IP address" if not self.answers.atem_ip \
                else "That is not a valid IPv4 address"
            self._error.setText(f"{detail}, or clear “Use an ATEM switcher”.")
            self.atem_ip.setFocus()
            self.atem_ip.selectAll()
            return False
        self._error.setText("")
        return True


class PasswordsPage(_BasePage):
    """Two independent passwords: entry (operator) and administrator."""

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Passwords")
        self.setSubTitle("Two roles, two separate logins — both are required")
        lay = QVBoxLayout(self)

        entry_box = QGroupBox("Operator")
        entry_form = QFormLayout(entry_box)
        self.entry = self._pw_field()
        self.entry_confirm = self._pw_field()
        entry_form.addRow("Password", self.entry)
        entry_form.addRow("Confirm", self.entry_confirm)
        lay.addWidget(entry_box)

        admin_box = QGroupBox("Administrator")
        admin_form = QFormLayout(admin_box)
        self.admin = self._pw_field()
        self.admin_confirm = self._pw_field()
        admin_form.addRow("Password", self.admin)
        admin_form.addRow("Confirm", self.admin_confirm)
        lay.addWidget(admin_box)

        self._error = QLabel("")
        self._error.setStyleSheet(error_label_qss())
        self._error.setWordWrap(True)
        lay.addWidget(self._error)
        lay.addStretch()

    @staticmethod
    def _pw_field() -> QLineEdit:
        f = QLineEdit()
        f.setEchoMode(QLineEdit.Password)
        return f

    def collect(self) -> None:
        self.answers.entry_password = self.entry.text()
        self.answers.admin_password = self.admin.text()

    def error_text(self) -> str:
        return self._error.text()

    def validatePage(self) -> bool:
        if not self.entry.text():
            return self._fail("Enter an operator password.")
        if self.entry.text() != self.entry_confirm.text():
            return self._fail("The operator passwords do not match.")
        if not self.admin.text():
            return self._fail("Enter an administrator password.")
        if self.admin.text() != self.admin_confirm.text():
            return self._fail("The administrator passwords do not match.")
        if self.entry.text() == self.admin.text():
            return self._fail("Use different passwords for operator and administrator.")
        self._error.setText("")
        self.collect()
        return True

    def _fail(self, message: str) -> bool:
        self._error.setText(message)
        return False


class ReviewPage(_BasePage):
    """Read-only summary built from ProvisioningService.plan() and validate()."""

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Review")
        self.setSubTitle("Nothing is written until you confirm")
        lay = QVBoxLayout(self)
        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.PlainText)
        lay.addWidget(self._summary)
        self._issues = QLabel("")
        self._issues.setStyleSheet(error_label_qss())
        self._issues.setWordWrap(True)
        lay.addWidget(self._issues)
        # Advisories are deployment advice, not errors — styled and worded
        # separately so an operator can tell "this will not work" from
        # "this works, but consider hardening it" (#886).
        self._advisories = QLabel("")
        self._advisories.setStyleSheet(f"color: {SECONDARY}; font-size: 11px;")
        self._advisories.setWordWrap(True)
        lay.addWidget(self._advisories)
        lay.addStretch()

    def initializePage(self) -> None:
        svc = self._wiz.service
        issues = svc.validate(self.answers)
        plan = svc.plan(self.answers)
        lines = [f"• {a.kind}: {a.detail}" for a in plan.artifacts]
        self._summary.setText("Will be created:\n" + "\n".join(lines))
        if issues:
            self._issues.setText(
                "Fix before installing:\n"
                + "\n".join(
                    f"• {i.message}" + (f" — {i.remediation}" if i.remediation else "")
                    for i in issues
                )
            )
        else:
            self._issues.setText("")

        advisories = svc.advisories(self.answers)
        if advisories:
            self._advisories.setText(
                "Recommended, not required:\n"
                + "\n".join(
                    f"• {a.message}" + (f" — {a.remediation}" if a.remediation else "")
                    for a in advisories
                )
            )
        else:
            self._advisories.setText("")

    def advisory_text(self) -> str:
        return self._advisories.text()

    def issue_text(self) -> str:
        return self._issues.text()

    def isComplete(self) -> bool:
        # Block Finish while validation issues remain.
        return not self._wiz.service.validate(self.answers)


class InstallingPage(_BasePage):
    """Hands the answers to the privileged provisioner and waits for the result.

    The wizard runs unprivileged; the OS work (write /etc/hallptz, enable the
    service) happens in the hallptz-provision oneshot. This page drops the request
    via ProvisionHandoff and polls for the result with a QTimer so the
    touchscreen stays responsive — it never blocks the UI thread. Next stays
    disabled until provisioning actually succeeds; on failure the operator goes
    Back to correct the settings and retries.
    """

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Installing")
        self.setSubTitle("Applying your settings — this only takes a moment")
        lay = QVBoxLayout(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.PlainText)
        lay.addWidget(self._status)
        lay.addStretch()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        self._result = None
        self._done = False

    def initializePage(self) -> None:
        self._result = None
        self._done = False
        self._status.setText("Installing… please wait.")
        self.completeChanged.emit()
        handoff = self._wiz.handoff

        # begin() writes the request into /run/hallptz, which the desktop user
        # cannot create itself. install.sh deliberately tolerates
        # `systemd-tmpfiles --create` failing ("/run/hallptz will be created on
        # next boot"), so an operator who opens the wizard before rebooting hits
        # an OSError here. Unhandled, that propagates out of a Qt slot and takes
        # the whole wizard down instead of explaining what to do.
        try:
            handoff.begin(self.answers)
        except OSError as exc:
            from application.provision_handoff import HandoffResult

            self._apply_result(HandoffResult(
                ok=False,
                error=(
                    f"Could not reach the provisioning channel ({exc}). "
                    "This usually means the device has not been rebooted since "
                    "installation. Reboot and run setup again."
                ),
            ))
            return

        self._timer.start(max(1, int(handoff.poll_interval_s * 1000)))

    def _poll_once(self) -> None:
        result = self._wiz.handoff.poll()
        if result is None:
            return
        self._timer.stop()
        self._apply_result(result)

    def _apply_result(self, result) -> None:
        self._result = result
        self._done = True
        self._status.setText(result.summary())
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done and self._result is not None and self._result.ok

    def cleanupPage(self) -> None:  # QWizard hook when Back is pressed
        self._timer.stop()


class DonePage(_BasePage):
    """Final screen: independently verifies the install before declaring success."""

    def __init__(self, wizard):
        super().__init__(wizard)
        self.setTitle("Done")
        self.setSubTitle("Installed and running")
        lay = QVBoxLayout(self)
        self._verdict = QLabel("")
        self._verdict.setWordWrap(True)
        self._verdict.setTextFormat(Qt.PlainText)
        lay.addWidget(self._verdict)
        msg = QLabel(
            "The room is ready. All local files are created and the service "
            "starts on every reboot. Reconfigure later via the HALLPTZ Setup icon."
        )
        msg.setWordWrap(True)
        lay.addWidget(msg)
        lay.addStretch()

    def initializePage(self) -> None:
        from application.install_verification import verify_provisioned
        verdict = verify_provisioned()
        self._verdict.setText(verdict.summary())
        # A missing marker means the privileged step did not finish cleanly;
        # point the operator at the diagnostic rather than implying all is well.
        if not verdict.ok:
            self._verdict.setStyleSheet(error_label_qss(font_px=13))
            self._verdict.setText(
                verdict.summary() + "\nRun 'hallptz doctor' to diagnose."
            )
        else:
            self._verdict.setStyleSheet(f"color: {SUCCESS}; font: 600 13px 'Inter Tight', 'Segoe UI';")
