#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Raspberry Pi-specific wizard page refinements.

The generic page module remains UI-only and reusable. These subclasses add the
real-device warnings learned from the first Pi installation without moving any
privileged work into the desktop process.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from application.install_verification import verify_provisioned
from domain.network_validation import is_valid_ipv4
from ui.setup_wizard.pages import DonePage as _DonePage
from ui.setup_wizard.pages import OptionalPage as _OptionalPage
from ui.styles import WARNING, error_label_qss, success_label_qss


class OptionalPage(_OptionalPage):
    """Validate ATEM input early and explain the network-profile advisory."""

    def __init__(self, wizard):
        super().__init__(wizard)
        layout = self.layout()

        self._atem_error = QLabel("")
        self._atem_error.setWordWrap(True)
        self._atem_error.setStyleSheet(error_label_qss())
        layout.insertWidget(max(0, layout.count() - 1), self._atem_error)

        self._network_notice = QLabel("")
        self._network_notice.setWordWrap(True)
        self._network_notice.setStyleSheet(
            f"color: {WARNING}; font-size: 11px; font-family: 'Inter Tight';"
        )
        layout.insertWidget(max(0, layout.count() - 1), self._network_notice)

        self.atem_enabled.toggled.connect(self._refresh_notices)
        self.atem_ip.textChanged.connect(self._refresh_notices)
        self.profile.currentIndexChanged.connect(self._refresh_notices)
        self._refresh_notices()

    def _refresh_notices(self, *_args) -> None:
        enabled = self.atem_enabled.isChecked()
        ip = self.atem_ip.text().strip()
        # Same rule as validatePage, shown live so the operator is not stopped
        # only once they press Next.
        if enabled and not ip:
            self._atem_error.setText(
                "ATEM is enabled. Enter its IP address before continuing."
            )
        elif enabled and not is_valid_ipv4(ip):
            self._atem_error.setText(
                f"'{ip}' is not a valid IPv4 address."
            )
        else:
            self._atem_error.setText("")

        profile = self.profile.currentData()
        if profile == "flat_lan":
            self._network_notice.setText(
                "Flat LAN works for testing. An isolated AV VLAN is recommended "
                "for a production installation."
            )
        elif profile == "unknown":
            self._network_notice.setText(
                "Network profile is not confirmed. Choose the real layout before "
                "production handover."
            )
        else:
            self._network_notice.setText("")

    def validatePage(self) -> bool:
        """Refresh the live notices, then defer to the base IPv4 validation.

        The base page rejects a malformed address as well as a blank one and
        owns the inline error text, so this must delegate rather than reimplement
        an emptiness check — doing the latter let "999.1.1" through the wizard.
        """
        self._refresh_notices()
        return super().validatePage()


class DonePage(_DonePage):
    """Use parser-safe status styling and include Pi integration advisories."""

    def initializePage(self) -> None:
        verdict = verify_provisioned()
        self._verdict.setText(verdict.summary())
        if verdict.ok:
            self._verdict.setStyleSheet(success_label_qss(font_px=13))
        else:
            self._verdict.setStyleSheet(error_label_qss(font_px=13))
            self._verdict.setText(
                verdict.summary() + "\nRun 'khptz doctor' to diagnose."
            )
