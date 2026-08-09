"""Agent — prism agent。function-calling loop(借鉴 prime-agent), hooks 自举显示。

设计要点(对应 PLAN 原则):
  - function calling(非文本 ReAct): LLM 返回结构化 tool_calls, 不解析文本
  - 事件流(显示自举基础): emit 结构化事件, hooks["emit"] 可替换
  - 流式: message_delta 边生成边出
  - abort: threading.Event, run() 可被打断
  - python 工具: 在共享命名空间执行(IPython 运行时灵活, 原则4)
  - 自修改: agent 注册进命名空间, 能被自己操作
"""
from __future__ import annotations
import threading
from typing import Any, Callable

from .agent_loop import run_agent_loop, Tool


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
    """默认显示: 流式文本 + 工具调用/结果。

    可被 agent.hooks["emit"] 替换(显示自举, 原则9)。
    替换后接收的是【事件 dict】, 不是 (source, chunk)。
    """
    t = event["type"]
    if t == "message_delta":
        print(event["text"], end="", flush=True)
    elif t == "message_end":
        if event["text"]:
            print()  # 文本后换行
    elif t == "tool_start":
        print(f"  → {event['name']}({event['args']})")
    elif t == "tool_end":
        mark = "✗" if event["is_error"] else "✓"
        res = str(event["result"])
        print(f"    {mark} {res[:300]}")


def _python_tool(agent: "Agent") -> Tool:
    """python 工具: 在 agent 共享命名空间执行代码。"""
    def execute(args):
        code = args.get("code", "")
        status, detail = agent.execute(code)
        out = f"[{status}] {detail}".strip()
        return out or "[ok]"
    return Tool(
        name="python",
        description=(
            "在共享命名空间执行 Python 代码。能创建变量、操作对象、"
            "甚至修改自己的 system_prompt(你自己在命名空间里, 变量名是你的 name)。"
            "返回执行状态。完成任务后不要再调用工具, 直接回答。"
        ),
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "要执行的 Python 代码"}},
            "required": ["code"],
        },
        execute=execute,
    )


class Agent:
    """prism agent。function-calling loop。

    用法:
        a = Agent("alice", model=OpenAIModel())
        a.run("算 2+2 存到变量 x")   # LLM 调 python 工具: x = 4
        x                              # 直接访问(共享命名空间)
        a.system_prompt = "..."        # 改 agent 自己
        a.hooks["emit"] = my_emit      # 改显示(事件 dict)
        a.stop()                       # 中止当前 run
    """

    def __init__(self, name: str, model, *, system_prompt: str = "",
                 namespace: dict | None = None, tools: list[Tool] | None = None,
                 max_turns: int = 20):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt or (
            f"你是 {name}, 一个跑在 IPython 内核里的 agent。"
            "用 python 工具执行代码(在共享命名空间创建变量/操作对象/改自己 system_prompt)。"
            "简洁直接。完成时不再调用工具, 直接回答。"
        )
        self.namespace = namespace if namespace is not None else _user_ns()
        self.namespace.setdefault(name, self)   # agent 注册进命名空间, 能被自己操作
        self.max_turns = max_turns
        self.last_result: str = ""
        self.history: list[dict] = []
        # hooks —— 显示自举(原则9): emit 接收事件 dict, 可替换
        self.hooks: dict[str, Callable] = {"emit": _default_emit}
        self.abort = threading.Event()
        self._extra_tools: list[Tool] = list(tools or [])

    def emit(self, event: dict) -> None:
        self.hooks["emit"](event)

    def execute(self, code: str) -> tuple[str, str]:
        """在共享命名空间执行 Python(python 工具的底层)。"""
        try:
            exec(compile(code, f"<{self.name}>", "exec"), self.namespace)
            return ("ok", "")
        except Exception as e:
            return ("error", f"{type(e).__name__}: {e}")

    def _tools(self) -> list[Tool]:
        return [_python_tool(self)] + self._extra_tools

    def run(self, user_input: str) -> None:
        """function-calling agent loop。返回 None(显示靠 emit), 结果在 last_result。"""
        self.abort.clear()
        self.emit({"type": "user_input", "text": user_input})
        msgs = run_agent_loop(
            self.model, self.system_prompt, user_input, self._tools(),
            self.emit, abort=self.abort, max_turns=self.max_turns, history=self.history,
        )
        # 取最后一条 assistant 文本作 last_result
        for m in reversed(msgs):
            if m.get("role") == "assistant" and m.get("content"):
                self.last_result = m["content"]
                break
        # 累积历史(去掉 system, 供下一轮多轮对话)
        self.history = [m for m in msgs if m.get("role") != "system"]

    def chat(self, message: str) -> None:
        """对话入口(run 的别名, @ 路由用)。"""
        self.run(message)

    def stop(self) -> None:
        """请求中止当前 run(异步, run 在别的线程时有效)。"""
        self.abort.set()
