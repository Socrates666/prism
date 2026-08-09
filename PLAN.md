# prism

> 名字: 棱镜把一束光分成多束 —— 这个工具的核心机制:**一个 IPython 内核,分出多个 agent / 多个长任务会话**。被 PrimeAgent 启发,致敬 pi 的简洁。

---

## 一句话形态

prism 是一个在**项目根启动**、**主 agent 享完整 IPython(共享命名空间,用户等价)、子 agent 由工厂生产(受限、固定工作区、赋予工具)**、靠 **actor(每 agent 线程 + inbox + inject)** 并发、靠**扩展点 patch + 可变区人格插件**实现增量扩建、**前端 textual 全屏 TUI 套壳**、追求**无中断日常交互**的简单 agent 工具。

---

## 种子(用户原话)

> "使用 ipython 实现跨会话的 agent 交互可不可行"
> "我想用 primeagent 的那种 agent 调用方式,会话间的信息传递很低效,想探索一种方案"

---

## 设计哲学 / 核心原则

### 原则 1 · 输入即授权(零揣测)
用户输入就是命令,agent 不二次确认。agent 是用户延伸的手。

### 原则 2 · 硬护栏只护 agent 自身运作
护栏判据:会不会破坏 agent 自身运作。客观、硬编码、不靠 LLM 揣测。精确化(原则 10):不允许 overwrite 核心,允许增量扩建 + 可变区。

### 原则 3 · 跨会话状态是 agent 的器官
受硬护栏保护,持久化第一公民。

### 原则 4 · 灵活靠 IPython 运行时白送
agent 是命名空间活对象,加能力 = REPL 写代码注册。

### 原则 5 · 无中断交互(北极星)
不被提问打断 / 不被状态管理打断 / 不被长任务阻塞。

### 原则 6 · 持久化是核心地基
周期备份 + 记忆后端 + 文档后端。

### 原则 7 · 后端全可插拔(依赖接口)
RuntimeBackend / MemoryBackend / DocStore / ModelBackend 全可换。

### 原则 8 · 共享命名空间(用户与主 agent 等价)
**主 agent** 跟用户共享 IPython 命名空间,平等。输入既是代码也是对话。(注:子 agent 不共享完整命名空间,见原则 13)

### 原则 9 · 显示自举(agent 内部 hooks)
显示方法是 agent 运行时创造的。外壳提供 hooks,agent 改 hooks 创造显示。

### 原则 10 · 默认 agent 实现 immutable + 扩展层隔离
默认 agent 实现(抄 prime-agent 的 `agent_loop.py`)= immutable base,永不 overwrite。扩展层(patch/tool/skill)增量 add,跟 base 物理隔离(`ext/` vs `prism/`)。绕开 reload-vs-实例 冲突。

### 原则 11 · 扩展点 patch(before/after/around)
agent_loop 五点 patchable(build_messages / stream_response / execute_tools / should_stop / emit)。每点支持 before/after/around。patch 注册进 PatchRegistry,不改 base。

### 原则 12 · 可变区 = 人格插件(全局共享非单例,热插拔)
`ext/` 是 agent 人格插件:定义全局共享(注册表池),每 agent 各自实例(非单例),热插拔,容错降级。

### 原则 13 · 能力分层(主 agent 完整 / 子 agent 工厂受限)★多agent
- **主 agent**:享**完整 IPython 工具**(python 工具 = exec 任意代码),工作区=根(cwd),共享命名空间,跟用户等价。是用户的一等公民延伸,能 spawn 子 agent。
- **子 agent**:工厂函数(`spawn()`)生产,**不享完整 IPython(无裸 exec 的 python 工具)**。工具是工厂**赋予的固定集合**:文件工具(绑 workspace)+ 搜索/注册表 tool·skill **按情况赋予**。子 agent 是受限"工具化工人"。
- 主 agent 有完整能力(用户负责);子 agent 受限(可控、隔离)。

### 原则 14 · 工作区分层 + 文件工具闭包绑定★多agent
- prism **只能在项目根启动**(不全局)。
- 主 agent 工作区 = 项目根(用进程 cwd)。
- 子 agent 工作区 = `workspaces/<name>/`(独占、不重复,spawn 分配)。
- **文件工具闭包绑定 workspace**:`make_file_tools(ws)` 生成 read/write/ls,闭包绑死 ws,不依赖进程 cwd → 绕开 cwd 进程级问题 + 防踩踏。
- 子 agent 无裸 exec → 文件操作只走工具 → 天然落 workspace。

### 原则 15 · 多 agent 并发 = actor(每 agent 线程 + inbox + inject)★多agent
- 每 agent 一个独立线程,跑自己的循环(等 inbox → 处理)。
- exec(主 agent 的)/工具执行 在 agent 自己线程,不阻塞别的 agent。
- 通讯:`inject(msg)` 往 agent 的 inbox 递条子(跨线程 queue,立即返回不等)。
- 跟 textual(asyncio)桥接:agent 线程 emit → 跨线程到 TUI;TUI 输入 → inject inbox。

### 原则 16 · 通讯分层(读 eventual / 写 inbox)★多agent
- **读** agent 状态(属性:`b.history`/`b.last_result`):直接访问,原子(GIL),可能旧值(eventual consistency)。
- **写/触发** agent 行动:`b.inject(msg)`,B 自己线程处理,无 race(只有 B 改自己状态)。
- 不直接调 agent 的写方法(避免 race)。

---

## 被照亮的维度(按诘问出现顺序)

| # | 维度 | 来源 |
|---|------|------|
| 1-13 | (调用范式/路线/输入授权/护栏/状态器官/daemon/灵活/持久化/无中断/daemon可插拔/后端可插拔/前端REPL/显示自举) | 前期诘问 |
| 14 | 【自我修复=扩建】增量不覆盖 | 用户深化 |
| 15 | 【扩展点 patch】before/after/around | 用户定 |
| 16 | 【可变区=人格插件】全局共享非单例 | 用户定 |
| 17 | 【主/子能力分层】主完整IPython / 子工厂受限无裸exec | 多agent诘问 |
| 18 | 【工作区分层】主=根cwd / 子=workspaces独占 + 文件工具闭包 | 用户定 |
| 19 | 【actor 并发】每agent线程+inbox+inject,绕开asyncio exec阻塞 | 多agent诘问 |
| 20 | 【通讯分层】读eventual直接访问 / 写inbox触发 | 用户定 |

---

## 关键决策与被否定的押注(试错记录)

1-12. (前期:demo否/范围/路线/deepagents/远程/备份/分支/daemon/mem0/TUI/显示 — 见前版)
13. 核心只读 → 否:增量扩建(绕开 reload 冲突)
14. 覆盖+reload → 否:增量+注册表
15. 自我修复=改代码 → 修正:=扩建
16. 单例可变区 → 否:全局共享非单例
17. **exec to_thread(推共享池)** → 否:exec 跟 agent 循环一体
18. **await b.chat(直接对象调用)** → 否:进入对方执行;改为 inject 消息(递条子)
19. **共享命名空间 + 各自工作区 cwd** → 矛盾(cwd 进程级);改为**工作区分层 + 文件工具闭包**(绕开 cwd)
20. **子 agent 享完整 IPython** → 否:子 agent 工厂受限(无裸 exec),只有赋予的工具 → 隔离/安全

---

## 系统架构

```
┌─ textual TUI 套壳(全屏, asyncio) ──────────────────────┐
│  输入面板  @ 路由 / Python exec(主agent) / inject(子agent)│
│  输出面板  agent emit 事件 → 单 transcript(主视图, 取消分屏)  │
│  状态面板  agent 列表 / 后台 / 命名空间变量               │
└─────────────────────────────────────────────────────────┘
        ▲ emit(跨线程)               ▼ inject / 输入
┌─ agent 层(actor, 每 agent 一线程) ──────────────────────┐
│  主 agent [线程]                                         │
│    完整 IPython(python 工具=exec) / 共享 ns / cwd=根    │
│    能调 spawn()                                          │
│  子 agent alice [线程]    子 agent bob [线程]            │
│    无裸 exec              无裸 exec                      │
│    workspace=workspaces/  workspace=workspaces/          │
│            alice/                 bob/  (独占)           │
│    工具=工厂赋予(文件闭包+搜索+skill, 按情况)            │
│    inbox ← inject(主/用户/别的子agent 递条子)            │
└──────────────────────────────────────────────────────────┘
        ▲ 通讯: 读 eventual(属性) / 写 inbox(inject)
┌─ 扩展层(增量, 隔离 base) ────────────────────────────────┐
│  PatchRegistry(before/after/around) / tool_registry      │
│  ext/(人格插件: tools/prompts/patches/skills)            │
└──────────────────────────────────────────────────────────┘
┌─ immutable base(prism/, 不 overwrite) ──────────────────┐
│  agent_loop.py(抄 prime-agent) / agent.py / model.py    │
│  patch.py / registry.py / router.py / spawn.py          │
└──────────────────────────────────────────────────────────┘
```

---

## 工程设计

### 目录结构

```
prism/
├── PLAN.md
├── pyproject.toml
├── prism/                   # immutable base
│   ├── agent.py             # Agent(主/子共用骨架)
│   ├── agent_loop.py        # function-calling loop(patchable, 抄 prime)
│   ├── model.py             # ModelBackend + OpenAIModel(sync+async)
│   ├── router.py            # @ 路由
│   ├── shell.py             # textual TUI 套壳入口
│   ├── patch.py             # PatchRegistry(before/after/around)
│   ├── registry.py          # tool/prompt/skill 注册表
│   ├── spawn.py             # 子 agent 工厂 + make_file_tools ★多agent
│   └── actor.py             # inbox + inject + 线程循环 ★多agent
├── ext/                     # 可变区 · 人格插件
│   ├── tools/ prompts/ patches/ skills/
├── workspaces/              # 子 agent 独占工作区(spawn 时分配) ★多agent
│   ├── alice/  bob/  ...
└── tests/
```

### 多 agent 核心(原则 13-16)

**子 agent 工厂 + 文件工具闭包**(原则 13/14):
```python
# prism/spawn.py
def make_file_tools(ws: Path) -> list[Tool]:
    """闭包绑定 ws, 不碰进程 cwd → 防踩踏。"""
    def _resolve(p): 
        p = Path(p); return p if p.is_absolute() else ws / p
    def read(path): return _resolve(path).read_text(encoding="utf-8")
    def write(path, content):
        _resolve(path).parent.mkdir(parents=True, exist_ok=True)
        _resolve(path).write_text(content, encoding="utf-8"); return f"wrote {path}"
    def ls(path="."):
        d=_resolve(path); return str(sorted(p.name for p in d.iterdir())) if d.is_dir() else "not dir"
    return [Tool("read",...), Tool("write",...), Tool("ls",...)]

def spawn(name, model, *, file_tools=True, search=False, tools=None, skills=None):
    ws = Path(f"workspaces/{name}")
    if ws.exists(): raise ValueError(f"'{name}' 工作区已存在(不重复)")
    ws.mkdir(parents=True)
    granted = []
    if file_tools: granted += make_file_tools(ws)      # 闭包绑 ws
    if search:     granted += [search_tool]
    granted += tools or []
    granted += load_skills(skills or [])               # 注册表/ext 按名赋予
    # 不给 python(exec)工具 —— 子 agent 不裸 exec
    return Agent(name, model, workspace=ws, tools=granted, kind="sub")
```

**actor(inbox + inject + 线程)**(原则 15/16):
```python
# prism/actor.py
class Agent:
    def __init__(..., kind="main"):
        self.kind = kind                 # main(完整IPython) / sub(受限)
        self.inbox = queue.Queue()       # 收件箱(线程安全)
        self._thread = Thread(target=self._loop, daemon=True); self._thread.start()

    def inject(self, msg):               # 公开: 递条子(主/用户/别的子agent 调)
        self.inbox.put(msg)              # 立即返回, 不等处理

    def _loop(self):                     # 自己线程
        while True:
            msg = self.inbox.get()       # 等条子
            self._handle(msg)            # 处理(exec/工具/LLM, 在自己线程)

    # 通讯:
    #   读 agent 状态 → 直接访问 b.history / b.last_result (eventual)
    #   触发 agent 行动 → b.inject(msg) (B 自己线程处理, 无 race)
```

### 扩展点 patch(原则 11, 见前版)
PatchRegistry + 五扩展点 before/after/around + around 异常降级。

### 继承关系
```
Agent(kind="main")  完整 IPython(python 工具) + 共享 ns + cwd=根
Agent(kind="sub")   工厂生产, 无裸 exec, workspace=workspaces/<name>/ + 赋予工具
Frontend(ABC) → TextualTui(全屏套壳)
后端(ABC): Runtime/Memory/DocStore/Model
注册表: Registry(tools/prompts/skills) + PatchRegistry
```

### Theme / 配色落点(原则 9 + 10 + 12)

**当前唯一硬编码点**: `prism/shell.py` 顶部 `CSS` 常量(transcript 边框 `$accent` / dock 边框 `$primary` + `:focus $accent`)。`$accent`/`$primary` 是 textual 设计 token, 跟 textual 内置主题绑定。textual 本身支持运行时切主题(`self.theme="nord"` 立即生效, 所有 `$accent` 变量跟着变), 但 prism 还没接它。

**Gap(2026-08-09 发现)**: 按"显示自举"(原则 9)+ 主 agent 完整 IPython(原则 13), agent 应能运行时改主题。但当前 TUI 模式 `Agent(namespace=_user_ns())` 时 `get_ipython()` 返回 None → namespace 只有 `{"main": agent}`; `on_mount` 里 `app=self` 是局部变量(只供 emit 闭包用), **没进 namespace** → agent 的 python 工具 exec `app.theme=...` 会 NameError。app 句柄没暴露, 主题自举这条路是断的。

**补法(按糙→正)**:
1. 糙版: `on_mount` 加 `self.agent.namespace["app"] = self`, dock 里 `app.theme="nord"` 立刻能切。符合原则 13(主 agent = 用户等价, 用户本就能 Ctrl+C 改 CSS)。
2. 干净版: 包 `ThemeCtl`(只暴露 set/register, 不暴露整个 app) 进 namespace。
3. 架构正: 配色走 **ext/ 可变区**(原则 12)+ textual `register_theme`, CSS 全用 `$accent` 这类变量, 切主题零改 CSS、不碰 prism/ 核心(原则 10 immutable)。

**注意**: theme 是 textual App 层状态(`self.theme`/CSS), 不是 agent `hooks["emit"]`(原则 9 hooks 只管事件渲染)能管的。改主题需要 App 句柄, 跟"显示自举"的 hooks 是两条路。

---

## prime-agent 翻译 / 借鉴记录

**源**: `PrimeIntellect-ai/prime-agent` `packages/agent/src/agent-loop.ts`

**借鉴 → prism**: function calling / 双层 while / streamResponse(delta) / executeToolCalls / EventStream / AbortSignal → `agent_loop.py`(function-calling + 事件流 + 流式)。砍 compaction/steering/parallel(后续)。

**textual TUI 抄 pi**(packages/tui): 全屏 alternate-screen + transcript(滚动对话区) + dock(底部输入) 布局(fullscreen.ts)。textual 抄: `App`+`RichLog`(transcript)+`Input`(dock); 组件 Box→Container / Input→Input / Markdown→Markdown。~~多 agent 输出分屏~~ **已取消(用户定)**: 只用单 transcript, 子 agent 输出汇入主视图(带 [name] 前缀), 不开多面板。

**prism 独有(超 prime)**:
- 主 agent 完整 IPython + 共享命名空间(prime 子 agent 独立 session,不共享)
- **子 agent 工厂受限**(prime 子 agent 也是完整 session,prism 子 agent 无裸 exec + 工厂赋予工具)
- 扩展点 patch(改 react 逻辑,prime 的 supplemental 只改 prompt/memory)
- 工作区分层 + 文件工具闭包(prime 靠独立 sessionDir)
- 输入即授权 / @ 路由 / 增量扩建

**关键差异**: prime 子 agent = 独立 session(隔离,无 race,放弃共享);prism 子 agent = 工厂受限(共享命名空间魅力留给主 agent + 用户,子 agent 受控隔离)。prism 的"共享命名空间"是 prime 放弃的路。

**复刻踩坑**: input_transformers_post 传 list / tool_calls 缺 type / run() Out[] 重复。

---

## 实现路线

### ✓ 阶段 0 · 骨架 + 本地内核 + REPL + function-calling loop
- [x] agent_loop.py(function calling + 事件流)/ model.py(chat_stream)/ @ 路由 / .env

### ✓ 阶段 1 · 对齐 pi agent 基线(语义 + prompt, 用户定)★

**详见 [docs/alignment-pi.md](docs/alignment-pi.md)** —— 对齐审计(偏离项 + 增量映射)。

**语言鸿沟**: pi = TS SDK, prism = Python(IPython 核心)。“严格对齐” = 语义/行为/prompt 对齐, 非 SDK 复用。prism 是 pi agent 的 Python 增量实现。

**偏离修正(全部完成, test_alignment 验收)**:
- [x] D1 事件命名对齐 pi(message_update·delta / message_start / tool_execution_start/end)
- [x] D2 state 命名对齐(history→messages; 补 streaming_message/error_message)
- [x] D3 system prompt override/append 机制(_resolve_system_prompt / append_to_system_prompt)
- [x] D4 inject 区分 steer/followUp(PriorityQueue 优先级) + 显式 subscribe
- [x] D5 retry(auto_retry 事件) + thinking_level + compact()

**增量(建在 pi 基础上, 已审计)**: 多agent actor / patch五点 / workspace闭包 / guard护栏 / @路由+IPython / ext容错 / 能力分层 —— 详见 alignment-pi.md §3

**验收**: D1-D5 全对齐, 71 测试绿; 增量映射清晰

### ✓ 阶段 2 · textual TUI 套壳(原则 8 升级)
- [x] textual 全屏 TUI(transcript + dock, 抄 pi)
- [x] @ 路由挪进 TUI 输入(单行 @name → inject)
- [x] transcript can_focus=False(点击不抢 Input 焦点)
- [ ] **遗留**: theme 口子——namespace 未暴露 app 句柄, agent 够不到 self.theme(见 Theme 节)
- [ ] **已取消**: 多 agent 输出分屏(用户定, 改单 transcript 汇入)
- [x] **验收**: TUI 跑, @main 对话, 流式输出

### ✓ 阶段 3 · actor 异步(原则 15)
- [x] Agent 线程 + inbox + inject
- [x] agent emit 跨线程到 TUI(call_from_thread)
- [x] **验收**: 主 agent run 不冻 TUI; inject 递条子 agent 处理(跨 agent inject 待阶段 7)

### ✓ 阶段 4 · 扩展点 patch(原则 11)
- [x] patch.py(PatchRegistry before/after/around + 异常降级)
- [x] agent_loop 五点 patchable(build_messages/stream_response/execute_tools/should_stop/emit)
- [x] Agent 持有 patches; TUI 显示 patch_error 降级
- [x] **验收**: around patch 包裹 execute_tools 改行为,不改 base(patches 缺省 no-op)

### ✓ 阶段 5 · 注册表 + 可变区(原则 12)
- [x] registry.py(Registry tool/prompt/skill + load_ext 容错) + default_registry 全局共享池
- [x] Agent 加 registry 参数, _extra_tools += registry.tools()
- [x] **验收**: ext/tools 丢 .py 已有 agent 能用;坏的跳过+emit

### ✓ 阶段 6 · 多 agent 工厂 + 工作区(原则 13/14)★
- [x] spawn.py(spawn 工厂 + make_file_tools 闭包绑 ws)
- [x] workspaces/<name>/ 独占分配(已存在报错)
- [x] 子 agent kind=sub 无裸 exec,工厂赋予工具; spawn(parent=) 注册进父 namespace
- [x] **验收**: bob 文件操作落 workspaces/bob/,不踩主 agent

### ✓ 阶段 7 · 多 agent 通讯(原则 16)
- [x] inject 跨 agent(actor 阶段 3 已有); spawn(parent) 让主 agent 命名空间持子 agent
- [x] 读 eventual(直接属性访问 last_result/messages)
- [x] **验收**: 主 inject bob 干活 bob 处理; 主读 bob.last_result; inject 立即返回

### ✓ 阶段 8 · 增量扩建自我修复 + 护栏(原则 2/7/10)
- [x] guard.py: 包装主 agent exec 的 open, 写 prism/ 核心 → PermissionError
- [x] Agent.add_patch(point, fn, kind) / add_tool(tool): 运行时扩建正道
- [x] Agent.execute 用受限 builtins(open=guarded)
- [x] **验收**: add_patch 改 react 不改 agent_loop.py; 护栏拦 prism/ 放行别处

### ✓ 阶段 9 · 白盒 + 黑盒测试(用户定)
- [x] **白盒**: 单元测试覆盖率 67%→85%(补 router/model/patch 接入点)
- [x] **黑盒**: 端到端集成(test_e2e: main→spawn→inject→workspace) + TUI Pilot(test_tui: 结构/焦点/不崩)
- [x] **验收**: pytest 全绿; e2e 跑通 main→spawn→inject→workspace 全链路

### 阶段 10 · 持久化 + 后端可插拔 + daemon(原则 6/7)
- [ ] DocStore/MemoryBackend 周期 dump;后端切换;DaemonRuntime
- [ ] **验收**: 强杀重启恢复;NullMemory 能跑

### 阶段 11 · 跨会话传递验证
- [ ] 复现原始痛点验收

---

## 开放问题 / 风险

1-8. (前期:mem0共享/文档格式/异步GIL/护栏边界/恢复开销/NullMemory/@边界/流式阻塞)
9. around patch 异常降级(已定:跳过+警告)
10. 增量 vs 覆盖边界(核心 prism/ 不可 overwrite,ext/ 可改)
11. patch 注册表并发(线程安全)
12. **textual asyncio + agent 线程桥接**(emit 跨线程 call_from_thread)— 阶段 2 spike
13. **子 agent python 工具裸 open**(若未来赋予):落 cwd=根,踩踏。当前子 agent 无 python 工具,无此问题;若赋予,上 chdir 锁
14. **inbox 通讯 vs 共享变量**:通讯主走 inject(安全),共享变量辅助(eventual + 加锁)
15. **子 agent workspace 清理**:子 agent 结束后 workspaces/<name>/ 保留还是清理?待定
16. **theme namespace gap**:TUI 模式 namespace 没 app 句柄, agent 运行时改不了主题(见 Theme 节)。补法已定, 待实现

---

## Werden 流程元数据

- 种子:用户抛"ipython 跨会话 agent 交互"
- 诘问轮数:20+ 轮
- 项目:superharness 分支 → 独立仓库 prism
- 命名:prism(棱镜分光;被 prime 启发,致敬 pi)
- 设计修正链:daemon/mem0 可插拔 → 后端全可插拔 → 前端 IPython REPL → **textual TUI 套壳** → 显示自举 → 增量扩建 → 扩展点 patch → 可变区人格插件 → **能力分层(主完整/子工厂受限)** → **工作区分层+文件闭包** → **actor 并发** → **通讯分层(读eventual/写inbox)**
- prime-agent 翻译:agent-loop.ts → agent_loop.py,记录见专章
- 关键差异:prime 子 agent 独立 session(隔离);prism 主 agent 共享 ns + 子 agent 工厂受限
- 产出:本计划文档(交 triage / plan 执行)
