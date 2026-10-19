"""Local web viewer: a stdlib HTTP server plus a static HTML export.

The browser page (web/index.html) draws the arm, the panel and the paint; all
the maths runs here in Python, so the viewer and the tests use the same code.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlparse

from .config import config_from_params
from .simulate import reach_map, simulate

WEB_DIR = Path(__file__).parent / "web"
DATA_MARKER = "<!--SIM_DATA-->"


def _key(params: Dict[str, str]):
    return tuple(sorted(params.items()))


@lru_cache(maxsize=64)
def _cached_sim(key) -> str:
    return json.dumps(simulate(config_from_params(dict(key))))


@lru_cache(maxsize=64)
def _cached_reach(key) -> str:
    params = dict(key)
    step = float(params.pop("step", 20.0))
    step = min(max(step, 5.0), 60.0)
    return json.dumps(reach_map(config_from_params(params), step_mm=step))


REACH_KEYS = ("standoff", "tilt", "canvas_x", "canvas_y", "canvas_z", "nozzle_depth", "step")


class Handler(BaseHTTPRequestHandler):
    server_version = "airbrush-sim/1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (stdlib name)
        url = urlparse(self.path)
        params = dict(parse_qsl(url.query))
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/simulate":
                self._send(200, _cached_sim(_key(params)).encode(), "application/json")
            elif url.path == "/api/reach":
                params = {k: v for k, v in params.items() if k in REACH_KEYS}
                self._send(200, _cached_reach(_key(params)).encode(), "application/json")
            else:
                self._send(404, b'{"error": "not found"}', "application/json")
        except ValueError as exc:
            self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    httpd = make_server(host, port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"Airbrush arm sim running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def export_html(result: Dict[str, Any], reach: Optional[Dict[str, Any]], out: Path) -> Path:
    """Write a self-contained HTML file with one precomputed run (playback only)."""
    page = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    payload = json.dumps({"result": result, "reach": reach}, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")  # never close the script tag early
    page = page.replace(DATA_MARKER, f"<script>window.SIM_DATA = {payload};</script>", 1)
    out.write_text(page, encoding="utf-8")
    return out
