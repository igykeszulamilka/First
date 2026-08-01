#!/usr/bin/env python3
"""Local Shelly LAN panel: serves the UI and proxies device API calls (avoids CORS)."""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def app_root() -> Path:
    """Source folder, or PyInstaller temp extract dir when frozen as .exe."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


ROOT = app_root()
INDEX = ROOT / "index.html"
TIMEOUT = 2.5


def fetch(url: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None) -> tuple[int, bytes, str]:
    req_headers = {"User-Agent": "ShellyLANPanel/1.0", "Accept": "application/json,*/*"}
    if headers:
        req_headers.update(headers)
    if body is not None and "Content-Type" not in req_headers:
        req_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "application/json")
            return resp.status, resp.read(), ctype
    except urllib.error.HTTPError as err:
        ctype = err.headers.get("Content-Type", "text/plain") if err.headers else "text/plain"
        return err.code, err.read() if err.fp else b"", ctype
    except Exception as exc:  # noqa: BLE001 — surface network errors to the UI
        payload = json.dumps({"error": str(exc)}).encode()
        return 502, payload, "application/json"


def probe_device(ip: str) -> dict | None:
    # Gen2 first
    status, data, _ = fetch(f"http://{ip}/rpc/Shelly.GetDeviceInfo", method="POST", body=b"{}")
    if status == 200:
        try:
            info = json.loads(data.decode())
        except json.JSONDecodeError:
            info = {}
        return {
            "ip": ip,
            "gen": 2,
            "id": info.get("id") or info.get("mac") or ip,
            "name": info.get("name") or info.get("id") or ip,
            "model": info.get("model") or info.get("app") or "Shelly Gen2",
            "type": "switch",
        }

    status, data, _ = fetch(f"http://{ip}/shelly")
    if status == 200:
        try:
            info = json.loads(data.decode())
        except json.JSONDecodeError:
            info = {}
        return {
            "ip": ip,
            "gen": 1,
            "id": info.get("mac") or ip,
            "name": info.get("name") or info.get("type") or ip,
            "model": info.get("type") or info.get("model") or "Shelly Gen1",
            "type": "relay",
        }
    return None


def scan_subnet(cidr: str, max_hosts: int = 254) -> list[dict]:
    network = ipaddress.ip_network(cidr, strict=False)
    hosts = [str(h) for h in network.hosts()][:max_hosts]
    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(probe_device, ip): ip for ip in hosts}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)
    found.sort(key=lambda d: tuple(int(p) for p in d["ip"].split(".")))
    return found


class Handler(BaseHTTPRequestHandler):
    server_version = "ShellyLANPanel/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: object) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return

        if parsed.path == "/api/health":
            self._json(200, {"ok": True})
            return

        if parsed.path == "/api/probe":
            qs = parse_qs(parsed.query)
            ip = (qs.get("ip") or [""])[0].strip()
            if not ip:
                self._json(400, {"error": "ip required"})
                return
            device = probe_device(ip)
            if not device:
                self._json(404, {"error": "no Shelly device at that IP"})
                return
            self._json(200, device)
            return

        if parsed.path == "/api/proxy":
            qs = parse_qs(parsed.query)
            ip = (qs.get("ip") or [""])[0].strip()
            path = (qs.get("path") or [""])[0]
            if not ip or not path.startswith("/"):
                self._json(400, {"error": "ip and absolute path required"})
                return
            auth = (qs.get("auth") or [""])[0]
            headers = {}
            if auth:
                headers["Authorization"] = f"Basic {auth}"
            status, data, ctype = fetch(f"http://{ip}{path}", headers=headers)
            self._send(status, data, ctype)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid JSON"})
            return

        if parsed.path == "/api/scan":
            cidr = str(payload.get("cidr") or "").strip()
            if not cidr:
                self._json(400, {"error": "cidr required, e.g. 192.168.1.0/24"})
                return
            try:
                devices = scan_subnet(cidr)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"devices": devices})
            return

        if parsed.path == "/api/proxy":
            ip = str(payload.get("ip") or "").strip()
            path = str(payload.get("path") or "")
            method = str(payload.get("method") or "GET").upper()
            body = payload.get("body")
            auth = str(payload.get("auth") or "")
            if not ip or not path.startswith("/"):
                self._json(400, {"error": "ip and absolute path required"})
                return
            headers = {}
            if auth:
                headers["Authorization"] = f"Basic {auth}"
            data = None
            if body is not None:
                data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
            status, resp, ctype = fetch(f"http://{ip}{path}", method=method, body=data, headers=headers)
            self._send(status, resp, ctype)
            return

        self._json(404, {"error": "not found"})


def guess_default_cidr() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except OSError:
        return "192.168.1.0/24"


def main() -> None:
    parser = argparse.ArgumentParser(description="Shelly LAN panel / KAPCS")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true", help="Ne nyissa meg automatikusan a böngészőt")
    args = parser.parse_args()

    if not INDEX.exists():
        raise SystemExit(f"Missing UI file: {INDEX}")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    cidr = guess_default_cidr()
    print("KAPCS — Shelly LAN panel")
    print(f"  Böngésző:  {url}")
    print(f"  Telefon:   http://<ennek-a-gepnek-az-IP-je>:{args.port}")
    print(f"  Scan tipp: {cidr}")
    print("  Leállítás: Ctrl+C")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nLeállítva.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
