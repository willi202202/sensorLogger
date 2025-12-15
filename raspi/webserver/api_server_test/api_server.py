# api_server.py
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

def generate_reports():
    # HIER deine bestehende Funktion aufrufen
    log.info("Reports werden aktualisiert...")
    # generate_reports()
    pass

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/update":
            try:
                generate_reports()
                self._reply(200, {"ok": True})
            except Exception as e:
                log.exception("Update fehlgeschlagen")
                self._reply(500, {"ok": False, "error": str(e)})
        else:
            self._reply(404, {"ok": False, "error": "Not found"})

    def _reply(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8001), Handler).serve_forever()
