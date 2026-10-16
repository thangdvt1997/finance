"""CLI + API noi bo (stdlib) de engine goi.
  python -m pattern_render render --candles c.json --ann a.json --out x.png [--max-kb 150]
  python -m pattern_render serve --port 8791        # POST /render {candles, annotations, max_kb?} -> image/png ; GET /healthz
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .render import render_png_bytes
from .schema import SchemaError


def _handler():
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/healthz":
                self._send(200, b'{"ok":true}', "application/json")
            else:
                self._send(404, b'{"error":"not found"}', "application/json")

        def do_POST(self):
            if self.path != "/render":
                return self._send(404, b'{"error":"not found"}', "application/json")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > 8_000_000:
                    return self._send(413, b'{"error":"payload qua lon"}', "application/json")
                req = json.loads(self.rfile.read(n) or b"{}")
                png = render_png_bytes(req["candles"], req.get("annotations"), max_kb=req.get("max_kb"))
                self._send(200, png, "image/png")
            except (SchemaError, KeyError, ValueError) as e:
                self._send(400, json.dumps({"error": str(e)}).encode(), "application/json")

        def log_message(self, *a):
            pass

    return H


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pattern_render")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--candles", required=True)
    r.add_argument("--ann", default=None)
    r.add_argument("--out", required=True)
    r.add_argument("--max-kb", type=int, default=None)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8791)
    a = ap.parse_args(argv)
    if a.cmd == "render":
        candles = json.load(open(a.candles, encoding="utf-8"))
        if isinstance(candles, dict):
            candles = candles["candles"]
        ann = json.load(open(a.ann, encoding="utf-8")) if a.ann else None
        open(a.out, "wb").write(render_png_bytes(candles, ann, max_kb=a.max_kb))
        print(a.out)
        return 0
    ThreadingHTTPServer((a.host, a.port), _handler()).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
