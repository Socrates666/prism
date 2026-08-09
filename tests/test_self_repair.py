"""增量扩建自我修复 + 护栏测试(阶段 7, 原则 2/7/10)。"""
import json
from pathlib import Path
import prism
from prism.agent import Agent
from prism.agent_loop import Tool


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


def tc(name="echo", arg=None, cid="1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(arg or {})}}


def make_echo(calls):
    def e(a):
        calls.append(a.get("x"))
        return "hi"
    return Tool("echo", "", {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}, e)


def test_add_patch_changes_behavior():                   # [C1] 运行时加 patch 改 react
    calls = []
    agent = Agent("a", model=FakeModel([("", [tc("echo", {"x": "a"})]), ("done", [])]),
                  tools=[make_echo(calls)])
    agent.add_patch("execute_tools", lambda ctx: calls.append("before-exec"), kind="before")
    agent.run("go")
    assert "before-exec" in calls                        # patch 生效, 没改 agent_loop.py


def test_add_tool_runtime():                            # [C2] 运行时加 tool
    agent = Agent("a", model=FakeModel([("", [tc("newtool", {})]), ("done", [])]), tools=[])
    agent.add_tool(Tool("newtool", "", {"type": "object", "properties": {}}, lambda a: "nt-ok"))
    assert "newtool" in [t.name for t in agent._tools()]
    agent.run("go")
    tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["content"] == "nt-ok"


def test_add_patch_bad_kind_raises():
    agent = Agent("a", model=FakeModel([]))
    try:
        agent.add_patch("execute_tools", lambda ctx: None, kind="sideways")
        assert False, "应报错"
    except ValueError:
        pass


def test_guard_blocks_write_to_prism_core():            # [C3] 护栏拦 prism/
    agent = Agent("a", model=FakeModel([]))
    core_file = Path(prism.__file__).parent / "agent.py"
    status, detail = agent.execute(f"open({str(core_file)!r}, 'w')")
    assert status == "error"
    assert "护栏" in detail                              # PermissionError 被捕获


def test_guard_allows_write_elsewhere(tmp_path):        # [C4] 放行别处
    agent = Agent("a", model=FakeModel([]))
    f = tmp_path / "out.txt"
    status, _ = agent.execute(f"f = open({str(f)!r}, 'w'); f.write('ok'); f.close()")
    assert status == "ok"
    assert f.read_text() == "ok"


def test_guard_preserves_normal_python():               # [C5] 正常 python 不破坏
    agent = Agent("a", model=FakeModel([]))
    status, _ = agent.execute("import math\nx = math.sqrt(16)\nns_var = 42")
    assert status == "ok"
    assert agent.namespace.get("ns_var") == 42
    assert agent.namespace.get("x") == 4.0
