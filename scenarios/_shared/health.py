"""Tiny stand-in for a project's web app (standard library only).

GET /health -> 200 if the database is reachable, 503 otherwise.
Runs inside the `app` container of every scenario project.
"""

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer

DB = (os.environ.get("DB_HOST", "db"), 5432)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return

        try:
            socket.create_connection(DB, timeout=2).close()
            ok = True
        except OSError:
            ok = False

        body = json.dumps({"status": "ok" if ok else "degraded", "db": "up" if ok else "down"}).encode()
        self.send_response(200 if ok else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()
