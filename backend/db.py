"""SQLite helpers for the predictions database."""

import json
import os
import sqlite3
import sys

# Allow imports from the project root so we can reach src/config.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.config import DB_PATH


def _connect():
    """Return a connection to the predictions database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safe concurrent reads
    return conn


def init_db():
    """Create the predictions table if it doesn't already exist."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            summary      TEXT,
            published    TEXT,
            snapshot_ts  TEXT,
            rss_url      TEXT,
            article_url  TEXT,
            prediction   TEXT,
            timeframe    TEXT,
            target_year  INTEGER,
            score        INTEGER,
            explanation  TEXT,
            facts        TEXT,
            upvotes      INTEGER DEFAULT 0,
            downvotes    INTEGER DEFAULT 0,
            debug_log    TEXT,
            created_at   TEXT NOT NULL,
            UNIQUE(title, published, rss_url)
        )
    """)

    # If the table existed before adding `article_url`, add the column safely.
    cur = conn.execute("PRAGMA table_info(predictions)")
    cols = [r[1] for r in cur.fetchall()]
    if "article_url" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN article_url TEXT")

    # ---- Migration: remove any pre-existing duplicate titles ---------------
    # Keep the row with the highest id (most recent insertion) for each title
    # so the UNIQUE index below can be created without an IntegrityError even
    # on databases that accumulated duplicates before this fix was applied.
    conn.execute("""
        DELETE FROM predictions
        WHERE id NOT IN (
            SELECT MAX(id) FROM predictions GROUP BY title
        )
        AND title IN (
            SELECT title FROM predictions GROUP BY title HAVING COUNT(*) > 1
        )
    """)
    conn.commit()

    # Headline uniqueness — enforced at the DB level so INSERT OR IGNORE also
    # catches duplicates that slip through the Python pre-check (e.g. when
    # `published` is NULL and the UNIQUE(title, published, rss_url) constraint
    # cannot fire correctly due to SQLite NULL semantics).
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_predictions_title
        ON predictions (title)
    """)

    # Article-URL uniqueness — partial index excludes NULL article_url rows so
    # articles without a resolved URL don't block each other.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_predictions_article_url
        ON predictions (article_url)
        WHERE article_url IS NOT NULL
    """)

    conn.commit()
    conn.close()


def insert_prediction(data):
    """Insert a prediction row.  Returns the new row id, or None if duplicate.

    `data` is a dict with keys matching the column names.
    `facts` and `debug_log` should be Python lists — they are JSON-serialised here.
    """
    conn = _connect()
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO predictions
                (title, summary, published, snapshot_ts, rss_url, article_url,
                 prediction, timeframe, target_year,
                 score, explanation, facts,
                 debug_log, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("title"),
            data.get("summary"),
            data.get("published"),
            data.get("snapshot_ts"),
            data.get("rss_url"),
            data.get("article_url"),
            data.get("prediction"),
            data.get("timeframe"),
            data.get("target_year"),
            data.get("score"),
            data.get("explanation"),
            json.dumps(data.get("facts") or []),
            json.dumps(data.get("debug_log") or []),
            data.get("created_at"),
        ))
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None
    finally:
        conn.close()


def article_exists(title, published, rss_url):
    """Return True if a row with this (title, published, rss_url) is already in the DB.

    Uses the same columns as the UNIQUE constraint so the query hits the index.
    `published` should be an ISO-format string (or None).

    NOTE: Uses IS-based NULL-safe comparison for `published` because SQLite
    evaluates `NULL = NULL` as NULL (not TRUE), which caused articles whose
    pubDate could not be parsed to bypass this check on every run.
    """
    conn = _connect()
    row = conn.execute(
        """
        SELECT 1 FROM predictions
        WHERE title = ?
          AND rss_url = ?
          AND (published = ? OR (published IS NULL AND ? IS NULL))
        """,
        (title, rss_url, published, published),
    ).fetchone()
    conn.close()
    return row is not None


def title_exists(title):
    """Return True if any row with this exact headline already exists.

    This is the simplest possible deduplication guard — it fires regardless of
    `published` date, feed URL, or any other field.  Use it as a fast
    short-circuit before making any LLM calls.
    """
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM predictions WHERE title = ?",
        (title,),
    ).fetchone()
    conn.close()
    return row is not None


def url_exists(article_url):
    """Return True if any row with this article_url already exists.

    Catches the case where the same article URL appears in another snapshot
    with a corrected/different headline.  NULL / empty URLs are never matched.
    """
    if not article_url:
        return False
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM predictions WHERE article_url = ?",
        (article_url,),
    ).fetchone()
    conn.close()
    return row is not None


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict, deserialising JSON fields."""
    d = dict(row)
    for field in ("facts", "debug_log"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_recent(limit=10):
    """Return the most recent `limit` predictions, sorted by net votes descending."""
    conn = _connect()
    rows = conn.execute("""
        SELECT * FROM predictions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    results = [_row_to_dict(r) for r in rows]
    results.sort(key=lambda r: (r.get("upvotes", 0) - r.get("downvotes", 0)), reverse=True)
    return results


def get_top_all_time(limit=10):
    """Return the top `limit` predictions by net votes, all time."""
    conn = _connect()
    rows = conn.execute("""
        SELECT * FROM predictions
        ORDER BY (upvotes - downvotes) DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_recent_page(page=1, per_page=10):
    """Return a page of recent predictions and the total count.

    Results are ordered by created_at DESC, but returned list is then
    sorted by net votes (upvotes - downvotes) to preserve previous behaviour
    for the visible ordering.
    """
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) as c FROM predictions").fetchone()[0]
    offset = max(0, (page - 1) * per_page)
    rows = conn.execute("""
        SELECT * FROM predictions
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()
    results = [_row_to_dict(r) for r in rows]
    results.sort(key=lambda r: (r.get("upvotes", 0) - r.get("downvotes", 0)), reverse=True)
    return results, total


def get_top_page(page=1, per_page=10):
    """Return a page of top predictions (by net votes) and the total count."""
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) as c FROM predictions").fetchone()[0]
    offset = max(0, (page - 1) * per_page)
    rows = conn.execute("""
        SELECT * FROM predictions
        ORDER BY (upvotes - downvotes) DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows], total


def vote(prediction_id, direction):
    """Increment upvotes or downvotes for a prediction.

    direction: "up" or "down"
    Returns the updated (upvotes, downvotes) tuple, or None if id not found.
    """
    col = "upvotes" if direction == "up" else "downvotes"
    conn = _connect()
    conn.execute(f"UPDATE predictions SET {col} = {col} + 1 WHERE id = ?", (prediction_id,))
    conn.commit()
    row = conn.execute("SELECT upvotes, downvotes FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
