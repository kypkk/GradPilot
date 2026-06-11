#!/usr/bin/env python3
"""Local server for the new-grad tier-list job board.

- Serves the project folder statically (so swe-tier-list.html can fetch
  results/*.json).
- POST /api/applied {slug, job_id, applied}  -> persists the `applied` flag
  back into results/{slug}.json.

Run:  python3 server.py [port]   (default port 8000)
Open: http://localhost:8000/swe-tier-list.html
"""
import json
import os
import re
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(ROOT, "results")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def resolve_result_path(slug):
    """Return the real path of results/<slug>.json, matched case-insensitively.

    Lets the fetcher write Amazon.json / amazon.json / AMAZON.json interchangeably
    while the page always asks for the lowercase slug. Returns None if absent."""
    if not SLUG_RE.match(slug):
        return None
    target = (slug + ".json").lower()
    if not os.path.isdir(RESULTS_DIR):
        return None
    for fn in os.listdir(RESULTS_DIR):
        if fn.lower() == target:
            return os.path.join(RESULTS_DIR, fn)
    return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    # ----- helpers -----
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ----- routes -----
    def do_GET(self):
        # Serve results/<name>.json case-insensitively, e.g. a request for
        # results/amazon.json resolves a file saved as Amazon.json.
        path = self.path.split("?", 1)[0]
        if path.lower().startswith("/results/") and path.lower().endswith(".json"):
            slug = os.path.basename(path)[:-5]  # strip ".json"
            real = resolve_result_path(slug.lower())
            if real:
                try:
                    with open(real, "rb") as f:
                        body = f.read()
                except OSError:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self._send_json(404, {"ok": False, "error": "not fetched"})
            return
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/applied":
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        slug = str(data.get("slug", ""))
        job_id = data.get("job_id")
        applied = bool(data.get("applied", False))

        if not SLUG_RE.match(slug) or job_id is None:
            self._send_json(400, {"ok": False, "error": "slug/job_id required"})
            return

        path = resolve_result_path(slug)
        if not path:
            self._send_json(404, {"ok": False, "error": "company file not found"})
            return

        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)

        job = next((j for j in doc.get("jobs", []) if j.get("job_id") == job_id), None)
        if job is None:
            self._send_json(404, {"ok": False, "error": "job_id not found"})
            return

        job["applied"] = applied

        # atomic write
        fd, tmp = tempfile.mkstemp(dir=RESULTS_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

        self._send_json(200, {"ok": True, "job_id": job_id, "applied": applied})

    # quieter, single-line logging
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.makedirs(RESULTS_DIR, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving {ROOT}")
    print(f"Open  http://localhost:{port}/swe-tier-list.html")
    print("Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
