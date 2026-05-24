"""Tiny built-in HTTP server that renders the todos as a read-only table.

Runs in a daemon thread so it dies with the MCP server process. The
dashboard is read-only and does not cache — every GET re-parses
.claude/todos.md from disk.
"""
from __future__ import annotations

import socket
import threading
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from string import Template
from typing import Callable

from todo_mcp import data

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _find_port(start: int = 8765, max_tries: int = 10) -> int:
    for offset in range(max_tries):
        port = start + offset
        if _is_port_free(port):
            return port
    raise RuntimeError(
        f"No free port in range {start}-{start + max_tries - 1}"
    )


def _row(t: dict) -> str:
    status = "&check;" if t["done"] else "&deg;"
    klass = "done" if t["done"] else "open"
    due = escape(t["due"]) if t["due"] else ""
    return (
        f'<tr class="{klass}">'
        f"<td>{status}</td>"
        f'<td>#{t["id"]}</td>'
        f'<td class="prio-{t["prio"]}">{escape(t["prio"])}</td>'
        f"<td>{due}</td>"
        f'<td>{escape(t["text"])}</td>'
        "</tr>"
    )


def _render(todos: list[dict]) -> str:
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not todos:
        rows = '<tr><td colspan="5" class="empty">(no todos yet)</td></tr>'
    else:
        rows = "\n".join(_row(t) for t in sorted(todos, key=lambda x: x["id"]))
    return template.safe_substitute(
        rows=rows,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def start(get_todos_path: Callable[[], Path]) -> int:
    """Start the dashboard HTTP server in a daemon thread.

    Returns the chosen port. The thread dies with the main process.
    """
    port = _find_port()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler API
            if self.path != "/":
                self.send_error(404)
                return
            try:
                todos = data.load(get_todos_path())
                body = _render(todos).encode("utf-8")
            except Exception as e:
                body = f"<pre>render error: {escape(str(e))}</pre>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            # Silence default access log — keep stderr clean for MCP debugging.
            pass

    httpd = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return port
