# mini-mcp-client

一个极简的交互式 MCP 客户端。它通过 stdio 传输启动任意一个 MCP server，
让你在 REPL 里直接调用该 server 的 tools / resources / prompts。

你在这里扮演的，正是平时 Claude Code 在你工作流中扮演的角色——只是**去掉了
LLM**。这是端到端理解 MCP 协议最直接的方式。

## 安装

```bash
cd mini-mcp-client
python3 -m venv .venv && source .venv/bin/activate   # 需要 Python >= 3.10
pip install -e .
# 把你想驱动的 server 也装进同一个 venv：
pip install -e ../todo-mcp-server
```

> 注意：client 是按**裸命令名**（如 `todo-mcp`）去 fork server 子进程的，它依赖
> 该命令在 `PATH` 上。**激活 venv** 正是为了把 `.venv/bin` 加入 `PATH`，这样
> `todo-mcp` 才找得到——不激活会报 `FileNotFoundError`。

## 使用

```bash
mini-mcp todo-mcp --project-root /path/to/your/project
```

一次典型会话：

```
[mini-mcp] launching: todo-mcp --project-root /...
[mini-mcp] initializing...
[mini-mcp] connected to: todo v1.x.x
[mini-mcp] capabilities: tools, resources, prompts

mini-mcp connected. Type 'help' for commands, 'quit' to exit.

>> list-tools
* add_todo
    Add a new todo to the project's todo list.
    input schema keys: ['text', 'priority', 'due']
...

>> call add_todo text="买菜" priority=high
{
  "id": 1,
  "done": false,
  "prio": "high",
  "due": null,
  "text": "买菜"
}

>> read todo://list
# Todos
...

>> prompt weekly_review
# Generate a prompt for reviewing the past week's todos.

[user]
Please do a weekly review of these todos.
...

>> quit
[mini-mcp] disconnected.
```

## 支持的命令

| 命令 | 作用 | 对应协议消息 |
|------|------|------------|
| `list-tools` | 列出所有工具及其 JSON Schema 字段 | `tools/list` |
| `list-resources` | 列出所有资源 | `resources/list` |
| `list-prompts` | 列出所有 prompt 模板 | `prompts/list` |
| `call <name> [key=val ...]` | 调用工具（参数自动转型） | `tools/call` |
| `read <uri>` | 读取资源（如 `read todo://list`） | `resources/read` |
| `prompt <name> [key=val ...]` | 渲染 prompt 模板 | `prompts/get` |
| `help` | 显示帮助 | — |
| `quit` / `exit` | 断开并退出 | — |

## 这个项目教会你什么

走完一次 REPL 会话，你会看到任何 MCP 客户端（包括 Claude Code）都要做的四类
消息交换：

1. `initialize` —— 能力握手
2. `tools/list` —— 枚举工具及其 JSON Schema
3. `tools/call` —— 带参数调用工具
4. `resources/read` / `prompts/get` —— 另外两个原语

阅读 `src/mini_client/cli.py`，找其中的 `Protocol message sent:` 注释——每一条都
精确指出紧随其后的 SDK 调用触发了哪个协议消息。
