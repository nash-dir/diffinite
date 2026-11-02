"""Bookshelf API - catalogue of books and loans."""
from __future__ import annotations

import os
import sqlite3
from functools import wraps

from flask import Flask, jsonify, request, g, abort

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("SHELF_DB", "shelf.db")
app.config["API_KEY"] = os.environ.get("SHELF_KEY", "dev")


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


def require_key(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.headers.get("X-Api-Key") != app.config["API_KEY"]:
            abort(401)
        return view(*args, **kwargs)
    return wrapper


SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    isbn TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    copies INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY,
    isbn TEXT REFERENCES books(isbn),
    borrower TEXT NOT NULL,
    returned INTEGER DEFAULT 0
);
"""


def available_copies(db, isbn):
    total = db.execute("SELECT copies FROM books WHERE isbn=?", (isbn,)).fetchone()
    if total is None:
        return None
    out = db.execute(
        "SELECT COUNT(*) FROM loans WHERE isbn=? AND returned=0", (isbn,)
    ).fetchone()[0]
    return total["copies"] - out


@app.get("/books")
def books():
    author = request.args.get("author")
    db = get_db()
    if author:
        rows = db.execute("SELECT * FROM books WHERE author LIKE ?", (f"%{author}%",))
    else:
        rows = db.execute("SELECT * FROM books ORDER BY title")
    return jsonify([dict(r) for r in rows])


@app.get("/books/<isbn>")
def book_detail(isbn):
    db = get_db()
    row = db.execute("SELECT * FROM books WHERE isbn=?", (isbn,)).fetchone()
    if row is None:
        abort(404)
    data = dict(row)
    data["available"] = available_copies(db, isbn)
    return jsonify(data)


@app.post("/books")
@require_key
def add_book():
    payload = request.get_json(force=True)
    missing = [k for k in ("isbn", "title", "author") if not payload.get(k)]
    if missing:
        return jsonify(error="missing fields", fields=missing), 422
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO books(isbn, title, author, copies) VALUES (?,?,?,?)",
        (payload["isbn"], payload["title"], payload["author"], payload.get("copies", 1)),
    )
    db.commit()
    return jsonify(ok=True), 201


@app.post("/loans")
@require_key
def lend():
    payload = request.get_json(force=True)
    isbn, who = payload.get("isbn"), payload.get("borrower")
    db = get_db()
    left = available_copies(db, isbn)
    if left is None:
        abort(404)
    if left <= 0:
        return jsonify(error="no copies available"), 409
    cur = db.execute("INSERT INTO loans(isbn, borrower) VALUES (?, ?)", (isbn, who))
    db.commit()
    return jsonify(loan_id=cur.lastrowid), 201


@app.post("/loans/<int:loan_id>/return")
@require_key
def give_back(loan_id):
    db = get_db()
    db.execute("UPDATE loans SET returned=1 WHERE id=?", (loan_id,))
    db.commit()
    return jsonify(ok=True)


@app.errorhandler(401)
def unauthorized(_):
    return jsonify(error="bad api key"), 401


@app.errorhandler(404)
def not_found(_):
    return jsonify(error="not found"), 404


if __name__ == "__main__":
    with app.app_context():
        get_db().executescript(SCHEMA)
    app.run(debug=True)
