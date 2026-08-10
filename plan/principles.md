# 设计哲学 / 核心原则

> 这些是 prism **已落地或正落地**的设计铁律。RLM 认知层带来的**修正方向**(未实现)见文末。

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

### 原则 10 · base 可写 + 自动回退 + /revert(agent 自我演进, 安全网)

**演进**(从 immutable → 可变+回退; werden 讨论的原始设计): 主 agent **能改 prism/ 实现**(自我演进)。安全网: ① 改前自动备份(`.prism/backups/`) ② 运行失败(reload/import/sanity 错)自动回退 ③ `/revert` **第一公民指令**(base, 不在 ext/)手动回退。扩展层(ext/)仍增量 add(原则 12)。base 可写但有回退护栏 —— agent 进化自身, 失败可逆。

> 早期 immutable guard(拦写 prism/)退役 → 改为「备份 + 放行 + 回退」。
>
> ⚠️ **【RLM 修正方向, 未实现】** 9 轮 werden 推翻此条: core 将回归**硬不可变**(不允许改 core loop / Forest 契约 / ABC)。理由:不可变 core 是"直觉不可绕过"的物理实现 —— core 可变,agent 就能拆掉直觉那步。自我演进不需要改 core,走 patch/ext/认知树即可。详见 [rlm/core.md](rlm/core.md) §原则 10 修正。本条为**当前已实现状态**(`guard.py` 的备份+回退),与 RLM 方向并存,待路线推进时切换。

### 原则 11 · 扩展点 patch(before/after/around)
agent_loop 五点 patchable(build_messages / stream_response / execute_tools / should_stop / emit)。每点支持 before/after/around。patch 注册进 PatchRegistry,不改 base。

### 原则 12 · 可变区 = 人格插件(ext/ 四类: tools/prompts/patches/skills)
`ext/` 是 agent 人格插件 —— **tools/prompts/patches/skills 四类共同构成 agent 人格**(不是专门一个叫'人格'的东西)。全局共享(注册表池),每 agent 各自实例(非单例),热插拔,容错降级。agent 配置(prompt 段/tools/patches/skills)由这四类外部管理,不硬编码在 prism/ base(原则 10)。

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

## RLM 修正方向(认知层提案, 未实现)

9 轮 werden 逼出的修正与新增,详见 [rlm/](rlm/):

| 条目 | 方向 | 详见 |
|------|------|------|
| **原则 10 → 硬不可变 core** | core(loop+Forest 契约+ABC)不允许改;自我演进走 patch/ext/认知树 | [rlm/core.md](rlm/core.md) |
| **原则 8 边界** | agent 在命名空间无所不能,但 core 黑盒不可达(够不到 loop/model backend)→ 保证直觉不可绕过 | [rlm/core.md](rlm/core.md) |
| **新:认知自举(第 4 套自举)** | 与 hooks.emit(显示自举)/memory(状态自举)/patch(行为自举)同构的第 4 套 —— CognitiveHook | [rlm/core.md](rlm/core.md) |
| **新:认知树 = loop 同级基础设施** | Forest 契约进 core(不可变),树实例是可变 data | [rlm/tree.md](rlm/tree.md) |
| **loop 升级:线性 → 搜索循环** | agent_loop 从 function-calling 线性循环重写为 explore/evaluate/backtrack 搜索循环 | [rlm/cycle.md](rlm/cycle.md) |
