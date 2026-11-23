"""HTTPS local-network sandbox. Does not read or write the hall's live layout.

Explicit certificate, private LAN interface and existing administrator credential
required. This module never changes firewall/router settings or installs a service.
"""
from __future__ import annotations

import argparse
import ipaddress
import ssl
from pathlib import Path

from application.authentication import admin_secret_configured, verify_admin
from application.web_layout_editor import WebLayoutEditor
from runtime.web_layout_editor import BoundedEditorServer, make_handler, prepare_workspace


def build_lan_server(editor, *, address, port, certificate, private_key, authenticator):
    ip = ipaddress.ip_address(address)
    # No all-interface listener, DNS names, public interface or IPv6 in this phase.
    if ip.version != 4 or ip.is_unspecified or ip.is_multicast or not (ip.is_private or ip.is_link_local):
        raise ValueError("Bind to a specific private IPv4 interface")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certificate), str(private_key))
    origin = f"https://{address}:{port}"
    handler = make_handler(editor, origin, authenticator=authenticator)
    server = BoundedEditorServer((address, port), handler)
    # Handshake inside the bounded worker, never in the accept loop.
    server.tls_context = context
    return server, origin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", required=True, type=Path)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", default=8766, type=int)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    args = parser.parse_args()
    if not admin_secret_configured():
        parser.error("No dedicated administrator credential is configured")
    workspace, lock = prepare_workspace(args.sandbox)
    editor = WebLayoutEditor(workspace)
    editor.initialize()
    server, origin = build_lan_server(editor, address=args.bind, port=args.port,
                                      certificate=args.certificate, private_key=args.private_key,
                                      authenticator=verify_admin)
    print(f"HTTPS editor sandbox: {origin} | Test layout only", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        lock.close()


if __name__ == "__main__":
    main()
