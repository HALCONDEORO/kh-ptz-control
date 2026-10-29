#!/usr/bin/env python3
"""Product-only setup migration guard tests."""
from pathlib import Path

from runtime.setup_launcher import setup_wizard_needed


class _ProductResolver:
    config_dir = Path("/etc/khptz")

    def __init__(self, root: Path):
        self.provisioned_marker_file = root / ".provisioned"
        self.rpi_integration_marker_file = root / ".rpi-integrated"


def test_provisioned_product_without_integration_needs_wizard(tmp_path):
    resolver = _ProductResolver(tmp_path)
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    assert setup_wizard_needed(resolver) is True


def test_fully_integrated_product_self_suppresses_wizard(tmp_path):
    resolver = _ProductResolver(tmp_path)
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    resolver.rpi_integration_marker_file.write_text("ok\n", encoding="utf-8")
    assert setup_wizard_needed(resolver) is False


def test_force_always_opens_product_wizard(tmp_path):
    resolver = _ProductResolver(tmp_path)
    assert setup_wizard_needed(resolver, force=True) is True

