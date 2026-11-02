"""Tiny task tracker built on Flask + SQLite."""
import os
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, request, g, abort

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("TODO_DB", "todo.sqlite3")
app.config["JSON_SORT_KEYS"] = False


def open_conn():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def shutdown_conn(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def create_schema():
    db = open_conn()
    db.execute(
        """CREATE TABLE IF NOT EXISTS items (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               title TEXT NOT NULL,
               done INTEGER NOT NULL DEFAULT 0,
               due TEXT,
               created TEXT NOT NULL)"""
    )
    db.commit()


def row_as_json(rec):
    return {
        "id": rec["id"],
        "title": rec["title"],
        "done": bool(rec["done"]),
        "due": rec["due"],
        "created": rec["created"],
    }


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/items", methods=["GET"])
def all_items():
    pending_only = request.args.get("open") == "1"
    sql = "SELECT * FROM items"
    if pending_only:
        sql += " WHERE done = 0"
    sql += " ORDER BY due IS NULL, due"
    rows = open_conn().execute(sql).fetchall()
    return jsonify([row_as_json(r) for r in rows])


@app.route("/items", methods=["POST"])
def new_item():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        abort(400, description="title is required")
    due = payload.get("due")
    db = open_conn()
    cur = db.execute(
        "INSERT INTO items (title, due, created) VALUES (?, ?, ?)",
        (title, due, datetime.utcnow().isoformat()),
    )
    db.commit()
    rec = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_as_json(rec)), 201


@app.route("/items/<int:item_id>/toggle", methods=["POST"])
def flip_item(item_id):
    db = open_conn()
    rec = db.execute("SELECT done FROM items WHERE id = ?", (item_id,)).fetchone()
    if rec is None:
        abort(404)
    db.execute("UPDATE items SET done = ? WHERE id = ?", (0 if rec["done"] else 1, item_id))
    db.commit()
    return jsonify(id=item_id, done=not rec["done"])


@app.route("/items/<int:item_id>", methods=["DELETE"])
def remove_item(item_id):
    db = open_conn()
    db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    db.commit()
    return "", 204


@app.errorhandler(400)
def bad_request(err):
    return jsonify(error=str(err.description)), 400


@app.errorhandler(404)
def not_found(err):
    return jsonify(error="not found"), 404


if __name__ == "__main__":
    with app.app_context():
        create_schema()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
