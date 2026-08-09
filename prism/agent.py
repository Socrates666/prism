"""Agent — prism 的 agent. ReAct 循环, 跑在 IPython 内核命名空间里.

设计要点(对应 PLAN 原则):
  - 输入即授权(原则 1): run() 不二次确认
  - IPython 运行时灵活(原则 4): execute() 在共享命名空间跑任意代码
  - 显示自举(原则 9): hooks(emit/guard) 可被 agent 自己改 → 显示方法是活的
  - 自修改: system_prompt 运行时可变; agent 自己注册进命名空间, 能操作自己
"""
from __future__ import annotations
import re
from typing import Callable


REACT_INSTRUCTIONS = """\
你可以用 ReAct 方式工作。每一步严格按此格式输出:

Thought: <你的推理>
Action: <python | finish>
Action Input: <内容>

- Action: python  → Action Input 是要在共享命名空间执行的 Python 代码。
  你能在代码里创建变量、操作对象、甚至修改自己的 system_prompt
  (你自己在命名空间里, 变量名就是你的 name)。
  执行结果会作为 Observation 返回。
- Action: finish  → Action Input 是你的最终回答, 循环结束。

一次只输出一个 Action。"""


def _user_ns() -> dict:
    """获取 IPython 当前 shell 的 user_ns; 没有(不在 IPython 里)就返回空 dict。"""
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is not None:
            return shell.user_ns
    except Exception:
        pass
    return {}


def _parse_react(text: str) -> tuple[str, str]:
    """从 LLM 输出解析 Action / Action Input。解析失败默认 finish。"""
    action_m = re.search(r"Action:\s*(\S+)", text)
    input_m = re.search(r"Action\s*Input:\s*(.*)", text, re.S)
    action = action_m.group(1).strip().lower() if action_m else "finish"
    action_input = input_m.group(1).strip() if input_m else text.strip()
    return action, action_input


class Agent:
    """prism agent。

    用法:
        a = Agent("alice", model=OpenAIModel())
        a.run("把 2+2 算出来存到变量 x")   # agent 执行 python: x = 4
        x                                     # 直接访问(共享命名空间)
        a.system_prompt = "你只说海盗话"      # 改自己 prompt
    """

    def __init__(self, name: str, model, *,
                 system_prompt: str = "",
                 namespace: dict | None = None,
                 tools: dict[str, Callable] | None = None,
                 max_steps: int = 8):
        self.name = name
        self.model = model
        self.system_prompt = system_prompt or (
            f"你是 {name}, 一个跑在 IPython 内核里的 agent。"
            "你能执行 Python 代码(在共享命名空间创建变量、操作对象), "
            "也能修改自己的 system_prompt 来调整行为。简洁、直接。"
        )
        # 共享命名空间: 默认接 IPython 的 user_ns → 用户和 agent 等价(原则 8)
        self.namespace = namespace if namespace is not None else _user_ns()
        self.tools = tools or {}
        self.max_steps = max_steps
        self.history: list[dict] = []
        self.last_result: str = ""  # 最近一次 run 的最终结果(emit 已打印, 这里供程序化取用)
        # hooks —— 显示自举的核心(原则 9): agent 能改这些来重塑显示
        self.hooks: dict[str, Callable] = {
            "emit": lambda source, chunk: print(f"[{source} ▸] {chunk}"),
            "guard": lambda action, action_input: True,  # 默认放行(输入即授权)
        }
        # 把自己注册进命名空间 → agent 能在 python action 里操作自己(自修改)
        self.namespace.setdefault(name, self)

    # ── hooks(显示自举) ───────────────────────────
    def emit(self, chunk: str, source: str | None = None):
        self.hooks["emit"](source or self.name, chunk)

    # ── 核心行动: 在共享命名空间执行 Python ─────────
    def execute(self, code: str) -> tuple[str, str]:
        """agent 的核心能力。创建变量 / 操作对象 / 改自己 prompt 都靠它。"""
        try:
            exec(compile(code, f"<{self.name}>", "exec"), self.namespace)
            return ("ok", "")
        except Exception as e:
            return ("error", f"{type(e).__name__}: {e}")

    # ── ReAct 循环 ─────────────────────────────────
    def run(self, user_input: str) -> None:
        """主循环: 输入 → LLM(ReAct) → 行动(python/finish) → 观察 → ...

返回 None —— 显示全靠 emit hooks(原则9), 避免 IPython 把返回值当 Out[] 再打印一遍。
最终结果存 self.last_result。"""
        self.emit(f"← {user_input}", source="you")
        messages = (
            [{"role": "system",
              "content": self.system_prompt + "\n\n" + REACT_INSTRUCTIONS}]
            + self.history
            + [{"role": "user", "content": user_input}]
        )
        for step in range(self.max_steps):
            raw = self.model.chat(messages)
            action, action_input = _parse_react(raw)

            if action == "finish":
                self.emit(action_input)
                self.last_result = action_input
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": raw})
                return  # 不返回值 —— emit 已打印, 避免 IPython 的 Out[] 再显示一遍(显示靠 hooks, 原则9)

            # 行动前过 guard hook(默认放行 = 输入即授权)
            if not self.hooks["guard"](action, action_input):
                obs = "[BLOCKED by guardrail]"
            elif action == "python":
                status, detail = self.execute(action_input)
                obs = f"[python {status}] {detail}".strip()
            elif action in self.tools:
                try:
                    obs = f"[{action}] {self.tools[action](action_input)}"
                except Exception as e:
                    obs = f"[{action} error] {e}"
            else:
                obs = f"[unknown action: {action}]"

            self.emit(f"→ {action}: {action_input[:120]}", source=self.name)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {obs}"})

        self.last_result = "[max steps reached]"
        self.emit(self.last_result, source="system")

    def chat(self, message: str) -> None:
        """对话入口(run 的语义化别名)。返回 None, 显示靠 emit, 结果在 self.last_result。"""
        return self.run(message)
