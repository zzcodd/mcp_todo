# MCP 学习项目 — mini-mcp-client & todo-mcp-server

> 我的 MCP（Model Context Protocol）学习记录。
> 目标：从零搭一个 MCP server + 一个极简 client，端到端搞懂 MCP 协议，
> 并把它真正接入 Claude Code / Cursor。
>
> 记录日期：2026-05-26

## 项目构成

| 文件夹 | 是什么 | 作用 |
|--------|--------|------|
| `mini-mcp-client/` | 极简交互式 MCP 客户端（去掉 LLM 的 Claude Code） | 用 REPL 手动调工具，看清协议每一步 |
| `todo-mcp-server/` | 我做的 MCP server | todo 增删改查（tool）+ 列表（resource）+ 周复查（prompt）+ 浏览器看板 |

---

## 一、我对 MCP 的理解

### 1. 一句话本质

> **MCP = 把"调用本地函数"变成"给另一个进程发 JSON-RPC 消息"。**
> 两端各有一个 SDK 做镜像翻译：client SDK 把"调用"编码成消息发出，
> server SDK 把消息解码成"函数调用"执行。中间靠 stdio 字节流 + 请求 id 配对对齐异步收发。

### 2. 四层结构（应用层是我写的，下面三层 SDK 全包）

```
① 应用层   决策 / 业务逻辑        ← 我写（client: 决定调什么；server: 工具实现）
② 能力层   tools/resources/prompts ← SDK 给机制，我填内容（声明 + schema）
③ 协议层   JSON-RPC 2.0           ← SDK 全包（编解码、id 配对）
④ 传输层   stdio / HTTP           ← SDK 全包（进程/连接生命周期）
```

换传输（stdio → HTTP）只动 ④ 层，①②③ 不用改——这是分层的价值。

### 3. 三个原语（关键区别在"谁触发"）

| 原语 | 谁控制 | 触发方式 | 能否改变世界 |
|------|--------|----------|--------------|
| **tool** | model-controlled | LLM 推理中**自主**调用 | ✅ 有副作用（写文件、发请求…） |
| **resource** | application-controlled | 应用按需读取 | ❌ 只读数据 |
| **prompt** | user-controlled | 用户**主动**点 `/` 菜单 | ❌ 只产出文本 |

**最关键的领悟**（一开始没分清 prompt 和 tool）：
`prompt` 本身**只产出一段文本**（把数据内联进模板），**真正的分析是 LLM 收到这段文本之后做的**。
> 验证：我在 Cursor 里跑 `/mcp__todo_kevin__weekly_review`，server 端的 `weekly_review()`
> 只是拼了段"复查指令 + 当前 todos"，而"距今还有 4 天""按优先级排序""Top 3 推荐"
> 这些都是 LLM 自己算的——模板里根本没有。**server 出题，LLM 出答。**

### 4. client / server 谁干什么

- **client**：决定"做什么"（人 or LLM）。SDK 负责：起传输、编码请求、写读流、按 id 配对响应、解码。
- **server**：定义业务逻辑 + 用装饰器声明能力 + 调 `run()` 交出控制权。SDK 负责：监听、解析、路由、校验入参、打包返回、**从函数签名自省生成 JSON Schema**。
- **重要**：`initialize` / `tools/list` 等是 **SDK 内置应答**（读它自己的注册表），**不碰我写的函数**；只有 `tools/call` / `resources/read` / `prompts/get` 才路由到我的函数。

### 5. 接入 LLM 后的核心循环（tool-use loop）

```
initialize 握手 → 自动 tools/list（把工具喂给 LLM）
   → LLM 看工具清单 + 用户消息，决定调哪个工具
   → 产出 tool_use → client 转成 tools/call 发给 server
   → 结果回灌 LLM → LLM 继续推理或给最终答复
```

Claude Code 相比我的 mini-mcp client，只是把"人在 REPL 决策"换成"LLM 决策循环"，**协议骨架完全一样**。

---

## 二、如何接入 Claude Code / Cursor（我的集成理解）

**核心认知**：我**只需要给出 server 的"启动配方"**，client 这一侧由 Claude Code / Cursor 充当——
它会在会话里自己 fork server 子进程、走 initialize、自动 tools/list。所以配置里 `--` 后面只出现 server。

**命令**：
```bash
claude mcp add todo_kevin -s user -- \
  /Users/zhangyu/Project/mcp/mini-mcp-client/.venv/bin/todo-mcp \
  --project-root /Users/zhangyu/Project/ccDir/KevinDemo
```

**为什么这么写**：
- `--`：分隔符，告诉 `claude` 后面都是 server 的启动命令，否则 `--project-root` 会被 claude 自己吞掉。
- **绝对路径**到 venv 里的 `todo-mcp`：Claude Code 启动 server 时**不会激活我的 venv**，只有绝对路径（其 shebang 指向 venv 的 python3.12）能保证用对解释器。
- `-s user`：作用域选 user，所有项目都能用（因为它固定管 KevinDemo 的 todos，相当于我的全局个人待办）。

**配置 ≈ 代码里的 StdioServerParameters**：
配置里的 `command` + `args`，本质就是 mini-mcp 代码里 `StdioServerParameters(command=..., args=...)`——一个写死在代码、一个声明在配置，回答的是同一个问题"client 要 fork 哪个进程"。

**验证生效**：
- 斜杠命令 `/mcp__<server名>__<prompt名>` → 触发 prompt 原语（user-controlled）。
- 对话里说"帮我加一条 todo" → LLM 自动调 `mcp__todo_kevin__add_todo`（tool 原语，model-controlled）。
- ⚠️ 新加的 server **当前会话不自动加载，要重开会话**才生效。

---

## 三、踩过的坑

1. **Python 版本**：系统默认 `python3` 是 3.9.6，不满足项目要求的 `>=3.10`。
   → 用 Homebrew 的 `/opt/homebrew/bin/python3.12` 建 venv。
2. **公网 PyPI 连不通**（SSLError / 超时）。
   → 加清华镜像：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .`
3. **client 报 `FileNotFoundError: 'todo-mcp'`**：client 按**裸命令名** fork server，依赖 PATH。
   → 必须 `source .venv/bin/activate` 把 `.venv/bin` 加进 PATH。
4. **接入 Claude Code 时同样的坑**：Claude 不激活 venv。
   → 配置里用 `todo-mcp` 的**绝对路径**，而不是裸命令名。
5. **REPL 里 `>>` 夹杂 `INFO Processing request...`**：这是 server 把日志打到 stderr，和输入混显，**正常现象**，无视即可。
6. **todo 的 id**：`add` 的新 id 接着当前最大值递增；`mark_done id=N` 标的是**已存在**的那条，不是刚加的。
7. **浏览器看板随 server 进程存活**：client 一退出，server 子进程被终止，`localhost:8765` 也随之消失——要在 `quit` 之前打开看。

---

## 四、收获

- 把"Claude Code 调工具"这件平时的黑盒，拆到了**字节级**：能说清从斜杠命令/自然语言到 JSON-RPC 报文、再到 server 函数执行的完整链路。
- 想通了**为什么分发 MCP server 只需要 server**——client 是用户的 IDE 提供的。
- 分清了 **tool / resource / prompt** 的本质区别（谁触发、能否改变世界、谁做分析）。
- 理解了 SDK 的职责边界：**我只写业务 + 一行声明，协议与传输全归 SDK**；`initialize`/`list` 是 SDK 内置应答，不碰我的代码。
- 落地了一个**真实可用**的个人 todo MCP server，并成功接入 Cursor。

### 下一步

- [ ] 把 server 发布出去（GitHub / PyPI，支持 `uvx` 免装即用）让别人也能用。
- [ ] 尝试把 mini-mcp client 的 `_repl` 换成真实 LLM 循环，做一个会自己调工具的最小 agent。
