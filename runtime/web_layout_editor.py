"""Explicitly started loopback-only editor sandbox. Never opens production data."""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from application.web_layout_editor import EditorError, WebLayoutEditor
from ui.styles import web_editor_tokens_css

ASSETS = Path(__file__).resolve().parents[1] / "ui" / "web_layout_editor"
MAX_BODY = 512_000


def make_handler(editor, origin):
    sessions = set()

    class Handler(BaseHTTPRequestHandler):
        server_version = "KHLayoutSandbox"

        def log_message(self, *args):
            pass  # Never log cookies, draft contents or request paths.

        def send_result(self, status, body, content_type="application/json", cookie=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            if cookie:
                self.send_header("Set-Cookie", f"kh_editor={cookie}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") == urlsplit(origin).netloc

        def cookie_session(self):
            try:
                cookies = SimpleCookie(self.headers.get("Cookie", ""))
                value = cookies["kh_editor"].value
                return value if value in sessions else None
            except (KeyError, ValueError):
                return None

        def session(self):
            cookie = self.cookie_session()
            tab = self.headers.get("X-KH-Tab", "")
            if cookie and re.fullmatch(r"[a-zA-Z0-9-]{20,64}", tab):
                return cookie + ":" + tab
            return None

        def do_GET(self):
            if not self.valid_host():
                return self.send_result(403, {"error": "host_rejected"})
            path = urlsplit(self.path).path
            if path == "/api/layout":
                session = self.session()
                if not session or self.headers.get("X-KH-Editor") != "1":
                    return self.send_result(403, {"error": "session_required"})
                try:
                    return self.send_result(200, editor.read(session))
                except (OSError, ValueError, EditorError):
                    return self.send_result(500, {"error": "master_unreadable"})
            if path == "/theme.css":
                return self.send_result(200, web_editor_tokens_css().encode(), "text/css; charset=utf-8")
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
                     "/editor.css": ("editor.css", "text/css; charset=utf-8")}
            if path not in files:
                return self.send_result(404, {"error": "not_found"})
            name, mime = files[path]
            session = self.cookie_session()
            if path == "/" and not session:
                if len(sessions) >= 100:
                    return self.send_result(503, {"error": "session_limit"})
                session = secrets.token_urlsafe(32)
                sessions.add(session)
            self.send_result(200, (ASSETS / name).read_bytes(), mime,
                             cookie=session if path == "/" else None)

        def do_POST(self):
            if (not self.valid_host() or self.headers.get("Origin") != origin
                    or self.headers.get("Content-Type") != "application/json"
                    or self.headers.get("X-KH-Editor") != "1"):
                return self.send_result(403, {"error": "origin_rejected"})
            session = self.session()
            if not session:
                return self.send_result(403, {"error": "session_required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.send_result(413, {"error": "body_size"})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError()
                if self.path == "/api/lease":
                    result = editor.acquire(session)
                elif self.path == "/api/release":
                    result = editor.release(session)
                elif self.path == "/api/save":
                    result = editor.save(session, data.get("revision"), data.get("document"))
                else:
                    return self.send_result(404, {"error": "not_found"})
                return self.send_result(200, result)
            except EditorError as exc:
                return self.send_result(exc.status, {"error": exc.code})
            except (ValueError, TypeError, KeyError):
                return self.send_result(400, {"error": "invalid_request"})
            except OSError:
                return self.send_result(500, {"error": "storage_error_reload_before_retry"})

    return Handler


def prepare_workspace(path):
    path = path.expanduser().absolute()
    # The sandbox may resume only its own workspace, never adopt an existing layout.
    if path.is_symlink():
        raise ValueError("Sandbox must not be a symlink")
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".kh-web-editor-sandbox"
    if not marker.exists() and any(path.iterdir()):
        raise ValueError("Choose a new empty sandbox directory; production data is not accepted")
    marker.touch(exist_ok=True)
    if any(p.is_symlink() for p in path.iterdir()):
        raise ValueError("Sandbox files must not be symlinks")
    lock = (path / ".editor.lock").open("a")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise ValueError("Another editor server owns this sandbox") from None
    return path, lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", required=True, type=Path)
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    workspace, lock = prepare_workspace(args.sandbox)
    editor = WebLayoutEditor(workspace)
    editor.initialize()
    origin = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(editor, origin))
    print(f"Editor de prueba: {origin} | Sin cámaras ni datos del salón", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        lock.close()


if __name__ == "__main__":
    main()
