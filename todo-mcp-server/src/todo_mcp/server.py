"""todo-mcp-server entry point.

MCP server exposing todo CRUD as Tools, the full list as a Resource,
and a weekly_review Prompt. A read-only HTTP dashboard runs alongside
in a daemon thread.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from todo_mcp import dashboard, data

mcp = FastMCP("todo")

# Populated by main(). Tool/Resource/Prompt callbacks read from here.
# Accessing them before main() runs will raise KeyError — which is the
# behaviour we want, since the server has no business serving requests
# before --project-root is set.
_state: dict = {}


def _todos_path() -> Path:
    return _state["project_root"] / ".claude" / "todos.md"


# ---------- Tools ----------

@mcp.tool()
def add_todo(text: str, priority: str = "med", due: str | None = None) -> dict:
    """Add a new todo to the project's todo list.

    Args:
        text: The todo content. Required, non-empty.
        priority: One of "high", "med", "low". Defaults to "med".
        due: Due date as YYYY-MM-DD, or null/omitted for no due date.

    Returns:
        The created todo (dict with id, done, prio, due, text).
    """
    return data.add(_todos_path(), text, priority=priority, due=due)


@mcp.tool()
def mark_done(id: int) -> dict:
    """Mark the todo with the given id as done. Returns the updated todo."""
    return data.mark_done(_todos_path(), id, done=True)


@mcp.tool()
def edit_todo(
    id: int,
    text: str | None = None,
    priority: str | None = None,
    due: str | None = None,
    done: bool | None = None,
) -> dict:
    """Edit fields of an existing todo. Pass only the fields you want to change.

    Args:
        id: The todo id.
        text: New text. Omit to keep existing.
        priority: New priority (high/med/low). Omit to keep existing.
        due: New due date YYYY-MM-DD; pass empty string to clear an existing date.
        done: True/False to set status. Use this to "undo" a completed todo.

    Returns:
        The updated todo.
    """
    return data.edit(
        _todos_path(),
        id,
        text=text,
        priority=priority,
        due=due,
        done=done,
    )


@mcp.tool()
def remove_todo(id: int) -> dict:
    """Remove the todo with the given id. Returns the removed todo."""
    return data.remove(_todos_path(), id)


@mcp.tool()
def open_dashboard() -> str:
    """Return the URL of the read-only web dashboard for the todo list.

    Opening this URL in a browser shows the todos rendered as a table.
    The dashboard re-reads the file on every request.
    """
    return f"http://localhost:{_state['dashboard_port']}"


# ---------- Resource ----------

@mcp.resource("todo://list", mime_type="text/markdown")
def todos_list() -> str:
    """The full todos.md content as markdown, served as a Resource."""
    path = _todos_path()
    if not path.exists():
        return "# Todos\n\n_(empty — no todos yet)_\n"
    return path.read_text(encoding="utf-8")


# ---------- Prompt ----------

@mcp.prompt()
def weekly_review() -> str:
    """Generate a prompt for reviewing the past week's todos."""
    path = _todos_path()
    contents = (
        path.read_text(encoding="utf-8")
        if path.exists()
        else "(no todos.md yet)"
    )
    return (
        "Please do a weekly review of these todos.\n\n"
        "1. List what was completed (status = done).\n"
        "2. List what's still open, sorted by priority.\n"
        "3. Flag any items with a due date that has passed.\n"
        "4. Suggest the top 3 todos to focus on next week.\n\n"
        f"Current todos:\n\n```markdown\n{contents}\n```\n"
    )


# ---------- Entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="todo-mcp",
        description="MCP server exposing a project-local todo list",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Project root containing .claude/todos.md",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    if not root.is_dir():
        print(
            f"error: --project-root {root} is not a directory",
            file=sys.stderr,
        )
        sys.exit(1)
    _state["project_root"] = root

    # Start the HTTP dashboard before entering the MCP loop.
    _state["dashboard_port"] = dashboard.start(_todos_path)

    # All log lines go to stderr — stdout is owned by the MCP stdio transport.
    print(f"[todo-mcp] project-root: {root}", file=sys.stderr)
    print(
        f"[todo-mcp] dashboard:    http://localhost:{_state['dashboard_port']}",
        file=sys.stderr,
    )

    mcp.run()


if __name__ == "__main__":
    main()
