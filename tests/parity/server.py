#!/usr/bin/env python3
"""Loopback collector for stock-vs-camoufox comparisons.

GET  /probe.html?tag=X  -> the probe page (its request headers are logged too)
POST /result?tag=X      -> JSON body written to OUT/<tag>.json
Every request's headers go to OUT/<tag>.headers.jsonl, so Accept-Encoding and
friends are compared on the wire, not from JS.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
os.makedirs(OUT, exist_ok=True)


def tag_of(path):
    return parse_qs(urlparse(path).query).get("tag", ["untagged"])[0]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _log_headers(self):
        with open(os.path.join(OUT, tag_of(self.path) + ".headers.jsonl"), "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path,
                                "headers": list(self.headers.items())}) + "\n")

    def do_GET(self):
        self._log_headers()
        p = urlparse(self.path).path
        if p == "/favicon.ico":
            self.send_response(404)
            self.end_headers()
            return
        if p == "/pos":
            self.send_response(204)
            self.end_headers()
            return
        name = {"/probe.html": "probe.html", "/blank.html": "blank.html"}.get(p)
        if not name:
            self.send_response(404)
            self.end_headers()
            return
        body = open(os.path.join(HERE, name), "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._log_headers()
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        with open(os.path.join(OUT, tag_of(self.path) + ".json"), "wb") as f:
            f.write(data)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        print(f"result {tag_of(self.path)} {len(data)} bytes", flush=True)


ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
