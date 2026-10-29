#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests unitarios para descubrimiento de camaras sin tocar la red real.
"""

from types import SimpleNamespace

import application.camera_discovery as cd


class TestCameraSubnet:

    def test_get_camera_subnet_uses_first_three_octets(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="172.16.1.11"))

        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_falls_back_on_invalid_ip_shape(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="not-an-ip"))

        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_rejects_out_of_range_octets(self, monkeypatch):
        # "999.abc.1.2" has 4 parts but is not a valid IPv4 — old code would
        # produce "999.abc.1", new code falls back to default (#141)
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="999.abc.1.2"))
        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_rejects_alpha_octets(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="10.abc.1.2"))
        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_falls_back_on_empty_string(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip=""))
        assert cd.get_camera_subnet() == "172.16.1"

    def test_get_camera_subnet_different_valid_subnet(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="10.0.1.50"))
        assert cd.get_camera_subnet() == "10.0.1"

    def test_get_camera_subnet_uses_default_constant(self):
        assert cd._DEFAULT_SUBNET == "172.16.1"


class TestArpScan:

    def test_arp_scan_parses_matching_unique_ips_and_skips_broadcast(self, monkeypatch):
        stdout = """
Interface: 172.16.1.10 --- 0x8
  Internet Address      Physical Address      Type
  172.16.1.11           aa-bb-cc-dd-ee-01     dynamic
  172.16.1.12           aa-bb-cc-dd-ee-02     dynamic
  172.16.1.12           aa-bb-cc-dd-ee-02     dynamic
  172.16.1.255          ff-ff-ff-ff-ff-ff     static
  10.0.0.5              aa-bb-cc-dd-ee-03     dynamic
"""

        def fake_run(*_args, **_kwargs):
            return SimpleNamespace(stdout=stdout)

        monkeypatch.setattr(cd.subprocess, "run", fake_run)

        assert cd.arp_scan("172.16.1") == ["172.16.1.11", "172.16.1.12"]

    def test_arp_scan_ignores_interface_headers_and_deduplicates(self, monkeypatch):
        stdout = """
Interface: 172.16.1.10 --- 0x8
  Internet Address      Physical Address      Type
  172.16.1.20           aa-bb-cc-dd-ee-20     dynamic
  172.16.1.20           aa-bb-cc-dd-ee-20     dynamic
Interface: 172.16.1.254 --- 0x9
  Internet Address      Physical Address      Type
  172.16.1.21           aa-bb-cc-dd-ee-21     dynamic
  172.16.2.22           aa-bb-cc-dd-ee-22     dynamic
"""

        monkeypatch.setattr(cd.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=stdout))

        assert cd.arp_scan("172.16.1") == ["172.16.1.20", "172.16.1.21"]
    def test_arp_scan_returns_empty_on_subprocess_error(self, monkeypatch):
        def fake_run(*_args, **_kwargs):
            raise OSError("arp unavailable")

        monkeypatch.setattr(cd.subprocess, "run", fake_run)

        assert cd.arp_scan("172.16.1") == []


class _FakeSocket:
    open_hosts = set()

    def __init__(self, *_args, **_kwargs):
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        host, _port = address
        return 0 if host in self.open_hosts else 1


class _PortAwareSocket:
    """Fake socket that only reports a host open on a specific port."""

    open_on = {}  # host -> port

    def __init__(self, *_args, **_kwargs):
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        host, port = address
        return 0 if self.open_on.get(host) == port else 1


class TestTcpScan:

    def test_tcp_scan_returns_sorted_open_hosts(self, monkeypatch):
        _FakeSocket.open_hosts = {"172.16.1.7", "172.16.1.3"}
        monkeypatch.setattr(cd.socket, "socket", _FakeSocket)

        assert cd.tcp_scan("172.16.1", workers=1, timeout=0.01) == ["172.16.1.3", "172.16.1.7"]

    def test_tcp_scan_uses_supplied_port(self, monkeypatch):
        # Host is only open on port 9910; a default-port (VISCA) scan must miss it.
        _PortAwareSocket.open_on = {"172.16.1.50": 9910}
        monkeypatch.setattr(cd.socket, "socket", _PortAwareSocket)

        assert cd.tcp_scan("172.16.1", workers=1, timeout=0.01) == []
        assert cd.tcp_scan("172.16.1", workers=1, timeout=0.01, port=9910) == ["172.16.1.50"]


class TestDiscoverAtemSwitchers:

    def test_discover_atem_scans_control_port_on_camera_subnet(self, monkeypatch):
        calls = {}

        def fake_tcp_scan(subnet, port=cd.VISCA_PORT):
            calls["subnet"] = subnet
            calls["port"] = port
            return ["172.16.1.10"]

        monkeypatch.setattr(cd, "tcp_scan", fake_tcp_scan)

        assert cd.discover_atem_switchers("172.16.1") == ["172.16.1.10"]
        assert calls["port"] == cd.ATEM_PORT == 9910
        assert calls["subnet"] == "172.16.1"

    def test_discover_atem_defaults_to_camera_subnet(self, monkeypatch):
        monkeypatch.setattr(cd, "CAM1", SimpleNamespace(ip="10.0.5.11"))
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet, port=cd.VISCA_PORT: [subnet])

        assert cd.discover_atem_switchers() == ["10.0.5"]


class TestDiscoverCameras:

    def test_discover_cameras_includes_arp_only_if_tcp_validates(self, monkeypatch):
        """ARP candidate 172.16.1.13 is included only when _tcp_connect returns True."""
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: ["172.16.1.11", "172.16.1.12"])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.12", "172.16.1.13"])
        monkeypatch.setattr(cd, "_tcp_connect", lambda ip, **kw: ip == "172.16.1.13")

        assert cd.discover_cameras("172.16.1") == ["172.16.1.11", "172.16.1.12", "172.16.1.13"]

    def test_discover_cameras_excludes_arp_only_that_fail_tcp(self, monkeypatch):
        """ARP-only IP rejected when _tcp_connect returns False — prevents false positives (#190)."""
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: ["172.16.1.11"])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.11", "172.16.1.99"])
        monkeypatch.setattr(cd, "_tcp_connect", lambda ip, **kw: False)

        assert cd.discover_cameras("172.16.1") == ["172.16.1.11"]

    def test_discover_cameras_does_not_revalidate_tcp_confirmed_ips(self, monkeypatch):
        """IPs already confirmed by tcp_scan must not be passed to _tcp_connect again."""
        validated = []
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: ["172.16.1.11"])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.11"])
        monkeypatch.setattr(cd, "_tcp_connect", lambda ip, **kw: validated.append(ip) or True)

        cd.discover_cameras("172.16.1")
        assert "172.16.1.11" not in validated

    def test_discover_cameras_result_is_sorted(self, monkeypatch):
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: ["172.16.1.20"])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.5"])
        monkeypatch.setattr(cd, "_tcp_connect", lambda ip, **kw: True)

        result = cd.discover_cameras("172.16.1")
        assert result == sorted(result)

    def test_discover_cameras_empty_when_nothing_reachable(self, monkeypatch):
        monkeypatch.setattr(cd, "tcp_scan", lambda subnet: [])
        monkeypatch.setattr(cd, "arp_scan", lambda subnet: ["172.16.1.1", "172.16.1.2"])
        monkeypatch.setattr(cd, "_tcp_connect", lambda ip, **kw: False)

        assert cd.discover_cameras("172.16.1") == []
