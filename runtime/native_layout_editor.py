"""Explicit native Qt test launcher, optionally sharing its master over HTTPS.

No startup installation or production data. The one process owns one workspace
lock and one editor transaction service, used by both native and web clients.
"""

from __future__ import annotations
import argparse
from pathlib import Path
import sys
import threading
from PyQt5.QtWidgets import QApplication
from application.web_layout_editor import WebLayoutEditor
from runtime.web_layout_editor import prepare_workspace
from runtime.web_layout_editor_lan import build_lan_server
from application.authentication import admin_secret_configured, verify_admin
from ui.native_layout_editor import NativeLayoutEditor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", type=Path, required=True)
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--private-key", type=Path)
    args = parser.parse_args()
    if args.bind and not (args.certificate and args.private_key and admin_secret_configured()):
        parser.error(
            "HTTPS sharing requires certificate, private key and dedicated administrator credential"
        )
    workspace, lock = prepare_workspace(args.sandbox)
    server = None
    worker = None
    try:
        editor = WebLayoutEditor(workspace)
        editor.initialize()
        if args.bind:
            server, origin = build_lan_server(
                editor,
                address=args.bind,
                port=args.port,
                certificate=args.certificate,
                private_key=args.private_key,
                authenticator=verify_admin,
            )
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            print("Shared HTTPS sandbox: " + origin, flush=True)
        app = QApplication.instance() or QApplication(sys.argv[:1])
        dialog = NativeLayoutEditor(editor)
        dialog.show()
        return app.exec_()
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if worker:
            worker.join()
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
