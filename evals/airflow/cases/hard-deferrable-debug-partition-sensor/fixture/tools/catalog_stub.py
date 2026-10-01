"""Local stand-in for the lake catalog API.

    python tools/catalog_stub.py --publish orders/2026-09-29=0 --publish orders/2026-09-28=5

Flags:
  --publish TABLE/PARTITION=SECONDS  partition becomes PUBLISHED that many seconds after startup
                                     (repeatable; any other partition stays PENDING)
  --latency S                        delay added to every request, like the real API under load
  --down                             every request answers HTTP 503
  --outage START END                 every request answers HTTP 503 between START and END seconds
                                     after the first request
  --port N                           default: a free port, printed at startup
  --log FILE                         JSONL record of requests
Token: eval-lake-token.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "eval-lake-token"


def files_for(table: str, partition: str) -> list[str]:
    return [f"s3://lake/{table}/{partition}/part-{i}.parquet" for i in range(2)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--port-file", default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--latency", type=float, default=0.0)
    ap.add_argument("--down", action="store_true")
    ap.add_argument("--outage", type=float, nargs=2, default=None)
    ap.add_argument("--publish", action="append", default=[])
    args = ap.parse_args()
    started = time.time()
    first = {"t": None}
    publish = {}
    for spec in args.publish:
        key, _, delay = spec.partition("=")
        publish[key] = float(delay or 0)
    lock = threading.Lock()

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
            if args.latency:
                time.sleep(args.latency)
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                log(event="unauthorized", path=self.path)
                return self._send(401, {"error": "unauthorized"})
            with lock:
                if first["t"] is None:
                    first["t"] = time.time()
            in_outage = bool(args.outage) and args.outage[0] <= time.time() - first["t"] < args.outage[1]
            if args.down or in_outage:
                log(event="503", path=self.path)
                return self._send(503, {"error": "service unavailable"})
            if len(parts) == 5 and parts[:2] == ["v1", "tables"] and parts[3] == "partitions":
                table, partition = parts[2], parts[4]
                delay = publish.get(f"{table}/{partition}")
                ready = delay is not None and time.time() - started >= delay
                log(event="status", table=table, partition=partition, ready=ready)
                if ready:
                    return self._send(200, {"state": "PUBLISHED", "files": files_for(table, partition)})
                return self._send(200, {"state": "PENDING"})
            self._send(404, {"error": "not found"})

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    srv.daemon_threads = True
    if args.port_file:
        with open(args.port_file, "w") as fh:
            fh.write(str(srv.server_address[1]))
    print(f"lake catalog listening on http://127.0.0.1:{srv.server_address[1]} (token {TOKEN})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
