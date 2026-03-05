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
from backend.db import (
    init_db,
    get_recent,
    get_top_all_time,
    get_recent_page,
    get_top_page,
    vote,
)
import math

app = Flask(__name__)
CORS(app)


@app.before_request
def _ensure_db():
    """Lazily initialise the database on first request."""
    init_db()


@app.route("/api/predictions/recent")
def recent():
    # Backwards compatible: accept `limit` as previous behaviour, otherwise use
    # `page`/`per_page` pagination parameters.
    if "limit" in request.args and "page" not in request.args:
        limit = request.args.get("limit", 10, type=int)
        rows = get_recent(limit=limit)
        return jsonify(rows)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    rows, total = get_recent_page(page=page, per_page=per_page)
    total_pages = math.ceil(total / per_page) if per_page > 0 else 1
    return jsonify({
        "items": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@app.route("/api/predictions/top")
def top():
    if "limit" in request.args and "page" not in request.args:
        limit = request.args.get("limit", 10, type=int)
        rows = get_top_all_time(limit=limit)
        return jsonify(rows)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    rows, total = get_top_page(page=page, per_page=per_page)
    total_pages = math.ceil(total / per_page) if per_page > 0 else 1
    return jsonify({
        "items": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


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
