# Hall PTZ Control — Configuration Policy

## What is committed to this repository

| Path | Description | Committed? |
|------|-------------|-----------|
| `config/defaults/starter.yaml` | Template for starter installs | Yes — safe template |
| `config/defaults/standard.yaml` | Template for standard installs | Yes — safe template |
| `config/defaults/demo.yaml` | Demo mode config template | Yes — safe template |
| `config/examples/starter_1_camera.yaml` | Example: 1 camera, isolated AV VLAN | Yes — safe example |
| `config/examples/standard_2_camera.yaml` | Example: 2 cameras + ATEM | Yes — safe example |
| `config/examples/flat_lan_with_warning.yaml` | Example: flat LAN (produces WARNING) | Yes — safe example |
| `tests/fixtures/config/minimal_valid.yaml` | Minimal test fixture | Yes — safe test data |
| `config.yaml` | Real site configuration | **NEVER — gitignored** |

## Rules for committed config files

All committed config files (templates, examples, fixtures) must use:

- **Fake site/customer names** — "Example Venue A", "Test Venue", etc.
- **Private RFC1918 example IPs** — 192.168.30.x, 172.16.x.x (avoid 192.168.1.x which is
  commonly a real LAN range)
- **Fake installation IDs** — `hallptz-2026-EXAMPLE`, `hallptz-2026-TEST`
- **No real passwords, tokens or keys**
- **No real customer names, phone numbers or emails**
- **No real network details from actual customer sites**

## Where real customer configs belong

Real `config.yaml` files must:

1. Be stored on the customer's Raspberry Pi, not in this repository.
2. Be backed up via `hallptz backup` to a secure, private location.
3. Never be committed, pushed, shared or attached to support tickets in raw form.

The real `config.yaml` is gitignored at the project root (see `.gitignore`).

## Secret scanning

This repository does not have automated secret scanning configured as a CI gate.
Until one is added, follow these manual rules before every commit:

- Never commit `config.yaml`, `PTZ1IP.txt`, `PTZ2IP.txt`, `ATEMIP.txt`, `Contact.txt`
  or any file with real customer data.
- Use `hallptz support-bundle` (when available) to create redacted snapshots for support.
- If a secret is accidentally committed, treat it as compromised and rotate it.

## How to set up a new installation

1. Copy `config/examples/starter_1_camera.yaml` or `config/examples/standard_2_camera.yaml`
   to the project root as `config.yaml`.
2. Replace all example values with real site values.
3. Run `hallptz doctor` to verify the config.
4. Run `hallptz known-good mark` after a successful doctor pass.
5. The real `config.yaml` will never be tracked by git.

## Test fixtures

Tests that need a valid config file should:

- Use `tests/fixtures/config/minimal_valid.yaml` via `tmp_path` copy, or
- Build a minimal in-memory dict and write it to `tmp_path / "config.yaml"`.

Tests must not read from the real project-root `config.yaml` or any customer config.

---

*See also: docs/NETWORK_ARCHITECTURE.md, docs/RUNTIME_PATH_CONTRACT.md,
docs/SUPPORT_BUNDLE_CONTRACT.md*
