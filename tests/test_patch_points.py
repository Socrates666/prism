"""agent_loop 其余 patch 接入点测试(白盒, 补 build_messages/stream/should_stop/emit)。"""
import json
from prism.agent_loop import run_agent_loop, Tool
from prism.patch import PatchRegistry


class FakeModel:
    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def chat_stream(self, messages, tools=None):
        text, tcs = self.script[self.i]
        self.i += 1
        if text:
            yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def tc(name, arg=None, cid="1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(arg or {})}}


def test_build_messages_before_runs():
    seen = []
    reg = PatchRegistry()
    reg.before("build_messages", lambda ctx: seen.append(len(ctx["messages"])))
    run_agent_loop(FakeModel([("ans", [])]), "sys", "hi", [], lambda e: None, patches=reg)
    assert seen                                              # before 跑了


def test_stream_before_after_run():
    before = []
    after = []
    reg = PatchRegistry()
    reg.before("stream_response", lambda ctx: before.append(1))
    reg.after("stream_response", lambda ctx: after.append(1))
    run_agent_loop(FakeModel([("x", [])]), "s", "g", [], lambda e: None, patches=reg)
    assert before and after


def test_should_stop_before_can_force_stop():
    # model 想调工具, 但 should_stop before 强制 stop → 工具不执行
    tool = Tool("t", "", {"type": "object", "properties": {}}, lambda a: "x")
    reg = PatchRegistry()
    reg.before("should_stop", lambda ctx: ctx.update({"stop": True}))
    msgs = run_agent_loop(FakeModel([("", [tc("t", {})]), ("never", [])]),
                          "s", "g", [tool], lambda e: None, patches=reg)
    assert not any(m["role"] == "tool" for m in msgs)        # 被强制停, 工具没跑


def test_emit_before_can_mutate_event():
    captured = []
    reg = PatchRegistry()

    def tag(ctx):
        if ctx["event"].get("type") == "tool_execution_end":
            ctx["event"]["tagged"] = True

    reg.before("emit", tag)
    tool = Tool("t", "", {"type": "object", "properties": {}}, lambda a: "r")
    run_agent_loop(FakeModel([("", [tc("t", {})]), ("done", [])]),
                   "s", "g", [tool], lambda e: captured.append(e), patches=reg)
    tool_ends = [e for e in captured if e.get("type") == "tool_execution_end"]
    assert tool_ends and tool_ends[0].get("tagged") is True


def test_execute_tools_before_after_run():
    tool = Tool("t", "", {"type": "object", "properties": {}}, lambda a: "r")
    seq = []
    reg = PatchRegistry()
    reg.before("execute_tools", lambda ctx: seq.append("before"))
    reg.after("execute_tools", lambda ctx: seq.append("after"))
    run_agent_loop(FakeModel([("", [tc("t", {})]), ("done", [])]),
                   "s", "g", [tool], lambda e: None, patches=reg)
    assert seq == ["before", "after"]
