"""Prevent documented install commands drifting away from the wrapper contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_guides_use_desktop_user_and_readiness_wrapper():
    for name in ("README.md", "docs/INSTALL_RPI.md", "docs/INSTALL_RPI_ES.md"):
        text = (ROOT / name).read_text()
        assert 'install_khptz_rpi.sh --wizard-user "$USER" --check' in text
        assert '--wizard-user khptz' not in text
        assert 'sudo ./runtime/installer/install.sh' not in text


def test_guides_do_not_claim_pi5_bullseye_or_silent_validator():
    baseline = (ROOT / "docs/RPI_RUNTIME_BASELINE.md").read_text()
    guide = (ROOT / "docs/INSTALL_RPI.md").read_text()
    assert "Requires Bookworm 64-bit (not Bullseye)" in baseline
    assert "Tested target for MVP" not in baseline
    assert "creates a report directory" in guide
    assert "it changes\nnothing on the appliance" not in guide


def test_simulation_commands_use_existing_module_path():
    guide = (ROOT / "docs/INSTALL_RPI.md").read_text()
    assert "python3 sim_mode.py" not in guide
    assert (ROOT / "adapters/sim_mode.py").is_file()


def _uninstall_section() -> str:
    text = (ROOT / "docs/UPDATE_ROLLBACK.md").read_text()
    start = text.find("## Uninstalling")
    assert start != -1, "no uninstall section"
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def test_uninstall_stops_user_gui_before_removing_its_unit():
    """Removing /etc/systemd/user/khptz-gui.service while the user instance
    is active leaves a running GUI with no unit: stop/disable and a user
    daemon-reload must come first."""
    sec = _uninstall_section()
    stop = sec.find("systemctl --user stop khptz-gui.service")
    reload_ = sec.find("systemctl --user daemon-reload")
    rm_unit = sec.find("/etc/systemd/user/khptz-gui.service \\")
    reload_after = sec.find("systemctl --user daemon-reload", rm_unit)
    assert -1 not in (stop, reload_, rm_unit, reload_after)
    assert stop < reload_ < rm_unit < reload_after


def test_uninstall_offers_code_only_variant_that_keeps_data():
    """The keep-data variant must remove the code (/opt/khptz) and name the
    directories it deliberately keeps."""
    sec = _uninstall_section()
    variant = sec.find("Remove the code only")
    assert variant != -1
    assert sec.find("rm -rf /opt/khptz", variant) != -1
    for kept in ("/etc/khptz", "/var/lib/khptz", "/var/backups/khptz"):
        assert sec.find(kept, variant) != -1, f"kept dir not named: {kept}"


def test_uninstall_dev_note_lists_real_dev_paths():
    """Dev installs keep app+config in the checkout but still write data,
    logs and backups outside it - the note must name those paths."""
    sec = _uninstall_section()
    dev = sec.find("--dev")
    assert dev != -1
    note = sec[dev:]
    for path in ("~/.config/khptz", "/var/log/khptz", "/var/backups/khptz"):
        assert path in note, f"dev note misses {path}"


def test_uninstall_removes_repair_artifacts_before_userdel():
    """repair_rpi_runtime.sh adds its own chain: display-ready path/service
    units, a khptz-control.service.d drop-in, a libexec helper and autostart
    entries (current and legacy). All must go BEFORE userdel khptz."""
    sec = _uninstall_section()
    userdel = sec.find("userdel khptz")
    assert userdel != -1
    for artifact in (
        "khptz-display-ready.path",
        "khptz-display-ready.service",
        "khptz-control.service.d",
        "/usr/local/libexec/khptz-display-session",
        "khptz-display-session.desktop",
        "khptz-display-permission.desktop",
        "/etc/tmpfiles.d/khptz.conf",
        "xhost -SI:localuser:khptz",
    ):
        idx = sec.find(artifact)
        assert idx != -1, f"artifact not covered: {artifact}"
        assert idx < userdel, f"artifact removed after userdel: {artifact}"


def test_uninstall_stops_display_chain():
    """The display-ready path unit is enabled --now and its helper re-grants
    xhost at login: stop and disable it, not just delete the files."""
    sec = _uninstall_section()
    stop = sec.find("systemctl stop")
    disable = sec.find("systemctl disable")
    rm_units = sec.find("khptz-display-ready.path \\")
    assert "khptz-display-ready.path" in sec[stop:stop + 300]
    assert "khptz-display-ready.path" in sec[disable:disable + 300]
    assert stop < rm_units


def test_uninstall_code_only_variant_warns_about_dangling_entries():
    """Removing only /opt/khptz leaves autostarts and the launcher pointing
    at a missing tree; khptz-gui has no [Install] but its autostart starts
    it anyway - the doc must say so."""
    sec = _uninstall_section()
    variant = sec.find("Remove the code only")
    full = sec.find("Full removal")
    assert -1 not in (variant, full) and variant < full
    block = sec[variant:full]
    assert "autostart" in block
    assert "[Install]" in block
    assert "/usr/local/bin/khptz" in block


def test_golden_image_uses_product_install_flow():
    text = (ROOT / "docs/RPI_GOLDEN_IMAGE.md").read_text()
    assert "HALCONDEORO/kh-ptz-control.git" in text
    assert "legacy-ptz-controller" not in text
    assert 'install_khptz_rpi.sh --wizard-user "$USER" --check' in text
    assert 'install_khptz_rpi.sh --wizard-user "$USER"' in text
    assert "sudo bash runtime/installer/install.sh" not in text
    for package in ("git", "rsync", "python3-pyqt5", "python3-pyqt5.qtsvg",
                    "python3-yaml", "x11-xserver-utils"):
        assert package in text
    for path in ("/opt/khptz/", "/etc/khptz/", "/var/lib/khptz/",
                 "/var/log/khptz/", "/var/backups/khptz/"):
        assert path in text
    assert "khptz setup" in text
    assert "sudo chown -R" not in text
    assert "sudo pip3 install" not in text
    assert "unprovisioned" in text


def test_offline_install_preparation_is_documented():
    """A hall with no WAN cannot apt/pip/git-fetch on site. The EN guide must
    carry a preparation section, and it must not overstate the installer:
    python3-yaml is a hard readiness FAIL while x11-xserver-utils only WARNs
    (the wizard apt-installs it later, which breaks offline). The session
    check must inspect Name/Active/Type like the golden-image checklist, and
    the offline guarantee must be scoped to the stock product."""
    en = (ROOT / "docs/INSTALL_RPI.md").read_text()
    es = (ROOT / "docs/INSTALL_RPI_ES.md").read_text()
    assert "## Sites without internet access (offline installs)" in en
    start = en.index("## Sites without internet access")
    end = en.index("## 1. Choose the reviewed build")
    section = en[start:end]
    assert "x11-xserver-utils" in section and "python3-yaml" in section
    # Severity must be accurate: only WARN for xhost, FAIL for python3-yaml.
    assert "the readiness check FAILs without it" in section
    assert "the readiness check only WARNs" in section
    assert "everything after this point works without WAN" not in section
    assert "stock product flow works without WAN" in section
    assert "--dev" in section and "ATEM" in section
    assert "requirements-rpi.txt" in section
    # Session verification matches the golden-image checklist (RPI_GOLDEN_IMAGE).
    assert "loginctl show-session <session-id> -p Name -p Active -p Type" in section
    assert "Active=yes" in section and "Type=x11" in section
    assert "git status --ignored" in section
    for needle in ("x11-xserver-utils", "python3-yaml",
                   "loginctl show-session <id> -p Name -p Active -p Type",
                   "git status --ignored"):
        assert needle in es


def test_dark_screen_troubleshooting_names_the_wayland_remedy():
    """A dark screen after login can be a Wayland session - a possibility to
    check first, not a proven frequency claim. Both guides must point at the
    session-type check (Name/Active/Type) and the raspi-config X11 remedy,
    without claiming unmerged tooling already logs it."""
    en = (ROOT / "docs/INSTALL_RPI.md").read_text()
    es = (ROOT / "docs/INSTALL_RPI_ES.md").read_text()
    start = en.find("### The GUI never appears after login (dark screen)")
    assert start != -1
    section = en[start:start + 1100]
    assert "Most often" not in section
    assert "possible cause" in section
    assert "-p Name -p Active -p Type" in section
    assert "raspi-config" in section and "Type=wayland" in section
    # Only the merged readiness check may be cited as logging the remedy.
    assert "acceptance validator all log" not in section
    assert "pantalla oscura" in es
    assert "raspi-config" in es and "loginctl" in es


def test_update_guide_requires_explicit_off_device_backup():
    """install.sh now takes the pre-update backup automatically: the guide must
    say so, name the guard flag, and still require a copy off the Pi."""
    text = (ROOT / "docs/UPDATE_ROLLBACK.md").read_text()
    before = text[text.index("## Before any update"):text.index("## Rollback")]
    assert "`runtime/installer/install.sh` creates a pre-update backup automatically" in before
    assert "install-state.env" in before
    assert "--skip-pre-update-backup" in before
    assert "copy the resulting" in before and "ZIP off the Pi" in before
    assert "A data ZIP is not an SD-card image" in before
    assert "it does not undo data-format changes" in before
