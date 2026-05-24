# todo-mcp-server — MVP Spec

> Status: Design locked, implementation not started
> Last updated: 2026-05-23
> Owner: Zhang Yu

## 0. Context

学习项目。目的是把已有的 `todo-manager` Claude Code Skill（位于
`~/Project/ccDir/KevinDemo/.claude/skills/todo-manager/`）的能力，借
MCP 协议重新实现一遍，主要为了：

1. 真正动手写一个 MCP server，把协议链路打穿（注册、stdio、tool/resource/prompt 三原语）
2. 借这个场景对比 Skill 和 MCP 在 Claude Code 中的协作 / 竞争关系
3. 顺便给 todo 加一个浏览器可访问的 dashboard

数据 source of truth 仍是 `KevinDemo/.claude/todos.md`。Skill 和 MCP
共用这份文件，避免数据漂移。

## 1. 工程结构

```
todo-mcp-server/
├── pyproject.toml                 # Python 项目配置 + 依赖声明
├── README.md
├── docs/
│   └── MVP_SPEC.md                # 本文档
└── src/todo_mcp/
    ├── __init__.py
    ├── server.py                  # MCP 入口 (stdio transport)
    ├── data.py                    # todos.md 读写，移植自 KevinDemo 的 todo.py
    ├── dashboard.py               # 内嵌 HTTP server
    └── templates/
        └── index.html             # Dashboard 页面
```

## 2. 数据策略

- **Source of truth**: `<project-root>/.claude/todos.md`
- **项目根定位**: 通过启动参数 `--project-root <path>` 传入
- **格式延续**: `- [ ] #ID [priority] (due: DATE) text`
  - 与 `todo-manager` Skill 中 `scripts/todo.py` 的格式完全一致
  - `data.py` 应能直接读取 Skill 写入的文件，反之亦然

## 3. 进程模型

- MCP server 启动时**同步**起 HTTP server，两者**同生命周期**
- Transport: `stdio`
- HTTP server 默认端口 `8765`；冲突时 `+1` 探测，最多试 10 次
- HTTP server 服务停止时间 = MCP server 退出时间

## 4. Tools（5 个）

| Tool             | 参数                                                | 返回                       |
|------------------|-----------------------------------------------------|----------------------------|
| `add_todo`       | `text: str, priority?: str = "med", due?: str`      | 新建的 todo 对象           |
| `mark_done`      | `id: int`                                           | 更新后的 todo 对象         |
| `edit_todo`      | `id: int, text?, priority?, due?, done?: bool`      | 更新后的 todo 对象         |
| `remove_todo`    | `id: int`                                           | 被删除的 todo 对象         |
| `open_dashboard` | —                                                   | `http://localhost:<port>`  |

设计要点：

- 没有 `list_todos` tool — 由 Resource 暴露（"读靠 Resource，写靠 Tool"）
- `edit_todo` 通过 `done` 参数吸收 `mark_undone`，少一个接口
- 所有写操作返回修改后的 todo，Claude 不必再读 Resource 就知道结果

## 5. Resources（1 个）

| 字段       | 值                                  |
|------------|-------------------------------------|
| URI        | `todo://list`                       |
| mimeType   | `text/markdown`                     |
| 内容       | 当前 `.claude/todos.md` 全文        |
| 订阅       | MVP 不支持 subscribe，只支持 read   |

## 6. Prompts（1 个）

| 字段        | 值                                                              |
|-------------|-----------------------------------------------------------------|
| name        | `weekly_review`                                                 |
| description | 复盘本周已完成 / 未完成 / 过期的 todos                          |
| 触发方式    | 用户在 Claude Code 的 `/` 菜单手动选用（user-controlled）       |
| 行为        | 把当前 todos.md + 复盘指令模板注入新对话                        |

## 7. 错误处理

- Tool 失败：用 MCP 协议 `isError: true` 返回；message 为 Python exception 转字符串
- Resource read 失败：抛 `ResourceNotFound`
- HTTP 端口探测全部失败：MCP server 也不启动，直接报错退出

## 8. 注册方式

```bash
claude mcp add todo \
  --scope user \
  -- \
  python -m todo_mcp.server --project-root /Users/zhangyu/Project/ccDir/KevinDemo
```

- `--scope user`：全局可用，跨项目可见
- `--project-root`：server 自身的启动参数，告诉它服务哪个项目的 todos.md
- 一个 server 实例只服务一个 project-root；想服务多个项目就多注册几个实例

## 9. Dashboard UI（MVP 极简版）

- **只读**：表格展示 status / ID / priority / due / text
- **无交互**：不能在网页上勾选、编辑、删除
- **不缓存**：服务端每次 GET 重读 `.claude/todos.md`
- 后续迭代：SSE 推送实时刷新、编辑能力

## 10. MVP 明确不做

- ❌ `mark_undone` 单独 tool（已合并到 `edit_todo`）
- ❌ `list_todos` tool（由 Resource 取代）
- ❌ Resource subscribe / SSE 推送
- ❌ 多项目并发服务（一个 server 实例对应一个 project-root）
- ❌ Dashboard 上的编辑能力

## 11. 与 todo-manager Skill 的关系 — 待定

- MVP 完成前：Skill 原样保留，与 MCP server 并存
- MVP 完成后：实证决策，3 种可能
  1. 保留 Skill 原样 — 如果发现它仍提供 MCP 不能给的价值
  2. 删除 Skill — 如果 MCP 工具描述写得够好，Claude 自能正确使用
  3. 退化为极短 SKILL.md — 只保留沟通风格 / 业务规则约束

**不在 MVP 阶段拍板**。等用过几天再回头判断。

## 12. 学习目标 checklist

跑完 MVP 应该能回答：

- [ ] 怎么从零起一个 MCP server（pyproject、entry point、stdio）
- [ ] 怎么定义 tool 的 schema，Claude 才能正确调用
- [ ] Resources 和 Tools 在客户端的实际行为差异（Claude Code 怎么消费 Resource？）
- [ ] Prompts 的"user-controlled"特性具体在 Claude Code 里怎么触发
- [ ] MCP server 调试方法（stderr 日志、协议消息抓取）
- [ ] Skill 和 MCP server 同时存在时，Claude 的决策倾向
