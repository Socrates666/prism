# prism

> 名字: 棱镜把一束光分成多束 —— 这个工具的核心机制:**一个 IPython 内核,分出多个 agent / 多个长任务会话**。被 PrimeAgent 启发,致敬 pi 的简洁。

---

## 一句话形态

prism 是一个跑在 **IPython 内核**里的、前端是**增强 IPython REPL**(用户与 agent 共享命名空间、等价)的、**多 agent 同进程通讯**的、**输入即授权零揣测**的、靠 **before/after/around 扩展点 + 注册表**实现**增量扩建式自我修复**的、**可变区=人格插件**(全局共享非单例、热插拔)的、靠可插拔后端解跨会话传递的、追求**无中断日常交互**的简单 agent 工具。

> **核心只依赖接口,实现全可插拔**:daemon/mem0/模型/文档后端全可换。
> **自我修复 = 自我扩建**:只 add 进注册表,不 overwrite 核心 —— 绕开 reload-vs-实例 冲突。

---

## 种子(用户原话)

> "使用 ipython 实现跨会话的 agent 交互可不可行"
> "我想用 primeagent 的那种 agent 调用方式,然后在我的实践中也经常需要开多个会话来思考和推进同一个问题,会话间的信息传递很低效,想探索一种方案处理这个问题"

---

## 设计哲学 / 核心原则

这些原则**没有一个**是用户一开始说得清的,全是被诘问一巴掌一巴掌逼出来的。每条都值得在实现时死守。

### 原则 1 · 输入即授权(零揣测)
用户输入就是命令,agent 不回头质疑、不二次确认。zcode 烦就烦在"中断问蠢问题"。agent 的角色是**用户延伸的手**,不是替用户把关的大脑。

### 原则 2 · 硬护栏只护 agent 自身运作
护栏的判据是**会不会破坏 agent 自身运作**。客观、可机械识别、硬编码,不靠 LLM 揣测。护栏语义现在精确化为(**见原则 10/11**):**不允许 overwrite 核心代码**(`prism/`),允许增量扩建(add 进注册表)+ 可变区容错降级。

### 原则 3 · 跨会话状态是 agent 的器官
agent 的记忆 / 跨会话状态是 agent 自身的一部分,受原则 2 保护,是持久化的第一公民。

### 原则 4 · 灵活靠 IPython 运行时白送
agent 是 IPython 命名空间里的活对象。"加能力"= REPL 里写代码注册,立即生效。

### 原则 5 · 无中断交互(北极星)
不被提问打断(输入即授权)/ 不被状态管理打断(周期备份)/ 不被长任务阻塞(多长任务会话)。

### 原则 6 · 持久化是核心地基
周期备份 + 记忆后端 + 文档后端,防崩溃 + 解跨会话传递。

### 原则 7 · 后端全可插拔(依赖接口)
核心只依赖后端接口(RuntimeBackend / MemoryBackend / DocStore / ModelBackend),实现全可换。

### 原则 8 · 前端是增强 IPython REPL(用户与 agent 等价)
前端不是聊天框,是增强 IPython REPL。用户和 agent 共享命名空间,平等。输入既是代码也是对话。

### 原则 9 · 显示自举(agent 内部 hooks)
显示方法是 agent 在运行时创造的。外壳只在 agent 内部提供 hooks(emit/guard 等可替换回调),agent 改 hooks → 创造任何显示方法。

### 原则 10 · 默认 agent 实现 immutable + 扩展层隔离
系统有**绝对不能改的部分:默认 agent 实现**(即抄 prime-agent 的 `agent_loop.py` —— function-calling 循环)。它是 **immutable base**, 所有扩展的地基, 永不被 overwrite。

agent 修改自己**只允许在扩展层增量扩建**(add patch/tool/prompt 进注册表), 扩展层跟核心实现**物理隔离**(`ext/` vs `prism/`)。这绕开 `reload`-vs-实例 冲突:不 reload base, 只加载扩展;已有实例(base 代码)继续跑 + 通过注册表动态查询看见新增。"修 bug"=加 patch(advice), 不覆盖原函数。

> 澄清"核心只读":不是"agent 完全不能改自己", 而是"**默认实现不改 + 扩展层可改**"。agent 通过扩展改变行为, 不碰 base。安全模型 = **immutable base + 增量扩展(隔离)**。

### 原则 11 · 扩展点 patch 系统(before/after/around)
agent_loop 的关键决策点设计为 **patchable**——查询 patch 注册表。每个扩展点支持 **before / after / around**:
- **before** — 扩展点前运行(可改输入、可阻止)
- **after** — 扩展点后运行(可改输出)
- **around** — 包裹扩展点(可完全替换、可调用原逻辑)

agent 加 patch 影响行为,**不改 agent_loop 本体**。这统一了:显示自举(emit hooks = patch)、可变区(注册表)、增量扩建(add)。

**扩展点清单**(agent_loop 的 patchable 点):
- `build_messages` — 构造发给 LLM 的 messages
- `stream_response` — 流式取 LLM 响应
- `execute_tools` — 执行工具调用
- `should_stop` — 终止判断
- `emit` — 事件输出

### 原则 12 · 可变区 = 人格插件(全局共享非单例,热插拔)
可变区(`ext/`)是 agent 的"人格插件":
- **定义全局共享**(注册表池,所有 agent 可见可选)
- **每个 agent 各自实例化**(非单例,改自己实例不影响别人)
- **热插拔**(运行时 load/unload 实例)
- **容错降级**(加载 try/except,坏了跳过不挂核心)

---

## 被照亮的维度(按诘问出现顺序)

| # | 维度 | 来源 |
|---|------|------|
| 1 | 【调用范式】RLM / persistent IPython / subagent-as-function | 认知 PrimeAgent |
| 2 | 【路线】自搓(非 pi 扩展,非 deepagents) | 基底审视 |
| 3 | 【舒服 = 输入即授权】zcode 烦在问蠢问题 | "pi 比 zcode 舒服"拆解 |
| 4 | 【护栏判据】破坏 agent 自身运作 + 硬编码 | force push 处境逼出 |
| 5 | 【状态 = agent 器官】受硬护栏保护 | 推论焊点 |
| 6 | 【daemon】Unix daemon,Windows 走不通 → 远程 Linux | "daemon 是啥"澄清 |
| 7 | 【灵活 = IPython 运行时】 | "灵活机制"拆解 |
| 8 | 【持久化三件套】周期备份 + 记忆 + 文档 | "结束才备份"被否 |
| 9 | 【无中断交互三层】 | 北极星拆解 |
| 10 | 【daemon 可插拔】 | 用户修正 |
| 11 | 【后端全可插拔】mem0 等也插拔 | 用户修正 |
| 12 | 【前端 = 增强 IPython REPL】用户与 agent 等价 | 前端细化 |
| 13 | 【显示自举】agent 内部 hooks | 用户澄清 |
| 14 | 【自我修复 = 自我扩建】增量不覆盖,绕开 reload 冲突 | 用户深化(核心只读被否) |
| 15 | 【扩展点 patch】before/after/around,agent_loop patchable | 用户定 |
| 16 | 【可变区 = 人格插件】全局共享非单例,热插拔 | 用户定 |

---

## 关键决策与被否定的押注(试错记录)

1. **journal.py demo** → 否:"思路没厘清,demo 没意义"。**教训:形态押注必须在思路厘清后。**
2. **"服务造 skill 的工作流"范围** → 纠正:通用工具。
3. **基于 pi 扩展** → 转自搓。
4. **用 deepagents** → 否:HITL + sandbox 哲学冲突。
5. **远程 agent 回连本地** → 我过度复杂化,澄清就是 SSH 进去干活。
6. **"结束才备份"** → 否:崩溃来不及。改周期备份。
7. **"自然是远程 linux"** → 戳连锁代价,澄清要简单灵活。
8. **塞进 superharness 普通分支** → 否:不同项目。改独立仓库 prism。
9. **daemon 当命脉** → 修正:可插拔。
10. **mem0 写死核心** → 修正:可插拔。
11. **"聊天对话框 TUI"** → 否:要 IPython REPL。
12. **外壳写死显示调度** → 修正:显示自举(hooks)。
13. **核心区只读(base immutable)** → 否:**不够**。改为增量扩建 + 可变区容错(只 add 不 overwrite,绕开 reload 冲突)。
14. **"覆盖 + reload" 改核心** → 否:reload 不更新运行中对象。改为"增量 + 注册表",根本不 reload 已有。
15. **"自我修复 = 改自己代码"** → 修正:= **自我扩建**(只 add patch/tool/prompt 进注册表)。
16. **单例式可变区** → 否:全局共享但非单例(各自实例,改不影响别人)。

---

## 系统架构(最终形态)

**四层:前端 + 核心(patchable)+ 扩展点/注册表层 + 可变区/可插拔后端**

```
┌──────────────────────────────────────────────────────────┐
│  前端层 · 增强 IPython REPL(原则 8)                         │
│   @name 消息 路由 / 默认 Python / agent 流式输出            │
└──────────────────────────────────────────────────────────┘
            ▲ 共享命名空间
┌──────────────────────────────────────────────────────────┐
│  核心层(prism/, patchable 但不 overwrite —— 原则 10)        │
│   agent_loop: build_messages / stream_response /           │
│               execute_tools / should_stop / emit           │
│   ↑ 每个点查询 patch 注册表(原则 11)                        │
│   Agent / Kernel / Session / Guardrail / Frontend          │
└──────────────────────────────────────────────────────────┘
            ▲ 查询注册表(动态, 已有实例也看见新增)
┌──────────────────────────────────────────────────────────┐
│  注册表层(全局共享, 增量 add)                                │
│   tool_registry / prompt_registry / patch_registry         │
│   ↑ before/after/around patch 链                            │
└──────────────────────────────────────────────────────────┘
            ▲ 容错加载(坏了跳过)        ▲ 增量扩建(agent add)
┌──────────────────────────────────────────────────────────┐
│  可变区 · 人格插件(ext/, 原则 12) + 可插拔后端                │
│   ext/tools/ ext/prompts/ ext/patches/ ext/skills/         │
│   RuntimeBackend / MemoryBackend / DocStore / ModelBackend │
└──────────────────────────────────────────────────────────┘
```

---

## 工程设计(目录 / 类 / 扩展点协议 / 继承)

### 目录结构

```
prism/
├── PLAN.md
├── pyproject.toml
├── prism/                  # 核心区(patchable, 不被 overwrite)
│   ├── agent.py            # Agent
│   ├── agent_loop.py       # function-calling loop(patchable 扩展点)
│   ├── model.py            # ModelBackend + OpenAIModel
│   ├── router.py           # @ 路由
│   ├── shell.py            # IPython REPL 入口
│   ├── registry.py         # tool/prompt/patch 注册表(全局共享)
│   └── patch.py            # 扩展点协议(before/after/around)
├── ext/                    # 可变区 · 人格插件(agent 能任意改, 容错加载)
│   ├── tools/              # 动态工具脚本(.py) → tool_registry
│   ├── prompts/            # 补充 prompt 片段(.md) → prompt_registry
│   ├── patches/            # patch 脚本(.py) → patch_registry
│   └── skills/             # skill(工具+prompt 组合)
└── tests/
```

### 扩展点 patch 系统设计(原则 11, 阶段 3 实现)

**immutable base 边界**:`patch.py` + `agent_loop.py` 都属 base —— agent 不能 overwrite。patch 只能 **register 进 PatchRegistry**(扩展层), 不能改 patch 机制本身。

**PatchRegistry**(全局共享, 增量 add, 按 priority 排序):
```python
class PatchRegistry:
    def register(self, point, name, when, fn, priority=0):
        # when: "before" | "after" | "around"; 同 point+when 按 priority 升序(小先跑)
    def run_before(self, point, ctx) -> ctx:               # 顺序跑 before 链
    def run_after(self, point, ctx, result) -> result:     # 顺序跑 after 链
    def run_around(self, point, ctx, original_fn):         # 包裹链, 最内调 original_fn
```

**五个扩展点 + ctx/result 协议:**

| 扩展点 | ctx | before 可改 | after 可改 | around 可替换 |
|---|---|---|---|---|
| build_messages | messages, system_prompt, user_input | messages | messages | 构造逻辑 |
| stream_response | messages, tools | messages/tools | response | 流式逻辑 |
| execute_tools | tool_calls, tool_map | tool_calls(可拦) | results | 执行逻辑 |
| should_stop | message, tool_results, turn | 判断输入 | stop 布尔 | 判断逻辑 |
| emit | event | event | — | 输出逻辑 |

**around 异常降级**(关键, 跟可变区容错一致):任何 patch(before/after/around)抛异常 → **跳过该 patch + emit 警告, 不挂 base loop**。扩展层坏不拖垮 base, base loop 永远跑得下去。

**agent_loop 接入**(每扩展点: before → around(原逻辑) → after):
```python
ctx = {"messages":..., "system_prompt":..., "user_input":...}
ctx = patches.run_before("build_messages", ctx)
msgs = patches.run_around("build_messages", ctx, _build_messages)
msgs = patches.run_after("build_messages", ctx, msgs)
```

### 注册表(原则 12, 全局共享非单例)

```python
# prism/registry.py
class Registry:
    """全局共享的注册表池。每个 Agent 查询时各自实例化(非单例)。"""
    tools: list[Tool]          # ext/tools/ 加载 + agent add
    prompts: list[str]         # ext/prompts/ 加载 + agent add
    patches: PatchRegistry     # ext/patches/ 加载 + agent add

    def load_ext():            # 容错加载 ext/, 坏了跳过
        for f in glob("ext/tools/*.py"):
            try: tools.append(make_tool(f))
            except: emit(warn(f"{f} 加载失败, 跳过"))

# Agent 查询走注册表(动态, 非固化):
def _tools(self):
    return [_python_tool(self)] + registry.tools   # 已有实例也看见新增
```

### 继承关系树

```
前端层
└── Frontend (ABC) → ReplFrontend

可插拔后端(ABC)
├── RuntimeBackend → Local / Daemon
├── MemoryBackend  → Mem0 / File / Null
├── DocStore       → Markdown
└── ModelBackend   → OpenAI / Claude / Local

注册表/扩展点(全局共享)
├── Registry(tools/prompts/patches)
└── PatchRegistry(before/after/around per point)

核心类(patchable, 不 overwrite)
├── Agent
├── Kernel
├── Session → Interactive / Background
└── Guardrail
```

---

## prime-agent 翻译 / 借鉴记录(落盘)

**源**: `PrimeIntellect-ai/prime-agent`,`packages/agent/src/agent-loop.ts`(以及 `packages/coding-agent/src/core/` 的 session/runtime/rlm 层)。

**从 agent-loop.ts 借鉴并翻译成 prism 的:**

| prime-agent (TS) | prism (Python) | 备注 |
|---|---|---|
| function calling(`toolCall` blocks + `validateToolArguments`) | `agent_loop.run_agent_loop` 的 tool_calls | 扔文本 ReAct, 用结构化 |
| 双层 while(tool calls + steering/followup) | 单层(暂砍 steering/followup) | 后续补 |
| `streamAssistantResponse`(delta 事件) | `model.chat_stream` yield delta | 真流式 |
| `executeToolCalls`(sequential/parallel) | `execute_tool_calls`(仅 sequential) | parallel 后续 |
| `EventStream`(agent_start/turn/message/tool) | `emit` 结构化事件 dict | 事件流 |
| `AbortSignal` + `raceWithAbort` | `threading.Event` | abort |
| `transformContext`(compaction) | 砍 | 后续 |
| `getSteeringMessages`/`getFollowUpMessages` | 砍 | 后续 |

**prism 独有(超 prime-agent 的设计):**
- **python-in-namespace 工具**(agent 在 IPython 共享命名空间,能操作自己) — prime 的 persistent IPython 更偏工具调用,prism 把命名空间共享做到极致
- **hooks 自举显示**(原则 9)→ 泛化为 **扩展点 patch 系统**(原则 11),prime 的 supplemental state 只改 prompt/memory,prism 的 patch 能改 react 逻辑任意扩展点
- **输入即授权**(无 HITL)— prime 没明确,prism 死守
- **@ 路由**(原则 8 落地)— prime 用 pi 的 TUI,prism 用 IPython input transformer
- **增量扩建式自我修复**(原则 10)— prime 是 base immutable(静态禁止),prism 是增量 add(动态扩建)

**复刻踩的坑(落盘, 避免重蹈):**
1. **input_transformers_post 传 `list[str]` 不是 `str`** — FakeModel 测不出, 真跑才暴露
2. **tool_calls 缺 `type: "function"`** + **assistant content 空→`null`** → 第二轮 `BadRequestError`。openai 标准 tool_calls 格式必须对齐
3. **`run()` 返回值被 IPython 当 `Out[]` 重复显示** → 改返回 None, 显示靠 emit

**翻译原则**: 不是逐行翻 TS→Python(TS 的类型/async/EventStream 映射 Python 别扭),而是**借鉴设计、Python 惯用法重写**。

---

## 实现路线(交给 triage / plan)

**本地优先**。已完成阶段 0-部分,标注 ✓。

### ✓ 阶段 0 · 骨架 + 本地内核 + REPL + agent 内循环
- [x] 项目骨架、pyproject、.env 加载
- [x] `Kernel`+`LocalRuntime`(隐式: IPython start_ipython)
- [x] `ReplFrontend` + `@` 路由 input transformer
- [x] `Agent` + function-calling loop(`agent_loop.py`)
- [x] `ModelBackend` + `OpenAIModel`(chat_stream + tools)

### ✓ 阶段 0.5 · @ 路由 + bug 修复
- [x] `@name 消息` 路由(不群发/不裸写/空消息/不存在 全报错)
- [x] run() 返回 None(避免 Out[] 重复)
- [x] tool_calls 规范化 + content null(修 BadRequestError)

### 阶段 1 · 多 agent + 同进程通讯
- [ ] `Agent.spawn()` + 命名空间共享
- [ ] `Agent.send()` agent 间通讯
- [ ] **验收**: 主 agent spawn 子 agent, 结果回主 agent

### 阶段 2 · 流式显示 + 多长任务会话
- [ ] `message_delta` 流式注入 REPL(异步)
- [ ] `BackgroundSession`(threading)不阻塞主 REPL
- [ ] **验收**: `@a` 流式实时显示; 后台 agent 跑着主 REPL 继续敲

### 阶段 3 · 扩展点 patch 系统(原则 11)★新增
- [ ] `patch.py`: PatchRegistry + before/after/around 协议
- [ ] `agent_loop` 五个扩展点 patchable(build_messages/stream_response/execute_tools/should_stop/emit)
- [ ] **验收**: 加一个 around patch 包裹 execute_tools, 行为改变, 不改 agent_loop 本体

### 阶段 4 · 注册表 + 可变区(原则 12)★新增
- [ ] `registry.py`: tool/prompt/patch 注册表(全局共享)
- [ ] `ext/` 加载(容错降级, 坏了跳过)
- [ ] Agent 能力查询走注册表(动态, 非固化)→ 已有实例看见新增
- [ ] **验收**: 往 ext/tools/ 丢一个 .py, 已有 agent 实例下次 run 能用; ext/ 里丢个语法错的, agent 不挂(跳过+警告)

### 阶段 5 · 增量扩建式自我修复(原则 10)★新增
- [ ] agent 能 add patch/tool/prompt 进注册表
- [ ] 硬护栏拦 overwrite `prism/` 核心(只允许 add, 不允许 overwrite)
- [ ] **验收**: agent 给自己加一个 before patch 改 react 行为, 不改 agent_loop.py; 已有实例行为更新

### 阶段 6 · 输入即授权 + 硬护栏
- [ ] 移除二次确认
- [ ] Guardrail 精确化: 拦 overwrite prism/ + 删 agent 自身; 放行 add 注册表 + ext/
- [ ] **验收**: 试图 overwrite prism/agent_loop.py 被拦; add ext/patches/x.py 放行

### 阶段 7 · 持久化后端(可插拔)
- [ ] DocStore + MarkdownDocStore 周期 dump
- [ ] MemoryBackend(File → Mem0)
- [ ] **验收**: 强杀重启, agent 从 DocStore + Memory 恢复

### 阶段 8 · 后端可插拔验证 + daemon
- [ ] 切换各后端只换注入
- [ ] DaemonRuntime 远程 Linux
- [ ] **验收**: NullMemory 也能跑; 本地/远程都跑

### 阶段 9 · 跨会话传递验证
- [ ] 复现原始痛点, 各组合验收

---

## 开放问题 / 风险

1. **多 agent 共享 MemoryBackend vs 各管各** — 先共享。
2. **结构性文档格式** — 从糙开始演化。
3. **异步 + 同进程 + GIL** — 阶段 2 spike。
4. **硬护栏"工作目录根"边界** — 精确划定。
5. **无 daemon 恢复开销** — 阶段 7 验证。
6. **NullMemory 传递退化** — 阶段 8 验证。
7. **`@agent` 语法边界** — 名字冲突/多行, 阶段 0 已定单行。
8. **流式 vs 阻塞 REPL** — 阶段 2 spike prompt-toolkit 异步注入。
9. **扩展点 patch 的 around 语义** — around 能完全替换原逻辑,若 patch 抛异常怎么办?回滚?降级?**阶段 3 spike**。
10. **增量 vs 覆盖的边界** — ext/ 内"改一个 patch 文件"对该 patch 是覆盖,对核心是增量。约束要在文件系统层(核心 prism/ 不可 overwrite)+ 注册表层(改 ext/ 项 = 注册表更新,已有实例下次查询拿新版)明确。**阶段 4/5 定**。
11. **patch 注册表的并发** — 多 agent 同时 add patch,注册表要线程安全。**阶段 4**。
12. **跟 pi 的关系** — prism 完全自搓,与本地 pi 并行。

---

## Werden 流程元数据

- 种子轮次:用户抛"ipython 跨会话 agent 交互"
- 诘问轮数:16+ 轮
- 关键转折:用户否 demo(形态押注必须在思路厘清后)
- 项目身份演化:superharness 普通分支 → 独立仓库 prism
- 命名:prism(棱镜分光;被 prime 启发,致敬 pi 简洁)
- 设计修正链:① daemon 可插拔 ② mem0 可插拔 → 后端全可插拔 ③ 前端=增强 IPython REPL ④ 显示自举 ⑤ **核心只读→增量扩建(绕开 reload 冲突)** ⑥ **扩展点 patch(before/after/around)** ⑦ **可变区=人格插件(全局共享非单例)**
- prime-agent 翻译:agent-loop.ts → agent_loop.py(function calling + 事件流 + 流式),记录见专章
- 产出:本计划文档(交 triage / plan 执行)
