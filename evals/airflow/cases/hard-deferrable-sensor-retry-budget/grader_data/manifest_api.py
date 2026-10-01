"""Local stand-in for the partner manifest API.

    python tools/manifest_stub.py --publish-after 10     # prints its URL (a free port unless --port)

Flags:
  --publish-after S     manifests become PUBLISHED S seconds after the first request (default: never)
  --latency S           delay added to every request, like the real API (default 0)
  --outage START END    every request answers HTTP 503 between START and END seconds after
                        the first request
  --port N, --log FILE  listen port; JSONL record of requests
Token: eval-manifest-token.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "eval-manifest-token"


def files_for(partner: str, ds: str) -> list[str]:
    return [f"s3://partners/{partner}/{ds}/batch-{i}.csv.gz" for i in range(3)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--port-file", default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--latency", type=float, default=0.0)
    ap.add_argument("--publish-after", type=float, default=None)
    ap.add_argument("--outage", type=float, nargs=2, default=None)
    args = ap.parse_args()
    lock = threading.Lock()
    first = {"t": None}

    def log(**rec):
        if args.log:
            rec["t"] = time.time()
            with lock, open(args.log, "a") as fh:
                fh.write(json.dumps(rec) + "\n")

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            with lock:
                if first["t"] is None:
                    first["t"] = time.time()
            if args.latency:
                time.sleep(args.latency)
            age = time.time() - first["t"]
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                log(event="unauthorized", path=self.path)
                return self._send(401, {"error": "unauthorized"})
            if args.outage and args.outage[0] <= age < args.outage[1]:
                log(event="503", path=self.path)
                return self._send(503, {"error": "service unavailable"})
            if len(parts) == 5 and parts[:2] == ["v1", "partners"] and parts[3] == "manifests":
                partner, ds = parts[2], parts[4]
                ready = args.publish_after is not None and age >= args.publish_after
                log(event="status", partner=partner, ds=ds, ready=ready)
                if ready:
                    return self._send(200, {"status": "PUBLISHED", "files": files_for(partner, ds)})
                return self._send(200, {"status": "PENDING"})
            self._send(404, {"error": "not found"})

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    srv.daemon_threads = True
    if args.port_file:
        with open(args.port_file, "w") as fh:
            fh.write(str(srv.server_address[1]))
    print(f"manifest API listening on http://127.0.0.1:{srv.server_address[1]} (token {TOKEN})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
