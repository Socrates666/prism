# prism

> 名字: 棱镜把一束光分成多束 —— 这个工具的核心机制:**一个 IPython 内核,分出多个 agent / 多个长任务会话**。被 PrimeAgent 启发,致敬 pi 的简洁。

---

## 一句话形态

prism 是一个跑在 **IPython 内核**里的、**多 agent 同进程通讯**的、**输入即授权零揣测**的、**硬护栏只护 agent 自身运作**的、靠可插拔后端解跨会话传递的、**IPython 运行时白送灵活**的、追求**无中断日常交互**的简单 agent 工具。

> **核心只依赖接口,实现全可插拔**:daemon 可拔(本地直跑)、mem0 可拔(换文件记忆或不用)、模型可换、文档后端可换。

---

## 种子(用户原话)

> "使用 ipython 实现跨会话的 agent 交互可不可行"
> "我想用 primeagent 的那种 agent 调用方式,然后在我的实践中也经常需要开多个会话来思考和推进同一个问题,会话间的信息传递很低效,想探索一种方案处理这个问题"

---

## 设计哲学 / 核心原则

这些原则**没有一个**是用户一开始说得清的,全是被诘问一巴掌一巴掌逼出来的。每条都值得在实现时死守。

### 原则 1 · 输入即授权(零揣测)
用户输入就是命令,agent 不回头质疑、不二次确认。zcode 烦就烦在"中断问蠢问题"——既问得频繁(中断阈值低),又问得蠢(该自己推断的不推断)。agent 的角色是**用户延伸的手**,不是替用户把关的大脑。

### 原则 2 · 硬护栏只护 agent 自身运作
护栏的判据不是"可逆性"、不是"破坏性"、不是"文件重不重要"——是**会不会破坏 agent 自身运作**。判据必须客观、可机械识别、硬编码,**不靠 LLM 揣测用户清不清醒**。护栏范围:agent 的可执行文件 / 配置 / 会话状态 / 记忆 / 运行环境 / 工作目录 / API 凭证。除此之外,用户输入一律执行,后果用户全担。

### 原则 3 · 跨会话状态是 agent 的器官
agent 的记忆 / 跨会话状态不是用户的数据附件,是 **agent 自身的一部分**。所以它受原则 2 的硬护栏保护(删它 = 破坏 agent 自身),并且是持久化的第一公民。

### 原则 4 · 灵活靠 IPython 运行时白送
agent 是 IPython 命名空间里的活对象。"加能力"= REPL 里写代码注册,立即生效。不用配置系统、不用重启、不用框架。这是跟 PrimeAgent 的 "persistent IPython + programmatic tool calling" 同一个思想。

### 原则 5 · 无中断交互(北极星)
三层都要覆盖:
- 不被**提问**打断 = 输入即授权(原则 1)
- 不被**状态管理**打断 = 周期性自动备份(原则 6)
- 不被**长任务**阻塞 = 一个内核开多个长任务会话,后台跑,主交互不卡

### 原则 6 · 持久化是核心地基(防崩溃 + 解传递)
- **周期性备份**:不等进程结束(崩溃来不及),每完成一步就落一次
- **记忆后端**:语义记忆,新 agent 能 retrieve(接口见原则 7)
- **文档后端**:信息有组织、可读、可交接(探索日志 / 决策记录 / 当前状态)

### 原则 7 · 后端全可插拔(依赖接口)
核心只依赖**后端接口**(`RuntimeBackend` / `MemoryBackend` / `DocStore` / `ModelBackend`),具体实现全可替换:
- **daemon 可拔** — `LocalRuntime`(进程会死,纯落盘恢复)/ `DaemonRuntime`(进程不死,免恢复)
- **mem0 可拔** — `Mem0Memory` / `FileMemory` / `NullMemory`(不用记忆)
- **模型可换** — `OpenAIModel` / `ClaudeModel` / `LocalModel`
- **文档可换** — `MarkdownDocStore` / 其他

这是**依赖倒置**:核心 `Agent` / `Kernel` 不绑死任何实现。棱镜的精神——核心是那个内核,一切外壳可插可拔。

---

## 被照亮的维度(按诘问出现顺序)

| # | 维度 | 来源 |
|---|------|------|
| 1 | 【调用范式】RLM / persistent IPython / subagent-as-function | 认知 PrimeAgent |
| 2 | 【路线】自搓(非用 pi 扩展,非用 deepagents) | 基底审视诘问 |
| 3 | 【舒服 = 输入即授权】zcode 烦在问蠢问题 | "pi 比 zcode 舒服"拆解 |
| 4 | 【护栏判据】破坏 agent 自身运作 + 硬编码 | force push / 删命根子处境逼出 |
| 5 | 【状态 = agent 器官】受硬护栏保护 | 推论焊点,用户确认 |
| 6 | 【daemon】Unix daemon,Windows 走不通 → 最初定远程 Linux | "daemon 是啥"澄清 |
| 7 | 【灵活 = IPython 运行时】 | "灵活机制"软词拆解 |
| 8 | 【持久化三件套】周期备份 + 记忆 + 文档 | "结束才备份"被否后补全 |
| 9 | 【无中断交互三层】 | 北极星词拆解 |
| 10 | 【daemon 可插拔】daemon 从命脉降为可选,落盘层升核心 | 用户修正 |
| 11 | 【后端全可插拔】mem0 等也插拔,提炼为依赖接口 | 用户修正(daemon+mem0 同源) |

---

## 关键决策与被否定的押注(试错记录)

> 这些"被否"和被纠正的过程,跟"被采纳"的同样重要——它们标出了**不要走**的路。

1. **journal.py demo(journal 落盘)** → 用户当场否:"思路没厘清,demo 没意义"。**教训:形态押注必须在思路厘清之后,不能倒过来。** demo 已撤销。
2. **"服务造 skill 的工作流"范围** → 用户纠正:是**通用工具**,不只造 skill。
3. **基于 pi 扩展** → 用户转向自搓("直接在 python 环境实现 agent,ipython 里启动")。
4. **用 deepagents** → 否。HITL(approve/reject tool calls)+ sandbox 哲学跟用户**根本性冲突**,要 reverse 它的默认值,性价比最低。
5. **远程 agent 回连本地 Windows 文件** → 我过度复杂化。用户澄清:就是 SSH 进 Linux 在那台机器干活,本地那套(pi/skill库/Hermes)跟这个工具无关。
6. **"结束才备份"** → 否。进程崩溃(OOM / SIGHUP / 断电 / kill -9)时根本跑不到退出钩子。改周期性备份。
7. **"自然是远程 linux"** → 我戳连锁代价。用户澄清:要的就是简单灵活日常工具,远程 Linux + SSH 是手段不是大工程。
8. **塞进 superharness 仓库的普通分支** → 用户否:不同项目不该用同一仓库普通分支(继承历史)。改为**独立仓库 prism**。
9. **daemon 当命脉** → 用户修正:daemon 可插拔,落盘层才是地基。
10. **mem0 写死在核心** → 用户修正:mem0 也可插拔。提炼为**后端全可插拔(依赖接口)**。

---

## 系统架构(最终形态)

**两层:核心层(只依赖接口) + 可插拔实现层**

```
┌──────────────────────────────────────────────────────────┐
│  核心层(prism 本质,不可插拔)                                │
│                                                           │
│   ┌─────────────────────────────────────────────┐        │
│   │  IPython 内核 (Kernel)                       │        │
│   │   命名空间(共享,灵活来源)                     │        │
│   │     ├── Agent A ──┐                          │        │
│   │     ├── Agent B ──┼─ 同进程对象间通讯         │        │
│   │     └── 子agent ──┘                          │        │
│   │   BackgroundSession(后台) ─┐                 │        │
│   │   InteractiveSession(前台) ─┘ 异步,不阻塞    │        │
│   └─────────────────────────────────────────────┘        │
│                                                           │
│   核心类: Agent / Kernel / Session / Guardrail            │
│   核心只持有【后端接口】,不持有具体实现                     │
│                                                           │
│   硬护栏 Guardrail(硬编码,只护 agent 自身运作)             │
└──────────────────────────────────────────────────────────┘
            ▲ 依赖接口(依赖倒置)        ▲ 周期性 dump 走 DocStore/MemoryBackend
┌──────────────────────────────────────────────────────────┐
│  可插拔实现层(全可替换)                                     │
│                                                           │
│   RuntimeBackend    → LocalRuntime / DaemonRuntime        │
│   MemoryBackend     → Mem0Memory / FileMemory / NullMemory│
│   DocStore          → MarkdownDocStore / ...              │
│   ModelBackend      → OpenAIModel / ClaudeModel / Local   │
└──────────────────────────────────────────────────────────┘
```

---

## 工程设计(目录 / 类 / 函数 / 继承)

### 目录结构

```
prism/
├── PLAN.md
├── README.md
├── pyproject.toml
├── prism/
│   ├── __init__.py
│   ├── core/                       # 核心(不可插拔,prism 本质)
│   │   ├── __init__.py
│   │   ├── agent.py                # Agent
│   │   ├── kernel.py               # Kernel(IPython 内核封装)
│   │   ├── session.py              # Session + Interactive/Background
│   │   └── guardrail.py            # Guardrail(硬护栏,硬编码)
│   ├── backends/                   # 可插拔后端(接口 + 实现)
│   │   ├── __init__.py
│   │   ├── runtime.py              # RuntimeBackend + Local/Daemon
│   │   ├── memory.py               # MemoryBackend + Mem0/File/Null
│   │   ├── docstore.py             # DocStore + MarkdownDocStore
│   │   └── model.py                # ModelBackend + 各 provider
│   ├── tools/
│   │   ├── __init__.py
│   │   └── builtin.py              # 内置工具(file/shell/...),函数式
│   └── cli.py                      # 入口: prism / prism daemon
└── tests/
    ├── test_agent.py
    ├── test_guardrail.py
    ├── test_backends.py
    └── ...
```

### 继承关系树

```
可插拔后端(ABC 接口,核心依赖它们,实现任意替换)
│
├── RuntimeBackend ─────── 控制内核进程生命周期
│   ├── LocalRuntime          本地直跑(进程会死,纯落盘恢复)
│   └── DaemonRuntime         daemon 常驻(进程不死,免恢复)
│
├── MemoryBackend ──────── 语义记忆 / 检索
│   ├── Mem0Memory            mem0 实现
│   ├── FileMemory            纯文件 / 简单检索
│   └── NullMemory            无记忆(可彻底拔掉)
│
├── DocStore ───────────── 结构性文档(可读、可交接)
│   └── MarkdownDocStore      markdown 落盘
│
└── ModelBackend ───────── LLM 接入
    ├── OpenAIModel
    ├── ClaudeModel
    └── LocalModel

核心类(不可插拔,prism 本质)
│
├── Agent ──────────────── agent 对象 + 内循环
│      (子 agent 是同 Agent 实例,配置不同,不分子类)
│
├── Kernel ─────────────── IPython 内核封装
│      (持有 RuntimeBackend —— 这是它唯一的可插拔依赖)
│
├── Session ────────────── 会话 / 长任务会话
│   ├── InteractiveSession     前台交互(阻塞主线程)
│   └── BackgroundSession      后台长任务(threading,不阻塞)
│
└── Guardrail ──────────── 硬护栏(硬编码,无继承)
       (PROTECTED 路径/操作写死,不靠 LLM)
```

### 核心类 · 函数签名

```python
# ── prism/core/agent.py ──────────────────────────
class Agent:
    def __init__(self, name: str, model: ModelBackend, *,
                 tools: list[callable] | None = None,
                 memory: MemoryBackend | None = None,
                 guardrail: Guardrail | None = None,
                 kernel: "Kernel" | None = None): ...

    def run(self, user_input: str) -> str:
        """主交互循环: 输入 → LLM → 工具 → 产出。输入即授权,不二次确认。"""

    def spawn(self, name: str, **overrides) -> "Agent":
        """spawn 子 agent。同进程,自动注册到 kernel 命名空间,可通讯。"""

    def send(self, target: "Agent", message) -> None:
        """agent 间通讯(同进程对象间调用)。"""

    def register_tool(self, func: callable) -> None:
        """加能力。IPython 运行时即时生效,不重启(灵活来源)。"""

    def recall(self, query: str, k: int = 5) -> list:
        """从 memory retrieve。memory 可拔(NullMemory 时返回空)。"""

    def _loop(self):
        """内循环: LLM 决策 → 调工具(过 Guardrail) → 回 LLM → 产出。"""


# ── prism/core/kernel.py ─────────────────────────
class Kernel:
    def __init__(self, runtime: RuntimeBackend): ...

    def start(self) -> None:
        """启动 IPython 内核(走 runtime,本地或 daemon)。"""

    def execute(self, code: str):
        """在命名空间执行任意代码 —— 灵活机制的来源(原则 4)。"""

    def register(self, name: str, obj) -> None:
        """注册对象(agent / 工具)到命名空间,供其他对象访问/通讯。"""

    def get(self, name: str): ...
    def list_agents(self) -> list["Agent"]: ...


# ── prism/core/session.py ────────────────────────
class Session:
    def __init__(self, agent: Agent, background: bool = False): ...
    def run(self, user_input): ...
    def is_alive(self) -> bool: ...
    def result(self):
        """取后台会话结果(BackgroundSession 用)。"""

class InteractiveSession(Session): ...   # 前台,阻塞
class BackgroundSession(Session): ...    # 后台,threading,不阻塞主交互


# ── prism/core/guardrail.py ──────────────────────
class Guardrail:
    # 硬编码:破坏 agent 自身运作的操作(原则 2)
    PROTECTED_PATHS = [
        "<prism 安装目录>",       # agent 可执行文件 / 配置
        "<state 目录>",           # 会话状态 / 记忆 / journal
        "<runtime / 依赖>",       # Python / 包
        "<工作目录根>",           # 删了 agent 失能(精确到根,非任意文件)
        "<API 凭证路径>",
    ]

    def check(self, operation) -> bool:
        """True=放行, False=拦截。机械识别,不调 LLM。"""

    def block_reason(self, operation) -> str | None:
        """被拦时返回原因(只护 agent 自身,不是保护用户)。"""
```

### 后端接口 · 函数签名

```python
# ── prism/backends/runtime.py ────────────────────
class RuntimeBackend(ABC):
    @abstractmethod
    def start_kernel(self) -> "Kernel": ...
    @abstractmethod
    def is_persistent(self) -> bool:
        """daemon=True(进程不死) / local=False(进程会死)。"""

class LocalRuntime(RuntimeBackend): ...     # 本地直接起 IPython
class DaemonRuntime(RuntimeBackend): ...    # tmux / systemd --user / nohup+setsid


# ── prism/backends/memory.py ────────────────────
class MemoryBackend(ABC):
    @abstractmethod
    def add(self, content, metadata: dict | None = None) -> str: ...
    @abstractmethod
    def search(self, query: str, k: int = 5) -> list: ...
    @abstractmethod
    def all(self) -> list: ...

class Mem0Memory(MemoryBackend): ...    # mem0 语义检索
class FileMemory(MemoryBackend): ...    # 纯文件 + 简单检索
class NullMemory(MemoryBackend): ...    # 无记忆(可彻底拔掉 mem0)


# ── prism/backends/docstore.py ──────────────────
class DocStore(ABC):
    @abstractmethod
    def append(self, doc_id: str, entry: str) -> None: ...
    @abstractmethod
    def read(self, doc_id: str) -> str: ...
    @abstractmethod
    def list_docs(self) -> list[str]: ...

class MarkdownDocStore(DocStore): ...   # .md 落盘,探索日志/决策记录/当前状态


# ── prism/backends/model.py ─────────────────────
class ModelBackend(ABC):
    @abstractmethod
    def chat(self, messages: list, tools: list | None = None) -> "Response": ...

class OpenAIModel(ModelBackend): ...
class ClaudeModel(ModelBackend): ...
class LocalModel(ModelBackend): ...     # vLLM / llama.cpp / ollama
```

### 模块职责一句话

| 模块 | 职责 |
|------|------|
| `core/agent.py` | agent 对象 + 内循环(LLM↔工具),spawn 子 agent,agent 间通讯 |
| `core/kernel.py` | IPython 内核封装,命名空间管理,代码执行(灵活来源) |
| `core/session.py` | 会话抽象,前台/后台(异步不阻塞) |
| `core/guardrail.py` | 硬护栏,硬编码保护 agent 自身运作 |
| `backends/*` | 四类可插拔后端的接口 + 实现 |
| `tools/builtin.py` | 内置工具(函数式,IPython 运行时注册) |
| `cli.py` | 入口:`prism`(本地)/ `prism daemon`(常驻) |

---

## 实现路线(交给 triage / plan)

**本地优先**——先把核心层在本地跑通,daemon / mem0 作为可插拔选项后期接。

### 阶段 0 · 骨架 + 本地内核 + agent 内循环
- [ ] 项目骨架(按目录结构)、`pyproject.toml`
- [ ] `Kernel` + `LocalRuntime`:本地起 IPython 内核
- [ ] `Agent` + `ModelBackend`(先接一个 provider)+ `run()` 内循环
- [ ] **验收**:本地 `prism` 起 agent,自然语言交互一轮

### 阶段 1 · 多 agent + 同进程通讯
- [ ] `Agent.spawn()` + `Kernel.register()` 命名空间共享
- [ ] `Agent.send()` agent 间通讯
- [ ] **验收**:主 agent spawn 子 agent 干活,结果回主 agent

### 阶段 2 · 多长任务会话(异步)
- [ ] `BackgroundSession`(threading)后台跑,不阻塞主交互
- [ ] (GIL 提醒:agent 主要 LLM IO,threading 可行)
- [ ] **验收**:开后台长任务,主交互继续输入立即响应

### 阶段 3 · 输入即授权 + 硬护栏
- [ ] 移除一切二次确认
- [ ] `Guardrail` 硬编码 `PROTECTED_PATHS`,工具调用前过 `check()`
- [ ] **验收**:任意指令直接执行;试图删 agent 自身任一项被拦

### 阶段 4 · 持久化后端(核心地基,可插拔)
- [ ] `DocStore` + `MarkdownDocStore`:周期性 dump 探索日志/决策/状态
- [ ] `MemoryBackend` + 先实现 `FileMemory`(糙),再接 `Mem0Memory`
- [ ] 周期性备份触发(每完成一步 / 每 N 秒)
- [ ] **验收**:强杀进程 → 重启 → agent 从 DocStore + MemoryBackend 恢复

### 阶段 5 · 后端可插拔验证
- [ ] 同一套核心,切换 `LocalRuntime`↔`DaemonRuntime`、`FileMemory`↔`Mem0Memory`↔`NullMemory`、不同 `ModelBackend`,只换构造注入,不动核心
- [ ] `DaemonRuntime`:远程 Linux daemon 常驻 + SSH detach/reattach
- [ ] **验收**:四种后端各自可独立替换;`NullMemory` 也能跑(证明 mem0 真的可拔)

### 阶段 6 · 跨会话传递验证(回检原始痛点)
- [ ] 复现原始痛点:开 agent A 探索 → spawn 子 B 验证 → 关进程 → 重开
- [ ] **验收**:有/无 daemon、有/无 mem0 各种组合,新会话都能拿到 A/B 的结论、卡点、下一步

---

## 开放问题 / 风险

1. **多 agent 共享 MemoryBackend vs 各管各的** — 共享一个 memory 库 vs 各有各的?**建议:先共享,简单。** 混乱再分。
2. **结构性文档(DocStore)的格式** — tree.md 式?决策记录式?**建议:从最糙开始(追加时间戳条目),用着演化。**
3. **异步 + 同进程的张力** — IPython 内核单线程消息处理,长任务靠线程。**建议:阶段 2 先 spike 验证 GIL 在 LLM IO 场景不踩坑。**
4. **硬护栏"工作目录根"的精确边界** — 工作目录算 agent 自身(删了失能),但用户正常工作也改工作目录文件。护栏要精确到"删整个根",不是"任意文件操作"。**实现时划定。**
5. **无 daemon 模式的恢复开销** — 纯落盘恢复,重启重建多少状态?延迟可接受吗?**建议:阶段 4 验证恢复速度,再决定 daemon 是不是日常必需。**
6. **NullMemory 时跨会话传递退化到什么程度** — mem0 拔掉后,只剩 DocStore(markdown)。这够不够"传递"?**建议:阶段 5/6 验证纯 DocStore 模式的传递质量。**
7. **跟 pi 的关系** — prism 完全自搓,与本地 pi 并行。用户本地那套(skill库/Hermes/Obsidian)与 prism 不通。已知并接受。

---

## Werden 流程元数据

- 种子轮次:用户抛"ipython 跨会话 agent 交互"
- 诘问轮数:11 轮
- 关键转折:用户否 demo(教训:形态押注必须在思路厘清后)
- 终止:用户明确"生成计划文档吧"
- 项目身份演化:superharness 普通分支 → 独立仓库 prism(不同项目不该同仓库普通分支)
- 命名:prism(棱镜分光 = 一内核分多会话/多agent;被 prime 启发,致敬 pi 简洁)
- 设计修正:① daemon 可插拔 ② mem0 可插拔 → 提炼为**后端全可插拔(依赖接口)**
- 工程下沉:第11轮,用户要求暴露目录结构/类/函数/继承树
- 产出:本计划文档(交 triage / plan 执行,非直接写代码)
