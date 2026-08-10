# 系统架构 + 工程设计

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

> ⚠️ RLM 方向:base 层将引入 **Forest(认知树契约)+ 搜索循环 loop**,agent_loop 从线性 → 搜索循环。详见 [rlm/](rlm/)。

---

## 工程设计

### 目录结构(当前)

```
prism/
├── plan/                  # ★结构化设计文档(本目录)
├── pyproject.toml
├── prism/                 # base(当前: 可写+回退; RLM方向: core 硬不可变)
│   ├── agent.py           # Agent(主/子共用骨架)
│   ├── agent_loop.py      # function-calling loop(patchable, 抄 prime)
│   ├── model.py           # ModelBackend + OpenAIModel(sync+async)
│   ├── router.py          # @ 路由
│   ├── shell.py           # textual TUI 套壳入口
│   ├── patch.py           # PatchRegistry(before/after/around)
│   ├── registry.py        # tool/prompt/skill 注册表
│   ├── memory.py          # MemoryBackend + FileMemory(原则 6/7)
│   ├── prompt.py          # SystemPrompt 结构化(阶段 13)
│   ├── guard.py           # 护栏(当前: 备份+回退; RLM方向: 拦写 core)
│   ├── commands.py        # slash 指令加载
│   └── agent_registry.py  # agent 注册表
├── ext/                   # 可变区 · 人格插件
│   ├── tools/ prompts/ patches/ skills/
│   └── commands/          # slash 指令
├── workspaces/            # 子 agent 独占工作区(spawn 时分配) ★多agent
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

### 扩展点 patch(原则 11)
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
