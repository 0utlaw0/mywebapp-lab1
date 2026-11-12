import argparse
import os
import sys

import pymysql
from flask import Flask, Response, jsonify, request


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="mywebapp Notes Service")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5200)
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-password", default=os.environ.get("DB_PASSWORD", ""))
    p.add_argument("--db-name", required=True)
    return p.parse_args(argv)


def html_page(title, body):
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{body}</body></html>"
    )


def esc(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def create_app(cfg):
    app = Flask(__name__)

    def get_conn():
        return pymysql.connect(
            host=cfg.db_host,
            port=cfg.db_port,
            user=cfg.db_user,
            password=cfg.db_password,
            database=cfg.db_name,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3,
            autocommit=True,
        )

    def wants_html():
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "text/html"

    def wants_json():
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "application/json"

    def respond(data, html_body, status=200):
        if wants_html():
            return Response(html_page("Notes", html_body), status=status, mimetype="text/html")
        if wants_json():
            resp = jsonify(data)
            resp.status_code = status
            return resp
        return Response("Not Acceptable: use Accept text/html or application/json\n",
                        status=406, mimetype="text/plain")

    @app.get("/health/alive")
    def alive():
        return Response("OK", mimetype="text/plain")

    @app.get("/health/ready")
    def ready():
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
        except Exception as e:
            return Response(f"Database is not available: {e.__class__.__name__}",
                            status=500, mimetype="text/plain")
        return Response("OK", mimetype="text/plain")

    @app.get("/")
    def root():
        body = (
            "<h1>Notes Service</h1><ul>"
            "<li>GET /notes - list of notes</li>"
            "<li>POST /notes - create a note (title, content)</li>"
            "<li>GET /notes/&lt;id&gt; - note details</li>"
            "</ul>"
        )
        return Response(html_page("mywebapp", body), mimetype="text/html")

    @app.get("/notes")
    def list_notes():
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, title FROM notes ORDER BY id")
            rows = cur.fetchall()
        conn.close()
        table = "<table border=\"1\"><tr><th>id</th><th>title</th></tr>" + "".join(
            f"<tr><td>{r['id']}</td><td>{esc(r['title'])}</td></tr>" for r in rows
        ) + "</table>"
        return respond(rows, "<h1>Notes</h1>" + table)

    @app.post("/notes")
    def create_note():
        if request.is_json:
            payload = request.get_json(silent=True) or {}
        else:
            payload = request.form
        title = (payload.get("title") or "").strip()
        content = payload.get("content") or ""
        if not title:
            return Response("title is required\n", status=400, mimetype="text/plain")
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO notes (title, content) VALUES (%s, %s)", (title, content))
            note_id = cur.lastrowid
        conn.close()
        data = {"id": note_id, "title": title}
        body = f"<h1>Note created</h1><p>id: {note_id}</p><p>title: {esc(title)}</p>"
        return respond(data, body, status=201)

    @app.get("/notes/<int:note_id>")
    def get_note(note_id):
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, created_at, content FROM notes WHERE id = %s", (note_id,)
            )
            row = cur.fetchone()
        conn.close()
        if row is None:
            return Response("Note not found\n", status=404, mimetype="text/plain")
        row["created_at"] = row["created_at"].isoformat(sep=" ")
        body = (
            "<h1>Note</h1><table border=\"1\">"
            f"<tr><th>id</th><td>{row['id']}</td></tr>"
            f"<tr><th>title</th><td>{esc(row['title'])}</td></tr>"
            f"<tr><th>created_at</th><td>{row['created_at']}</td></tr>"
            f"<tr><th>content</th><td>{esc(row['content'])}</td></tr>"
            "</table>"
        )
        return respond(row, body)

    return app


if __name__ == "__main__":
    cfg = parse_args()
    create_app(cfg).run(host=cfg.host, port=cfg.port)
