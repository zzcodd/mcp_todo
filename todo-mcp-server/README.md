# todo-mcp-server

一个用于学习的 MCP（Model Context Protocol）server：把一份纯文本 `todos.md`
的增删改查能力，通过 MCP 的 tool / resource / prompt 三种原语暴露出来，并附带
一个只读的浏览器看板。

## 它暴露了什么

- **5 个 tool**（`tools/call`）
  - `add_todo(text, priority="med", due=None)` —— 新增 todo
  - `mark_done(id)` —— 标记完成
  - `edit_todo(id, text?, priority?, due?, done?)` —— 编辑指定字段
  - `remove_todo(id)` —— 删除
  - `open_dashboard()` —— 返回只读看板的 URL
- **1 个 resource**（`resources/read`）
  - `todo://list` —— 当前 `todos.md` 的完整内容（markdown）
- **1 个 prompt**（`prompts/get`）
  - `weekly_review` —— 把当前 todos 内联进一段"周复查"指令模板

## 数据存储

所有数据落在 `--project-root` 指定目录下的 `.claude/todos.md`，行格式：

```
- [STATUS] #ID [PRIORITY] (due: YYYY-MM-DD)? TEXT
```

这份格式刻意与配套的 todo-manager Skill 保持一致，因此 Skill 与本 server 可以
读写同一份文件而互不破坏——`.claude/todos.md` 是唯一的事实来源。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate   # 需要 Python >= 3.10
pip install -e .
```

## 使用

MCP server 走 stdio 传输，通常由一个 client 拉起，而不是手动直接运行。

**用配套的 mini-mcp-client 驱动**（最直接的学习方式）：

```bash
mini-mcp todo-mcp --project-root /path/to/your/project
```

**接入 Claude Code**（在 MCP 配置的 `mcpServers` 中注册）：

```jsonc
{
  "mcpServers": {
    "todo": {
      "command": "todo-mcp",
      "args": ["--project-root", "/path/to/your/project"]
    }
  }
}
```

## 浏览器看板

server 启动时会在守护线程里附带起一个只读 HTTP 看板（默认 `http://localhost:8765`，
端口被占用则顺延），把 todos 渲染成表格，每次请求都重新读盘。调用 `open_dashboard`
工具可拿到它的 URL。

> 看板随 server 进程存活——client 退出、server 子进程被终止后，看板也随之消失。

## 设计文档

完整规格见 [`docs/MVP_SPEC.md`](docs/MVP_SPEC.md)。

## 这个项目教会你什么

从零搭一个真实可跑的 MCP server，端到端体会：

1. stdio 传输 + tool / resource / prompt 三原语 + 客户端注册流程；
2. MCP server 与 Claude Code Skill 操作同一份数据时如何协作（或竞争）；
3. 业务逻辑（`data.py`，零 MCP 认知）与协议适配层（`server.py`，仅做转接）如何
   彻底分离——这是把现有业务包装成 MCP server 的标准姿势。
