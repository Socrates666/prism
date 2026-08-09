# prism × pi 对齐审计

> 目标：保证 prism 的所有设计增量都建立在 **pi agent 语义基线**之上，不另起炉灶。
> 这是阶段 7.6 的产出，也是"严格对齐 piagents"的依据。

## 0 · 前提：语言鸿沟

| | pi | prism |
|---|---|---|
| 语言 | TypeScript / Node | Python |
| 核心 SDK | `@earendil-works/pi-coding-agent` + `pi-agent-core` + `pi-ai` | 自写(prism/) |
| agent 内核 | IPython? **否** —— pi 是 Node 进程 | **是** —— IPython 共享命名空间(原则 8, prism 灵魂) |

**结论**：prism 不能"用 pi SDK"(语言不通, 且会丢掉 IPython 核心)。"严格对齐" = **语义 / 行为 / 事件协议 / prompt 对齐**，prism 是 pi agent 的 **Python 增量实现**。代码不共享，契约对齐。

---

## 1 · pi agent 语义基线（对齐目标）

源自 `docs/sdk.md` + `examples/extensions/subagent/`：

**state（Agent.state）**：`messages / model / thinkingLevel / systemPrompt / tools / streamingMessage / errorMessage`

**生命周期（AgentSession）**：
- `prompt(text)` 发消息等完成
- `subscribe(listener)` 订阅事件流
- `steer(text)` 流式中插队（本轮工具调用后送达）
- `followUp(text)` 流式后追加（agent 停下才送达）
- `abort()` / `dispose()`

**事件协议**：
`message_update`(`text_delta` / `thinking_delta`) · `tool_execution_start` / `tool_execution_update` / `tool_execution_end` · `message_start` / `message_end` · `turn_start` / `turn_end` · `agent_start` / `agent_end` · `queue_update` · `compaction_*` · `auto_retry_*`

**system prompt**：默认 prompt + `systemPromptOverride`（整体替换）+ `appendSystemPromptOverride(base)`（在默认基础上追加，含 `APPEND_SYSTEM.md`）

**工具**：`defineTool({name, label, description, parameters(TypeBox), execute})`；内置 `read/bash/edit/write/grep/find/ls`

**扩展**：`pi.on(event, cb)` / `pi.registerTool()` / `eventBus`

**子 agent**：`subagent` 工具 spawn **独立 pi 进程**（`--mode json -p --no-session`），独立 context window；single / parallel / chain 三模式

---

## 2 · prism 现状 vs pi 基线 —— 偏离项（需修正对齐）

| # | 维度 | pi 基线 | prism 现状 | 偏离 | 修正方向 |
|---|------|---------|-----------|------|---------|
| D1 | 事件命名 | `message_update`·`text_delta` / `tool_execution_start` / `tool_execution_end` | `message_delta` / `message_end` / `tool_start` / `tool_end` | 命名自创，不对齐 | emit 改 pi 命名（prism 增量 `patch_error`/`ext_error` 保留） |
| D2 | state 命名 | `messages` / `streamingMessage` / `errorMessage` | `history` / `last_result`（无 streaming/error） | 命名 + 字段不对齐 | `history→messages`；补 `streaming_message`/`error_message` |
| D3 | system prompt 机制 | override(替换) + append(追加 base) | 构造时一个字符串，无 override/append | 机制缺失 | 加 `system_prompt_override` / `append_system_prompt` |
| D4 | 生命周期语义 | `steer`(插队) vs `followUp`(收尾) 分离；显式 `subscribe` | `inject`(单一，无 steer/followUp 区分)；hooks["emit"] 隐式 | 语义粗糙 | inject 区分 steer/followUp；显式 subscribe API |
| D5 | compaction / thinking / retry | 有 | 无（早期砍了） | 功能缺失 | 评估补回（对齐 pi 完整性） |

---

## 3 · prism 增量（建在 pi 基础上，明确标注，**不是偏离**）

这些是 prism 有意为之的架构选择，每个都映射到一个 pi 基础 + prism 的差异化：

| 增量 | pi 基础 | prism 的不同（原则） | 为什么 |
|------|---------|---------------------|--------|
| **多 agent actor**（线程 + inbox + inject） | pi 单 session；子 agent = 独立进程 | 同进程线程并发（原则 15） | 共享命名空间魅力（原则 8），避免进程间通讯低效（原始痛点） |
| **patch 五点**（before/after/around × 5 点） | pi extension（`pi.on` 事件级 hook） | 更细粒度的 loop 内 hook（原则 11） | extension 只能监听事件，patch 能改 loop 内部（build_messages/execute_tools 等） |
| **workspace 闭包**（`make_file_tools(ws)`） | pi 子 agent 靠独立进程 cwd | 闭包绑定 workspace（原则 14） | 同进程多 agent 不能靠 cwd（进程级），闭包防踩踏 |
| **guard 护栏**（拦写 prism/） | pi 无（靠进程隔离天然防互写） | exec open 拦截（原则 2） | 同进程共享 ns，需硬护栏防 agent 改自身核心 |
| **@ 路由 + IPython 命名空间** | pi 无（独立 session） | 主 agent 共享 ns（原则 8/13） | prism 灵魂：用户与主 agent 等价，输入既是代码也是对话 |
| **ext/ 容错加载** | pi extension（类似发现机制） | per-file try/except + `register` 入口（原则 12） | 单个 ext 坏不炸全部（容错降级） |
| **能力分层**（main/sub kind） | pi 子 agent 也受限（指定 tools） | 子 agent **无裸 exec**（原则 13） | 同进程下子 agent 不能有 python 工具（会踩共享 ns） |

---

## 4 · 对齐动作清单（全部完成 ✅ 71 测试）

**P0 低风险高价值**：
- [x] D1 事件命名对齐 pi（message_update/tool_execution_*/message_start；同步 emit + 测试）
- [x] D3 system prompt override/append 机制（_resolve_system_prompt / append_to_system_prompt）
- [ ] 增量标注：每个增量模块 docstring 注明 "pi 基础 + prism 增量"（部分已标，后续 review 补全）

**P1 中风险（改 API）**：
- [x] D2 state 命名对齐（history→messages；补 streaming_message/error_message）
- [x] D4 inject 区分 steer/followUp（PriorityQueue 优先级）+ 显式 subscribe

**P2 功能补齐**：
- [x] D5 retry（auto_retry 事件）/ thinking_level / compact()（对齐 pi 完整 agent）

**不做（语言鸿沟）**：
- ✗ 复用 pi SDK（TS，prism 是 Python）
- ✗ 放弃 IPython 命名空间（prism 灵魂）
