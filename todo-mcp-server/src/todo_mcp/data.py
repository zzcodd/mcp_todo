"""Read/write the shared .claude/todos.md file.

The on-disk format is intentionally identical to the todo-manager Skill's
scripts/todo.py, so the Skill and this MCP server can coexist on the same
file without trampling each other.

Line grammar:
    - [STATUS] #ID [PRIORITY] (due: YYYY-MM-DD)? TEXT
"""
from __future__ import annotations

import re
from pathlib import Path

PRIORITIES: tuple[str, ...] = ("high", "med", "low")

_LINE_RE = re.compile(
    r"^- \[(?P<done>[ x])\] #(?P<id>\d+) \[(?P<prio>high|med|low)\]"
    r"(?: \(due: (?P<due>\d{4}-\d{2}-\d{2})\))? (?P<text>.+)$"
)

Todo = dict  # alias used for documentation only


def load(path: Path) -> list[Todo]:
    """Return all parseable todos from the file. Lines that don't match are skipped."""
    if not path.exists():
        return []
    todos: list[Todo] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        todos.append({
            "id": int(m["id"]),
            "done": m["done"] == "x",
            "prio": m["prio"],
            "due": m["due"],
            "text": m["text"],
        })
    return todos


def dump(path: Path, todos: list[Todo]) -> None:
    """Write the full list back. Header (title + format comment) is regenerated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Todos",
        "",
        "<!-- Format: - [ ] #ID [priority] (due: YYYY-MM-DD) text -->",
        "",
    ]
    for t in sorted(todos, key=lambda x: x["id"]):
        mark = "x" if t["done"] else " "
        due = f" (due: {t['due']})" if t["due"] else ""
        lines.append(f"- [{mark}] #{t['id']} [{t['prio']}]{due} {t['text']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add(path: Path, text: str, priority: str = "med", due: str | None = None) -> Todo:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")
    todos = load(path)
    new_id = max((t["id"] for t in todos), default=0) + 1
    todo: Todo = {
        "id": new_id,
        "done": False,
        "prio": priority,
        "due": due,
        "text": text,
    }
    todos.append(todo)
    dump(path, todos)
    return todo


def mark_done(path: Path, todo_id: int, done: bool = True) -> Todo:
    todos = load(path)
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = done
            dump(path, todos)
            return t
    raise ValueError(f"No todo with id #{todo_id}")


def edit(
    path: Path,
    todo_id: int,
    *,
    text: str | None = None,
    priority: str | None = None,
    due: str | None = None,
    done: bool | None = None,
) -> Todo:
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")
    todos = load(path)
    for t in todos:
        if t["id"] == todo_id:
            if text is not None:
                t["text"] = text
            if priority is not None:
                t["prio"] = priority
            if due is not None:
                t["due"] = due or None
            if done is not None:
                t["done"] = done
            dump(path, todos)
            return t
    raise ValueError(f"No todo with id #{todo_id}")


def remove(path: Path, todo_id: int) -> Todo:
    todos = load(path)
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            removed = todos.pop(i)
            dump(path, todos)
            return removed
    raise ValueError(f"No todo with id #{todo_id}")
