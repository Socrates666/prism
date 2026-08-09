"""agent_loop 接入 patch 的端到端测试(阶段 3b)。

用 fake model(不联网), 验证 patch 能实际改 agent 行为 + 回归不破。
"""
import json
import pytest
from prism.agent_loop import run_agent_loop, Tool
from prism.patch import PatchRegistry
from prism.agent import Agent


# ── fakes ──────────────────────────────────────────
class FakeModel:
    """按 script 顺序吐响应。script = [(text, tool_calls), ...]。"""
    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def chat_stream(self, messages, tools=None):
        text, tcs = self.script[self.i]
        self.i += 1
        if text:
            yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def tc(name="echo", arg=None, cid="1"):
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arg or {})}}


def make_echo(calls):
    def exec_(a):
        calls.append(a.get("x"))
        return "hi"
    return Tool("echo", "", {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}, exec_)


def two_turn_script():
    """turn1 调 echo, turn2 给最终文本 'done'。"""
    return [("", [tc("echo", {"x": "a"})]), ("done", [])]


def _boom():
    raise ValueError("patch exploded")


# ── CHECKS ─────────────────────────────────────────
def test_no_patch_loop_runs_normally():                  # [C1] 回归
    calls = []
    tool = make_echo(calls)
    msgs = run_agent_loop(FakeModel(two_turn_script()), "sys", "go", [tool], lambda e: None)
    assert calls == ["a"]                                 # 工具被调
    assert [m["content"] for m in msgs if m["role"] == "tool"] == ["hi"]
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == "done"


def test_around_execute_tools_uppercases_results():      # [C2] around 改结果
    tool = make_echo([])
    reg = PatchRegistry()
    reg.around("execute_tools",
               lambda ctx, p: [{**m, "content": m["content"].upper()} for m in p(ctx)])
    msgs = run_agent_loop(FakeModel(two_turn_script()), "sys", "go", [tool],
                          lambda e: None, patches=reg)
    assert [m["content"] for m in msgs if m["role"] == "tool"] == ["HI"]


def test_around_execute_tools_short_circuits():          # [C3] around 短路
    calls = []
    tool = make_echo(calls)
    reg = PatchRegistry()
    reg.around("execute_tools", lambda ctx, p: [
        {"role": "tool", "tool_call_id": ctx["tool_calls"][0].get("id"), "content": "intercepted"}])
    msgs = run_agent_loop(FakeModel(two_turn_script()), "sys", "go", [tool],
                          lambda e: None, patches=reg)
    assert calls == []                                    # 原工具没跑
    assert [m["content"] for m in msgs if m["role"] == "tool"] == ["intercepted"]


def test_emit_after_patch_observes_events():             # [C4] emit after 副作用
    seen = []
    tool = make_echo([])
    reg = PatchRegistry()
    reg.after("emit", lambda ctx: seen.append(ctx["event"]["type"]))
    run_agent_loop(FakeModel(two_turn_script()), "sys", "go", [tool],
                   lambda e: None, patches=reg)
    assert "tool_execution_start" in seen
    assert "tool_execution_end" in seen


def test_around_execute_tools_exception_degrades():      # [C5] around 异常降级
    errs = []
    tool = make_echo([])
    reg = PatchRegistry(emit=lambda e: errs.append(e))
    reg.around("execute_tools", lambda ctx, p: _boom())
    msgs = run_agent_loop(FakeModel(two_turn_script()), "sys", "go", [tool],
                          lambda e: None, patches=reg)
    assert [m["content"] for m in msgs if m["role"] == "tool"] == ["hi"]   # 降级走原逻辑
    assert any(e.get("type") == "patch_error" and e.get("phase") == "around" for e in errs)


def test_agent_holds_patches_and_applies():              # Agent 级端到端: patch 真接通
    tool = make_echo([])
    agent = Agent("t", model=FakeModel(two_turn_script()), tools=[tool])
    agent.patches.around("execute_tools",
                         lambda ctx, p: [{**m, "content": m["content"].upper()} for m in p(ctx)])
    agent.run("go")
    tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["content"] == "HI"


def test_tool_terminate_stops_loop():                          # Tool.terminate=True→loop 停
    tool = Tool("stop", "", {"type": "object", "properties": {}}, lambda a: "done", terminate=True)
    model = FakeModel([("", [tc("stop", {})]), ("never-reached", [])])
    msgs = run_agent_loop(model, "s", "g", [tool], lambda e: None)
    assert any(m["role"] == "tool" for m in msgs)            # stop 被执行
    assert len([m for m in msgs if m["role"] == "assistant"]) == 1  # 只 1 轮(terminate 中断)
