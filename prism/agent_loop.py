"""prism agent loop — prime-agent agent-loop.ts 的 Python 借鉴版。

核心: function calling(非文本 ReAct) + 事件流 + 流式 + abort + 五扩展点 patch(原则 11)。
砍掉 compaction/steering/parallel(后续阶段加)。

五扩展点(原则 11, 接 PatchRegistry):
  build_messages   消息组装后      before/after
  stream_response  调 model 流式    before/after
  execute_tools    执行工具调用     before/after/around(可改/短路/降级)
  should_stop      判停             before/after(ctx.stop 可被改)
  emit             每个 emit 事件    before/after(ctx.event 可被改)

事件协议(对齐 pi: message_update/tool_execution_*/turn_*/agent_*):
  agent_start / turn_start
  message_start                 一轮 assistant 消息开始(对齐 pi)
  message_update {delta}        流式文本片段(对齐 pi text_delta)
  message_end  {text}           一轮 assistant 文本完整
  tool_execution_start {tool_name,args}   工具调用开始(对齐 pi)
  tool_execution_end   {tool_name,result,is_error}
  turn_end / agent_end
  patch_error {phase,point,error}   prism 增量(pi 无)
"""
from __future__ import annotations
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable

from .patch import PatchRegistry


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
                   max_turns: int = 1000, history: list[dict] | None = None,
                   patches: PatchRegistry | None = None,
                   max_retries: int = 0,
                   steer_check: Callable[[], bool] | None = None) -> list[dict]:
    """function-calling agent loop。返回本次累积的 messages(含 system)。

    patches=None 时建一个空 PatchRegistry(no-op), 行为与无 patch 完全一致。
    """
    patches = patches if patches is not None else PatchRegistry(emit)
    abort = abort or threading.Event()
    tool_map = {t.name: t for t in tools}

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages += history
    messages.append({"role": "user", "content": user_input})

    # build_messages 点
    ctx_build = {"messages": messages, "user_input": user_input}
    patches.run_before("build_messages", ctx_build)
    patches.run_after("build_messages", ctx_build)

    def _emit(event: dict) -> None:
        """emit 点: before/after patch 可观察/改事件。"""
        ctx_e = {"event": event}
        patches.run_before("emit", ctx_e)
        emit(ctx_e["event"])
        patches.run_after("emit", ctx_e)

    _emit({"type": "agent_start"})
    for _turn in range(max_turns):
        if abort.is_set():
            break  # pragma: no cover  (精确时序触发)
        if steer_check and steer_check():
            _emit({"type": "steer_interrupt"})
            break  # steer 插队: 中断当前 run, actor 线程处理 inbox
        _emit({"type": "turn_start"})

        # ── stream_response 点(before/after) + retry(对齐 pi auto_retry) ──
        ctx_stream = {"messages": messages, "tools": tools}
        patches.run_before("stream_response", ctx_stream)
        _emit({"type": "message_start"})          # 对齐 pi: assistant 消息开始
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for attempt in range(max_retries + 1):
            try:
                for ev in model.chat_stream(ctx_stream["messages"],
                                            tools=[_to_schema(t) for t in ctx_stream["tools"]]):
                    if abort.is_set():
                        break
                    if ev["type"] == "delta" and ev.get("text"):
                        text_parts.append(ev["text"])
                        _emit({"type": "message_update", "delta": ev["text"]})
                    elif ev["type"] == "reasoning" and ev.get("text"):
                        _emit({"type": "reasoning", "text": ev["text"]})
                    elif ev["type"] == "done":
                        tool_calls = ev.get("tool_calls") or []
                break  # 成功跳出 retry
            except Exception as e:
                text_parts, tool_calls = [], []    # 重置重试
                if attempt < max_retries:
                    _emit({"type": "auto_retry_start", "attempt": attempt + 1,
                           "error": f"{type(e).__name__}: {e}"})
                    continue
                _emit({"type": "auto_retry_end", "attempts": attempt + 1, "gave_up": True,
                       "error": f"{type(e).__name__}: {e}"})
                raise
        full_text = "".join(text_parts)
        _emit({"type": "message_end", "text": full_text})
        patches.run_after("stream_response", ctx_stream)

        asst: dict = {"role": "assistant", "content": full_text or None}
        if tool_calls:
            # 规范化: 喂回 LLM 时每个 tool_call 必须有 type: function(openai 要求)
            asst["tool_calls"] = [
                {**tc, "type": "function"} if "type" not in tc else tc
                for tc in tool_calls
            ]
        messages.append(asst)

        # ── should_stop 点(before/after; ctx.stop 可被 before 改) ──
        ctx_stop = {"messages": messages, "stop": not tool_calls}
        patches.run_before("should_stop", ctx_stop)
        patches.run_after("should_stop", ctx_stop)

        if ctx_stop["stop"]:
            _emit({"type": "turn_end"})
            break

        # ── execute_tools 点(before/after/around) ──
        # around 可改/短路/降级: proceed(ctx) 返回 tool messages list
        def _execute_tool_calls(ctx: dict) -> list[dict]:
            results: list[dict] = []
            for tc in ctx["tool_calls"]:
                if abort.is_set():
                    break  # pragma: no cover
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except Exception:
                    args = {}
                _emit({"type": "tool_execution_start", "tool_name": name, "args": args})

                tool = ctx["tool_map"].get(name)
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

                _emit({"type": "tool_execution_end", "tool_name": name, "result": result, "is_error": is_error})
                results.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
                if tool and tool.terminate:
                    ctx["terminate"] = True
            return results

        ctx_exec = {"tool_calls": tool_calls, "tool_map": tool_map, "terminate": False}
        patches.run_before("execute_tools", ctx_exec)
        tool_msgs = patches.apply_around("execute_tools", ctx_exec, _execute_tool_calls)
        patches.run_after("execute_tools", ctx_exec)
        messages.extend(tool_msgs)

        _emit({"type": "turn_end"})
        if ctx_exec.get("terminate"):
            break

    _emit({"type": "agent_end"})
    return messages
