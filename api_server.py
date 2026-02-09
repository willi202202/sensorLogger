# api_server.py
import logging
from flask import Flask, jsonify, request
from evaluation.generate_reports import generate_reports

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route("/api/update", methods=["POST"])
def update():
    """Update reports endpoint"""
    try:
        generate_reports()
        return jsonify({"ok": True}), 200
    except Exception as e:
        log.exception("Update fehlgeschlagen")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    log.exception("Interner Fehler")
    return jsonify({"ok": False, "error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=False)
