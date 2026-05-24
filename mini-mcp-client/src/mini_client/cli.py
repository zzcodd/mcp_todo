"""Interactive MCP client.

Launches an MCP server as a subprocess over stdio, lets you call its
tools/resources/prompts from a REPL. You're playing the role that Claude
Code plays in your normal workflow — minus the LLM. This is the most
direct way to understand the protocol end to end.

Usage:
    mini-mcp <server-command> [server-args...]

Example:
    mini-mcp todo-mcp --project-root /Users/zhangyu/Project/ccDir/KevinDemo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl


# ---------- Argument coercion ----------
# Tools have JSON-Schema-typed parameters. Pydantic on the server will
# reject e.g. id="3" when the schema says id: integer. We do a tiny bit
# of "smart" coercion here so the REPL feels natural.

def _coerce(value: str) -> Any:
    """Coerce a string token into int/bool/None/string."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.lower() == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_kwargs(tokens: list[str]) -> dict[str, Any]:
    """Parse `key=value` tokens into a dict, with type coercion."""
    out: dict[str, Any] = {}
    for tok in tokens:
        if "=" not in tok:
            raise ValueError(f"expected key=value, got {tok!r}")
        k, v = tok.split("=", 1)
        out[k] = _coerce(v)
    return out


# ---------- Pretty printing ----------

def _pretty(obj: Any) -> str:
    """Render a Python object as indented JSON. Pydantic objects -> dict first."""
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


# ---------- REPL handlers ----------
# Each handler takes a ClientSession + parsed tokens and prints the result.
# All session calls are async because the SDK is async-only.

async def _cmd_help() -> None:
    print(
        "Commands:\n"
        "  list-tools                     List all available tools\n"
        "  list-resources                 List all available resources\n"
        "  list-prompts                   List all available prompts\n"
        "  call <name> [key=val ...]      Call a tool (values auto-cast)\n"
        "  read <uri>                     Read a resource (e.g. todo://list)\n"
        "  prompt <name> [key=val ...]    Get a prompt (renders the template)\n"
        "  help                           Show this help\n"
        "  quit / exit                    Disconnect and exit\n"
        "\n"
        "Examples:\n"
        '  call add_todo text="买菜" priority=high\n'
        "  call mark_done id=3\n"
        "  read todo://list\n"
        "  prompt weekly_review\n"
    )


async def _cmd_list_tools(session: ClientSession) -> None:
    # Protocol message sent: tools/list
    # Server responds with the list of tools it registered (via @mcp.tool).
    result = await session.list_tools()
    for tool in result.tools:
        print(f"* {tool.name}")
        if tool.description:
            # First line of description = Claude's snap judgment of when to use
            print(f"    {tool.description.splitlines()[0]}")
        keys = list(tool.inputSchema.get("properties", {}).keys())
        print(f"    input schema keys: {keys}")
        print()


async def _cmd_list_resources(session: ClientSession) -> None:
    # Protocol message sent: resources/list
    result = await session.list_resources()
    if not result.resources:
        print("(no resources)")
        return
    for r in result.resources:
        print(f"* {r.uri}")
        if r.name:
            print(f"    name: {r.name}")
        if r.description:
            print(f"    desc: {r.description}")
        if r.mimeType:
            print(f"    mime: {r.mimeType}")
        print()


async def _cmd_list_prompts(session: ClientSession) -> None:
    # Protocol message sent: prompts/list
    result = await session.list_prompts()
    if not result.prompts:
        print("(no prompts)")
        return
    for p in result.prompts:
        print(f"* {p.name}")
        if p.description:
            print(f"    {p.description}")
        if p.arguments:
            print(f"    arguments: {[a.name for a in p.arguments]}")
        print()


async def _cmd_call(session: ClientSession, name: str, kwargs: dict[str, Any]) -> None:
    # Protocol message sent: tools/call
    # params = { name: <tool-name>, arguments: <kwargs dict> }
    # Server validates kwargs against the tool's JSON schema, runs the
    # Python function, packages the return value as MCP content.
    result = await session.call_tool(name, arguments=kwargs)

    # MCP tool results come back as a list of content blocks (text/image/etc.).
    # For our todo-mcp server every tool returns a dict, which the SDK wraps
    # as TextContent with a JSON-serialized string. We unpack and re-pretty.
    if result.isError:
        print("[error]")
    for block in result.content:
        # Most common case: TextContent
        if hasattr(block, "text"):
            # Try to parse as JSON for nicer display; fall back to raw.
            try:
                print(_pretty(json.loads(block.text)))
            except (json.JSONDecodeError, TypeError):
                print(block.text)
        else:
            print(_pretty(block))

    # The 1.x SDK also exposes structuredContent for typed results.
    if hasattr(result, "structuredContent") and result.structuredContent:
        print("--- structured ---")
        print(_pretty(result.structuredContent))


async def _cmd_read(session: ClientSession, uri: str) -> None:
    # Protocol message sent: resources/read
    # AnyUrl is pydantic's URL type; the SDK accepts a str too but the
    # canonical form is AnyUrl. We use it explicitly to make the type clear.
    result = await session.read_resource(AnyUrl(uri))
    for content in result.contents:
        # Resource content can be text or blob (base64). We only handle text.
        if hasattr(content, "text"):
            print(content.text)
        else:
            print(f"[binary content, mime: {getattr(content, 'mimeType', '?')}]")


async def _cmd_prompt(session: ClientSession, name: str, kwargs: dict[str, Any]) -> None:
    # Protocol message sent: prompts/get
    # The server runs the @mcp.prompt-decorated function with the given args
    # and returns the rendered message list (what would be inlined into a
    # conversation if a user picked this prompt from a / menu).
    result = await session.get_prompt(name, arguments=kwargs)
    if result.description:
        print(f"# {result.description}\n")
    for msg in result.messages:
        # Each message has a role + content. For todo-mcp's weekly_review,
        # there'll be one user-role message containing the rendered template.
        print(f"[{msg.role}]")
        content = msg.content
        if hasattr(content, "text"):
            print(content.text)
        else:
            print(_pretty(content))
        print()


# ---------- REPL main loop ----------

async def _repl(session: ClientSession) -> None:
    """Read-eval-print loop. Returns when user types quit/exit or hits EOF."""
    print("mini-mcp connected. Type 'help' for commands, 'quit' to exit.\n")
    while True:
        try:
            # input() is blocking. We offload it to a thread executor so the
            # SDK's background reader task on the asyncio loop keeps running.
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(">> ")
            )
        except EOFError:
            print()
            return

        line = line.strip()
        if not line:
            continue

        # shlex handles quoted strings, e.g. text="买 菜" stays as one token.
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            print(f"parse error: {e}")
            continue

        cmd, args = tokens[0], tokens[1:]

        try:
            if cmd in ("quit", "exit"):
                return
            elif cmd == "help":
                await _cmd_help()
            elif cmd == "list-tools":
                await _cmd_list_tools(session)
            elif cmd == "list-resources":
                await _cmd_list_resources(session)
            elif cmd == "list-prompts":
                await _cmd_list_prompts(session)
            elif cmd == "call":
                if not args:
                    print("usage: call <tool-name> [key=value ...]")
                    continue
                await _cmd_call(session, args[0], _parse_kwargs(args[1:]))
            elif cmd == "read":
                if not args:
                    print("usage: read <uri>")
                    continue
                await _cmd_read(session, args[0])
            elif cmd == "prompt":
                if not args:
                    print("usage: prompt <name> [key=value ...]")
                    continue
                await _cmd_prompt(session, args[0], _parse_kwargs(args[1:]))
            else:
                print(f"unknown command: {cmd!r}. Type 'help'.")
        except Exception as e:
            # Don't crash the REPL on per-command errors. Show & continue.
            print(f"[error] {type(e).__name__}: {e}")


# ---------- Async main ----------

async def _async_main(command: str, args: list[str]) -> None:
    """Launch the server subprocess, run the REPL, then clean up."""

    # StdioServerParameters describes the subprocess to spawn.
    # The client SDK will fork it, attach to its stdin/stdout, and hand us
    # the (read, write) streams as bidirectional message channels.
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=None,    # inherit parent env; pass dict to restrict
    )

    print(f"[mini-mcp] launching: {command} {' '.join(args)}", file=sys.stderr)

    # stdio_client is an async context manager. On enter it spawns the
    # subprocess. On exit it terminates the subprocess and closes streams.
    async with stdio_client(server_params) as (read, write):
        # ClientSession wraps the raw streams with the JSON-RPC protocol layer.
        # It owns a background task that reads incoming messages and routes
        # responses back to the awaiting call site by request id.
        async with ClientSession(read, write) as session:

            # Step 1: initialize handshake.
            # Protocol message sent: initialize
            # Server replies with serverInfo (name, version) and capabilities
            # (which of tools/resources/prompts/logging it supports).
            # Without this call no other call works -- the SDK enforces it.
            print("[mini-mcp] initializing...", file=sys.stderr)
            init = await session.initialize()
            print(
                f"[mini-mcp] connected to: {init.serverInfo.name} "
                f"v{init.serverInfo.version}",
                file=sys.stderr,
            )
            caps = init.capabilities
            features = [
                name for name, val in (
                    ("tools", caps.tools),
                    ("resources", caps.resources),
                    ("prompts", caps.prompts),
                    ("logging", caps.logging),
                ) if val is not None
            ]
            print(
                f"[mini-mcp] capabilities: {', '.join(features) or '(none)'}",
                file=sys.stderr,
            )
            print(file=sys.stderr)

            # Step 2: hand control to the REPL.
            await _repl(session)

    # stdio_client's __aexit__ has now terminated the subprocess.
    print("[mini-mcp] disconnected.", file=sys.stderr)


# ---------- Entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mini-mcp",
        description="Minimal interactive MCP client (stdio transport).",
        epilog="Example: mini-mcp todo-mcp --project-root /path/to/project",
    )
    parser.add_argument(
        "server_command",
        help="The command to launch the MCP server (e.g. 'todo-mcp').",
    )
    parser.add_argument(
        "server_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the server command.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(_async_main(args.server_command, args.server_args))
    except KeyboardInterrupt:
        print("\n[mini-mcp] interrupted.", file=sys.stderr)


if __name__ == "__main__":
    main()
