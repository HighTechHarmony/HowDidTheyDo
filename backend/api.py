"""Flask API for howdidtheydo.

Routes:
    GET  /api/predictions/recent   → latest 10 predictions (sorted by votes)
    GET  /api/predictions/top      → top 10 all-time (by net votes)
    POST /api/predictions/<id>/vote  body: {"direction": "up"|"down"}
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request
from flask_cors import CORS
from backend.db import init_db, get_recent, get_top_all_time, vote

app = Flask(__name__)
CORS(app)


@app.before_request
def _ensure_db():
    """Lazily initialise the database on first request."""
    init_db()


@app.route("/api/predictions/recent")
def recent():
    limit = request.args.get("limit", 10, type=int)
    rows = get_recent(limit=limit)
    return jsonify(rows)


@app.route("/api/predictions/top")
def top():
    limit = request.args.get("limit", 10, type=int)
    rows = get_top_all_time(limit=limit)
    return jsonify(rows)


@app.route("/api/predictions/<int:prediction_id>/vote", methods=["POST"])
def cast_vote(prediction_id):
    body = request.get_json(force=True)
    direction = body.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"error": "direction must be 'up' or 'down'"}), 400
    vote(prediction_id, direction)
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
