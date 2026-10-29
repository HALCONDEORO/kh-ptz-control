# Third-Party Notices

HallPTZ Controls uses the following third-party packages.
Each package is governed by its own licence; this file is provided for awareness only
and does not modify the terms of any upstream licence.

---

## Runtime Dependencies

### PyQt5

- **Purpose:** GUI framework — all windows, widgets and event handling.
- **Upstream project:** https://www.riverbankcomputing.com/software/pyqt/
- **Licence:** GNU General Public Licence v3 (GPL-3.0) for the open-source edition;
  a commercial licence is available from Riverbank Computing.

> **Important for commercial distribution:** PyQt5 is dual-licensed. Distributing
> this application to customers under the GPL-3.0 edition requires that the full
> application source code is also made available under GPL-3.0 terms. If that is
> not acceptable, a commercial PyQt5 licence must be purchased from Riverbank
> Computing before packaging or distributing the software commercially.
> Review this obligation before any customer handover.

### PyQt5-sip

- **Purpose:** SIP binding layer required by PyQt5.
- **Upstream project:** https://pypi.org/project/PyQt5-sip/
- **Licence:** SIP licence (similar to GPL-2.0 or later with an exception for
  generated code); see upstream for full terms.

---

## Optional Dependencies

### PyATEMMax

- **Purpose:** Optional Blackmagic ATEM switcher monitoring.
  Only required when `USE_ATEM=true` and a real ATEM is present.
- **Upstream project:** https://pypi.org/project/PyATEMMax/
- **Licence:** MIT Licence.

---

## Development and Test Dependencies

### pytest

- **Purpose:** Test runner used during development; not included in production deployments.
- **Upstream project:** https://docs.pytest.org/
- **Licence:** MIT Licence.

---

## System-Level Dependencies (Raspberry Pi)

On Raspberry Pi OS the following system packages are installed via `apt` rather than pip.
Their licences apply as distributed by the Raspberry Pi OS package archive.

| Package | Purpose | Licence |
|---------|---------|---------|
| `python3-pyqt5` | PyQt5 runtime | GPL-3.0 |
| `python3-pyqt5.qtsvg` | SVG rendering support | GPL-3.0 |

---

## Notes

- This file is maintained manually. Update it whenever a dependency is added, removed, or upgraded.
- Licence obligations (especially PyQt5/Qt) must be verified against the licence terms in force at the time of each customer deployment.
- This file does not constitute legal advice. Seek qualified legal counsel for jurisdiction-specific requirements.
