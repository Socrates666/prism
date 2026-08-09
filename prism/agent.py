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
import itertools
from typing import Callable

from .agent_loop import run_agent_loop, Tool
from .patch import PatchRegistry
from .memory import MemoryBackend, NullMemory


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
    if t == "message_update":
        print(event["delta"], end="", flush=True)
    elif t == "message_end":
        if event["text"]:
            print()
    elif t == "tool_execution_start":
        print(f"  → {event['tool_name']}({event['args']})")
    elif t == "tool_execution_end":
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
                 system_prompt_override: str | None = None,
                 append_system_prompt: list[str] | None = None,
                 namespace: dict | None = None, tools: list[Tool] | None = None,
                 max_turns: int = 20, kind: str = "main", actor: bool = True,
                 registry=None, max_retries: int = 0, thinking_level: str = "off",
                 memory: MemoryBackend | None = None):
        self.name = name
        self.model = model
        self.kind = kind                  # "main"(完整IPython, 有python工具) / "sub"(工厂受限, 无裸exec)
        # 结构化 system prompt(阶段13: 角色/环境/能力/指令/准则/goal/skills 拆分)
        from .prompt import SystemPrompt
        self.prompt = SystemPrompt()
        if system_prompt_override is not None:
            self.prompt.set_override(system_prompt_override)
        elif system_prompt:
            self.prompt.set_override(system_prompt)   # 自定义 system_prompt = 整体(兼容)
        else:
            pass  # 默认段由人格插件(ext/prompts/)注入, base 不硬编码(原则 12)
        for ap in (append_system_prompt or []):
            self.prompt.add_extra(ap)
        self.namespace = namespace if namespace is not None else _user_ns()
        self.namespace.setdefault(name, self)   # agent 注册进命名空间, 能被自己/别的对象操作
        self.max_turns = max_turns
        self.last_result: str = ""            # prism 增量便利(pi 无, 从 messages 提取最后 assistant)
        self.memory = memory if memory is not None else NullMemory()
        self.messages: list[dict] = list(self.memory.load(name))   # 启动恢复(原则6 跨会话)
        self.streaming_message: str | None = None   # 对齐 pi: 当前流式中的文本
        self.streaming_reasoning: str | None = None   # 对齐 pi: 当前思考过程(reasoning_content)
        self.error_message: str = ""          # 对齐 pi: 最近错误
        self.thinking_level: str = thinking_level     # 对齐 pi thinkingLevel
        self.max_retries: int = max_retries           # 对齐 pi retry.maxRetries
        if hasattr(self.model, "thinking_level"):
            self.model.thinking_level = thinking_level   # 同步到 model 层(如 OpenAIModel)
        self.hooks: dict[str, Callable] = {"emit": _default_emit}
        self.patches = PatchRegistry(self.emit)   # 五扩展点 patch 注册表(原则 11)
        self.abort = threading.Event()
        self._extra_tools: list[Tool] = list(tools or [])
        if registry is not None:
            self._extra_tools += registry.tools()    # 全局共享池的 tool(原则 12)
        self.workspace = None             # 子 agent 由 spawn 设(原则14)
        # actor(原则15): inbox 总在(PriorityQueue 支持 steer/followUp 优先级); actor 只控是否起线程
        self.inbox: queue.PriorityQueue = queue.PriorityQueue()
        self._inject_seq = itertools.count()
        self._subscribers: list[Callable] = []
        self._handlers: dict[str, Callable] = {"run": self._h_run, "msg": self._h_msg}
        if actor:
            self._thread = threading.Thread(target=self._actor_loop, daemon=True)
            self._thread.start()

    @property
    def system_prompt(self) -> str:
        """结构化 system prompt 渲染(阶段13, 各段组合)。"""
        return self.prompt.render()

    def apply_prompt(self, sections: dict, name: str | None = None, kind: str = "main") -> None:
        """从 ext/prompts/ 人格插件填充 prompt 段(配置外部化, 原则 12)。
        sections = {"main": {...段}, "sub": {...}}, role 支持 {name} 占位。
        """
        sec = sections.get(kind, sections.get("main", {}))
        p = self.prompt
        for k in ("role", "environment", "capabilities", "instructions", "guidelines"):
            if k in sec:
                val = sec[k]
                if name and isinstance(val, str) and "{name}" in val:
                    val = val.format(name=name)
                setattr(p, k, val)

    def append_to_system_prompt(self, text: str) -> None:
        """自由追加 system prompt(进 extra 段, 对齐 pi appendSystemPromptOverride)。"""
        self.prompt.add_extra(text)

    def emit(self, event: dict) -> None:
        """emit 点: 跟踪 streaming_message/error_message(对齐 pi state) + 转 hooks。"""
        t = event.get("type")
        if t == "message_update":
            self.streaming_message = (self.streaming_message or "") + event.get("delta", "")
        elif t == "message_end":
            self.streaming_message = None
        elif t == "reasoning":
            self.streaming_reasoning = (self.streaming_reasoning or "") + event.get("text", "")
        elif t == "tool_execution_end" and event.get("is_error"):
            self.error_message = str(event.get("result", ""))[:500]
        elif t == "error":
            self.error_message = str(event.get("error", ""))
        self.hooks["emit"](event)
        for sub in list(self._subscribers):
            try:
                sub(event)
            except Exception:
                pass

    def subscribe(self, listener: Callable[[dict], None]):
        """显式订阅事件流(对齐 pi session.subscribe)。返回 unsubscribe 函数。"""
        self._subscribers.append(listener)

        def unsubscribe() -> None:
            if listener in self._subscribers:
                self._subscribers.remove(listener)
        return unsubscribe

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
            history=self.messages, patches=self.patches, max_retries=self.max_retries,
        )
        for m in reversed(msgs):
            if m.get("role") == "assistant" and m.get("content"):
                self.last_result = m["content"]
                break
        self.messages = [m for m in msgs if m.get("role") != "system"]
        self.dump()

    def dump(self) -> None:
        """持久化 messages 到 memory(原则6 跨会话状态器官)。"""
        self.memory.save(self.name, self.messages)

    # ── actor(原则15/16) ──────────────────────────────
    def inject(self, msg: dict, *, kind: str = "followUp") -> None:
        """递条子(异步, 跨线程)。立即返回, 不等处理。

        kind(对齐 pi steer/followUp):
          steer    插队优先(高优先级, 排在 followUp 前)
          followUp 常规排队(默认)
        通讯分层(原则16): 触发 agent 行动用 inject(B 自己线程处理, 无 race)。
        """
        priority = 0 if kind == "steer" else 10
        self.inbox.put((priority, next(self._inject_seq), msg))

    def _actor_loop(self) -> None:
        """agent 自己的线程: 等 inbox → 处理(在自己线程, 不阻塞别的 agent)。"""
        while True:
            _, _, msg = self.inbox.get()
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

    # ── 对齐 pi: thinking / compaction ─────────────────
    def set_thinking_level(self, level: str) -> None:
        """对齐 pi thinkingLevel(off/minimal/low/medium/high/xhigh/max)。同步到 model 层。"""
        self.thinking_level = level
        if hasattr(self.model, "thinking_level"):
            self.model.thinking_level = level

    def compact(self, instructions: str = "") -> str:
        """对齐 pi compact(): 把 messages 压成摘要, 替换历史, 释放上下文。返回摘要。"""
        if not self.messages:
            return ""
        rendered = "\n\n".join(f"[{m.get('role')}] {m.get('content', '')}" for m in self.messages)
        prompt = ("把以下对话压成简洁的上下文摘要, 保留关键事实/决策/待办, 供后续继续。"
                  + (f"\n额外要求: {instructions}" if instructions else "")
                  + f"\n\n{rendered}")
        summary = self.model.chat([{"role": "user", "content": prompt}])
        self.messages = [{"role": "user", "content": f"[之前对话摘要]\n{summary}"}]
        self.last_result = summary
        return summary
