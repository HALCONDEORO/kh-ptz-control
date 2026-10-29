#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Touchscreen setup wizard shell.

The wizard collects input only. Configuration files and privileged Raspberry Pi
integration are applied by the provisioning service/path-unit after confirmation.
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QWizard

from application.provision_handoff import ProvisionHandoff
from application.provisioning_service import ProvisioningAnswers, ProvisioningService
from runtime.path_resolver import RuntimePathResolver
from ui.styles import apply_stylesheet_safely, setup_wizard_qss
from ui.setup_wizard.pages import (
    AdminAuthPage,
    CamerasPage,
    DeviceCheckPage,
    InstallingPage,
    PasswordsPage,
    ReviewPage,
    RoomDetailsPage,
    WelcomePage,
)
from ui.setup_wizard.rpi_pages import DonePage, OptionalPage


class SetupWizard(QWizard):
    """Guided first-run or repair setup."""

    def __init__(
        self,
        answers: Optional[ProvisioningAnswers] = None,
        service: Optional[ProvisioningService] = None,
        handoff: Optional[ProvisionHandoff] = None,
        parent=None,
        *,
        require_admin_auth: bool = False,
    ) -> None:
        super().__init__(parent)
        self.answers = answers if answers is not None else ProvisioningAnswers()
        self.service = service or ProvisioningService()
        self.handoff = handoff or self._default_handoff()

        self.setWindowTitle("KHPTZ Setup")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        apply_stylesheet_safely(self, setup_wizard_qss())

        if require_admin_auth:
            self.addPage(AdminAuthPage(self))

        self.addPage(WelcomePage(self))
        self.addPage(DeviceCheckPage(self))
        self.addPage(RoomDetailsPage(self))
        self.addPage(CamerasPage(self))
        self.addPage(OptionalPage(self))
        self.addPage(PasswordsPage(self))
        self.addPage(ReviewPage(self))
        self.addPage(InstallingPage(self))
        self.addPage(DonePage(self))

    @staticmethod
    def _default_handoff() -> ProvisionHandoff:
        """Build the production handoff over the /run/khptz channel.

        Raspberry Pi finalisation may install xhost and wait for the desktop
        display on a slow SD card/network, so stay above the provision service's
        600-second timeout while keeping an eventual operator-visible failure.
        """
        resolver = RuntimePathResolver()
        return ProvisionHandoff(
            resolver.provision_request_file,
            resolver.provision_result_file,
            timeout_s=660.0,
        )

    def collected_answers(self) -> ProvisioningAnswers:
        return self.answers
