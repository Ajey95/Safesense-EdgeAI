"""Store a Telegram bot token encrypted for the current Windows account."""

from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs


TOKEN_FILE = Path("data/live/sos_bot_token.dpapi")
BOT_TOKEN = re.compile(r"^[0-9]+:[A-Za-z0-9_-]{20,}$")

_PROTECT = (
    "Add-Type -AssemblyName System.Security;"
    "$value=[Console]::In.ReadToEnd();"
    "$bytes=[Text.Encoding]::UTF8.GetBytes($value);"
    "$sealed=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,"
    "[Security.Cryptography.DataProtectionScope]::CurrentUser);"
    "[Console]::Out.Write([Convert]::ToBase64String($sealed))"
)
_UNPROTECT = (
    "Add-Type -AssemblyName System.Security;"
    "$value=[Console]::In.ReadToEnd();"
    "$bytes=[Convert]::FromBase64String($value);"
    "$plain=[Security.Cryptography.ProtectedData]::Unprotect($bytes,$null,"
    "[Security.Cryptography.DataProtectionScope]::CurrentUser);"
    "[Console]::Out.Write([Text.Encoding]::UTF8.GetString($plain))"
)


def _dpapi(script: str, value: str) -> str:
    if sys.platform != "win32":
        raise ValueError("Telegram token store requires Windows DPAPI")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        input=value, text=True, capture_output=True, check=True, timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.stdout


def store_token(token: str, path: Path = TOKEN_FILE) -> None:
    if not BOT_TOKEN.fullmatch(token):
        raise ValueError("invalid Telegram bot token format")
    sealed = _dpapi(_PROTECT, token)
    base64.b64decode(sealed, validate=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(sealed, encoding="ascii")
    os.replace(temp, path)


def load_token(path: Path = TOKEN_FILE) -> str:
    token = os.getenv("SAFESENSE_TELEGRAM_BOT_TOKEN", "")
    if not token and path.exists():
        token = _dpapi(_UNPROTECT, path.read_text(encoding="ascii"))
    if not BOT_TOKEN.fullmatch(token):
        raise ValueError("Set SAFESENSE_TELEGRAM_BOT_TOKEN or import a token locally")
    return token


def serve_import(port: int = 8767) -> None:
    nonce = secrets.token_urlsafe(18)
    route = f"/import/{nonce}"
    completed = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            if self.path != route:
                self.send_error(404)
                return
            body = ("<!doctype html><title>SafeSense bot setup</title>"
                    "<h1>SafeSense bot token setup</h1>"
                    "<p>This page stores the token encrypted for this Windows account.</p>"
                    f"<form method='post' action='{route}'>"
                    "<label>Bot token <input name='token' type='password' required></label>"
                    "<button type='submit'>Store token locally</button></form>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            nonlocal completed
            if self.path != route or self.headers.get("Origin") not in (None, f"http://127.0.0.1:{port}"):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 256:
                    raise ValueError("invalid request length")
                form = parse_qs(self.rfile.read(length).decode("ascii"), strict_parsing=True)
                token = form["token"][0]
                store_token(token)
            except (ValueError, KeyError, UnicodeDecodeError, subprocess.SubprocessError):
                self.send_error(400, "Token import failed")
                return
            body = b"SafeSense bot token stored for the current Windows account."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            completed = True

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        deadline = time.monotonic() + 120
        print(f"http://127.0.0.1:{port}{route}", flush=True)
        while not completed and time.monotonic() < deadline:
            server.timeout = max(0.1, deadline - time.monotonic())
            server.handle_request()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import a Telegram token into the local Windows store")
    parser.add_argument("--import-ui", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=8767)
    arguments = parser.parse_args()
    serve_import(arguments.port)
