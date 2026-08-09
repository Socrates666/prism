"""Agent — prism agent。function-calling loop + actor(线程+inbox+inject)。

设计(对应 PLAN 原则):
  - function calling(原则: 非文本ReAct): 委托 agent_loop.py
  - actor(原则15): 每 agent 一线程 + inbox + inject, 多 agent 并发, exec 不阻塞别的
  - 能力分层(原则13): kind="main" 有 python 工具(完整IPython); kind="sub" 无裸 exec(工厂受限)
  - 通讯分层(原则16): 读属性(eventual) / 写 inbox(inject)
  - hooks 自举显示(原则9): emit 事件 dict, 可替换
"""
from __future__ import annotations
import threading
import queue
from typing import Callable

from .agent_loop import run_agent_loop, Tool
from .patch import PatchRegistry


def _user_ns() -> dict:
    """获取 IPython 当前 shell 的 user_ns; 没有(不在 IPython 里)就空 dict。"""
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is not None:
            return shell.user_ns
    except Exception:
        pass
    return {}


def _default_emit(event: dict) -> None:
    """默认显示: 流式文本 + 工具调用/结果。可被 hooks["emit"] 替换(显示自举)。"""
    t = event["type"]
    if t == "message_delta":
        print(event["text"], end="", flush=True)
    elif t == "message_end":
        if event["text"]:
            print()
    elif t == "tool_start":
        print(f"  → {event['name']}({event['args']})")
    elif t == "tool_end":
        mark = "✗" if event["is_error"] else "✓"
        print(f"    {mark} {str(event['result'])[:300]}")


def _python_tool(agent: "Agent") -> Tool:
    """python 工具: 在共享命名空间执行代码(主 agent 才有)。"""
    def execute(args):
        code = args.get("code", "")
        status, detail = agent.execute(code)
        out = f"[{status}] {detail}".strip()
        return out or "[ok]"
    return Tool(
        name="python",
        description=("在共享命名空间执行 Python 代码。能创建变量、操作对象、"
                     "修改自己的 system_prompt(你在命名空间里, 变量名是你的 name)。"
                     "完成任务后不再调用工具, 直接回答。"),
        parameters={"type": "object",
                    "properties": {"code": {"type": "string", "description": "要执行的 Python 代码"}},
                    "required": ["code"]},
        execute=execute,
    )


class Agent:
    """prism agent。function-calling loop + actor。

    用法:
        a = Agent("alice", model=OpenAIModel())          # 主 agent(完整IPython)
        a.run("...")                                       # 同步(前台)
        a.inject({"type":"run","input":"..."})             # 异速(actor 线程, 跨agent并发)
        a.inject({"type":"msg","from":"bob","text":"..."}) # 别的 agent 递消息
        b.history                                          # 读 b 状态(eventual, 原则16)
    """

    def __init__(self, name: str, model, *, system_prompt: str = "",
                 namespace: dict | None = None, tools: list[Tool] | None = None,
                 max_turns: int = 20, kind: str = "main", actor: bool = True,
                 registry=None):
        self.name = name
        self.model = model
        self.kind = kind                  # "main"(完整IPython, 有python工具) / "sub"(工厂受限, 无裸exec)
        self.system_prompt = system_prompt or (
            f"你是 {name}, prism 里的 agent。"
            "prism 是一个 textual 全屏 TUI(agent harness), 你跑在它的 IPython 内核里(有图形界面, 不是纯命令行)。"
            "你有 python 工具: 在共享命名空间执行 Python 代码(创建变量/操作对象/调标准库/改自己 system_prompt)。"
            "用户通过 @ 消息跟你对话, 你也能看到用户直接敲的 Python。你的回复流式显示在 transcript。"
            "简洁、直接、准确。不确定就说不确定, 不要编造自己的能力或环境。完成时不再调用工具, 直接回答。"
        )
        self.namespace = namespace if namespace is not None else _user_ns()
        self.namespace.setdefault(name, self)   # agent 注册进命名空间, 能被自己/别的对象操作
        self.max_turns = max_turns
        self.last_result: str = ""
        self.history: list[dict] = []
        self.hooks: dict[str, Callable] = {"emit": _default_emit}
        self.patches = PatchRegistry(self.emit)   # 五扩展点 patch 注册表(原则 11)
        self.abort = threading.Event()
        self._extra_tools: list[Tool] = list(tools or [])
        if registry is not None:
            self._extra_tools += registry.tools()    # 全局共享池的 tool(原则 12)
        self.workspace = None             # 子 agent 由 spawn 设(原则14)
        # ── actor(原则15): inbox + 线程 ──
        self.inbox: queue.Queue | None = queue.Queue() if actor else None
        self._handlers: dict[str, Callable] = {"run": self._h_run, "msg": self._h_msg}
        if actor:
            self._thread = threading.Thread(target=self._actor_loop, daemon=True)
            self._thread.start()

    def emit(self, event: dict) -> None:
        self.hooks["emit"](event)

    def execute(self, code: str) -> tuple[str, str]:
        """在共享命名空间执行 Python(python 工具底层)。

        护栏(原则 2/10): open 写 prism/ 核心 → PermissionError; 其余正常。
        """
        try:
            from .guard import restricted_builtins
            glb = dict(self.namespace)
            glb.pop("__builtins__", None)
            glb["__builtins__"] = restricted_builtins()
            exec(compile(code, f"<{self.name}>", "exec"), glb)
            glb.pop("__builtins__", None)
            self.namespace.update(glb)   # 同步新建变量回共享 namespace
            return ("ok", "")
        except Exception as e:
            return ("error", f"{type(e).__name__}: {e}")

    def _tools(self) -> list[Tool]:
        # 原则13: 主 agent 有 python 工具(完整IPython); 子 agent 只有工厂赋予的(_extra_tools)
        if self.kind == "main":
            return [_python_tool(self)] + self._extra_tools
        return list(self._extra_tools)    # 子 agent 无裸 exec

    # ── 增量扩建自我修复(原则 7/10, 走注册表正道) ────────
    def add_patch(self, point: str, fn, *, kind: str = "around") -> None:
        """运行时注册 patch(增量扩建正道)。kind ∈ before/after/around。"""
        if kind not in ("before", "after", "around"):
            raise ValueError(f"kind 须 before/after/around, 不是 '{kind}'")
        getattr(self.patches, kind)(point, fn)

    def add_tool(self, tool) -> None:
        """运行时加 tool(增量扩建正道)。"""
        self._extra_tools.append(tool)

    def run(self, user_input: str) -> None:
        """同步 function-calling loop(前台)。返回 None, 显示靠 emit, 结果在 last_result。"""
        self.abort.clear()
        self.emit({"type": "user_input", "text": user_input})
        msgs = run_agent_loop(
            self.model, self.system_prompt, user_input, self._tools(),
            self.emit, abort=self.abort, max_turns=self.max_turns,
            history=self.history, patches=self.patches,
        )
        for m in reversed(msgs):
            if m.get("role") == "assistant" and m.get("content"):
                self.last_result = m["content"]
                break
        self.history = [m for m in msgs if m.get("role") != "system"]

    # ── actor(原则15/16) ──────────────────────────────
    def inject(self, msg: dict) -> None:
        """递条子(异步, 跨线程)。msg = {"type":"run"/"msg", ...}。立即返回, 不等处理。

        通讯分层(原则16): 触发 agent 行动用 inject(B 自己线程处理, 无 race)。
        """
        if self.inbox is not None:
            self.inbox.put(msg)

    def _actor_loop(self) -> None:
        """agent 自己的线程: 等 inbox → 处理(在自己线程, 不阻塞别的 agent)。"""
        while True:
            msg = self.inbox.get()
            h = self._handlers.get(msg.get("type"))
            if h:
                try:
                    h(msg)
                except Exception as e:
                    self.emit({"type": "error", "error": f"{type(e).__name__}: {e}"})

    def _h_run(self, msg: dict) -> None:
        self.run(msg.get("input", ""))

    def _h_msg(self, msg: dict) -> None:
        src = msg.get("from", "?")
        self.run(f"[来自 {src} 的消息] {msg.get('text', '')}")

    def chat(self, message: str) -> None:
        """对话入口(@ 路由用)。"""
        self.run(message)

    def stop(self) -> None:
        """请求中止当前 run。"""
        self.abort.set()
