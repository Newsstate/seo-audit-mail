import json, os
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler


def get_redis():
    url   = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    try:
        from upstash_redis import Redis
        return Redis(url=url, token=token)
    except Exception:
        return None


def store_get(job_id):
    r = get_redis()
    if not r:
        return None
    try:
        v = r.get(f"seo:{job_id}")
        if not v:
            return None
        parsed = json.loads(v)
        # Must have a status key to be valid
        if not isinstance(parsed, dict) or "status" not in parsed:
            return None
        return parsed
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        qs     = parse_qs(urlparse(self.path).query)
        job_id = (qs.get("job_id") or [""])[0].strip()

        if not job_id:
            return self._json(400, {"error": "Missing job_id"})

        record = store_get(job_id)

        # No record yet = still running
        if record is None:
            return self._json(200, {"status": "running"})

        # Has status key — return it
        self._json(200, record)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *a): pass
