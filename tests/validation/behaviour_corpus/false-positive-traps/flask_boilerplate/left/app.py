"""Tiny task tracker built on Flask + SQLite."""
import os
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, request, g, abort

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("TODO_DB", "todo.sqlite3")
app.config["JSON_SORT_KEYS"] = False


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               title TEXT NOT NULL,
               done INTEGER NOT NULL DEFAULT 0,
               due TEXT,
               created TEXT NOT NULL)"""
    )
    db.commit()


def task_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "done": bool(row["done"]),
        "due": row["due"],
        "created": row["created"],
    }


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/tasks", methods=["GET"])
def list_tasks():
    only_open = request.args.get("open") == "1"
    sql = "SELECT * FROM tasks"
    if only_open:
        sql += " WHERE done = 0"
    sql += " ORDER BY due IS NULL, due"
    rows = get_db().execute(sql).fetchall()
    return jsonify([task_to_dict(r) for r in rows])


@app.route("/tasks", methods=["POST"])
def create_task():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        abort(400, description="title is required")
    due = body.get("due")
    db = get_db()
    cur = db.execute(
        "INSERT INTO tasks (title, due, created) VALUES (?, ?, ?)",
        (title, due, datetime.utcnow().isoformat()),
    )
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(task_to_dict(row)), 201


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    db = get_db()
    row = db.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        abort(404)
    db.execute("UPDATE tasks SET done = ? WHERE id = ?", (0 if row["done"] else 1, task_id))
    db.commit()
    return jsonify(id=task_id, done=not row["done"])


@app.route("/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
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
        init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
