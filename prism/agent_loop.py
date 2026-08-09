"""prism agent loop — prime-agent agent-loop.ts 的 Python 借鉴版。

核心: function calling(非文本 ReAct) + 事件流 + 流式 + abort。
砍掉 compaction/steering/parallel(后续阶段加)。

事件协议(emit 接收 dict):
  agent_start / turn_start
  message_delta {text}     流式文本片段
  message_end  {text}      一轮 assistant 文本完整
  tool_start   {name,args} 工具调用开始
  tool_end     {name,result,is_error}
  turn_end / agent_end
"""
from __future__ import annotations
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable


EventSink = Callable[[dict], None]


@dataclass
class Tool:
    """一个可被 LLM 调用的工具(JSON schema + execute)。"""
    name: str
    description: str
    parameters: dict                          # JSON schema
    execute: Callable[[dict], Any]            # args dict -> str | (str, is_error)
    terminate: bool = False                   # execute 后是否终止整个 loop


def _to_schema(tool: Tool) -> dict:
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description, "parameters": tool.parameters,
    }}


def run_agent_loop(model, system_prompt: str, user_input: str, tools: list[Tool],
                   emit: EventSink, *, abort: threading.Event | None = None,
                   max_turns: int = 20, history: list[dict] | None = None) -> list[dict]:
    """function-calling agent loop。返回本次累积的 messages(含 system)。"""
    abort = abort or threading.Event()
    tool_map = {t.name: t for t in tools}

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages += history
    messages.append({"role": "user", "content": user_input})

    emit({"type": "agent_start"})
    for _turn in range(max_turns):
        if abort.is_set():
            break
        emit({"type": "turn_start"})

        # ── 流式取 assistant 响应 + 累积 tool_calls ──
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for ev in model.chat_stream(messages, tools=[_to_schema(t) for t in tools]):
            if abort.is_set():
                break
            if ev["type"] == "delta" and ev.get("text"):
                text_parts.append(ev["text"])
                emit({"type": "message_delta", "text": ev["text"]})
            elif ev["type"] == "done":
                tool_calls = ev.get("tool_calls") or []
        full_text = "".join(text_parts)
        emit({"type": "message_end", "text": full_text})

        asst: dict = {"role": "assistant", "content": full_text}
        if tool_calls:
            asst["tool_calls"] = tool_calls
        messages.append(asst)

        # 无工具调用 → 本轮结束, loop 停
        if not tool_calls:
            emit({"type": "turn_end"})
            break

        # ── 执行工具(顺序, prime-agent 的串行模式) ──
        should_terminate = False
        for tc in tool_calls:
            if abort.is_set():
                break
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}") or "{}")
            except Exception:
                args = {}
            emit({"type": "tool_start", "name": name, "args": args})

            tool = tool_map.get(name)
            if not tool:
                result, is_error = f"工具 '{name}' 不存在", True
            else:
                try:
                    out = tool.execute(args)
                    if isinstance(out, tuple) and len(out) == 2:
                        result, is_error = out
                    else:
                        result, is_error = out, False
                except Exception as e:
                    result, is_error = f"{type(e).__name__}: {e}", True

            emit({"type": "tool_end", "name": name, "result": result, "is_error": is_error})
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
            if tool and tool.terminate:
                should_terminate = True

        emit({"type": "turn_end"})
        if should_terminate:
            break

    emit({"type": "agent_end"})
    return messages
