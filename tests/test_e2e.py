"""黑盒端到端: Agent + spawn + inject + workspace 全链路(FakeModel 不联网)。

不看内部, 只验外部行为: 主 agent 命名空间持子 agent / inject 跨 agent /
子 agent 文件落独占 workspace / 多 agent workspace 隔离。
"""
import json
import time
from prism.agent import Agent
from prism.spawn import spawn


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


def _wait(agent, timeout=3.0):
    t0 = time.time()
    while not agent.last_result and time.time() - t0 < timeout:
        time.sleep(0.02)
    return agent.last_result


def test_e2e_main_spawns_bob_bob_writes_file(tmp_path):
    main = Agent("main", model=FakeModel([]), namespace={})
    bob = spawn("bob",
                FakeModel([("", [tc("write", {"path": "report.txt", "content": "done"})]),
                           ("finished", [])]),
                workspaces_root=str(tmp_path), parent=main)
    bob.inject({"type": "run", "input": "写个报告"})
    _wait(bob)
    # 黑盒断言: 文件落 workspace, main 持有 bob, 没污染父级
    assert (tmp_path / "bob" / "report.txt").read_text() == "done"
    assert main.namespace.get("bob") is bob
    assert bob.last_result == "finished"
    assert not (tmp_path / "report.txt").exists()           # 没落父级


def test_e2e_two_agents_isolated_workspaces(tmp_path):
    a = spawn("alice",
              FakeModel([("", [tc("write", {"path": "a.txt", "content": "A"})]), ("done", [])]),
              workspaces_root=str(tmp_path))
    b = spawn("bob",
              FakeModel([("", [tc("write", {"path": "b.txt", "content": "B"})]), ("done", [])]),
              workspaces_root=str(tmp_path))
    a.inject({"type": "run", "input": ""})
    b.inject({"type": "run", "input": ""})
    _wait(a)
    _wait(b)
    assert (tmp_path / "alice" / "a.txt").read_text() == "A"
    assert (tmp_path / "bob" / "b.txt").read_text() == "B"
    assert not (tmp_path / "alice" / "b.txt").exists()      # 隔离


def test_e2e_cross_agent_inject_and_eventual_read(tmp_path):
    main = Agent("main", model=FakeModel([]), namespace={})
    worker = spawn("worker", FakeModel([("work-done", [])]),
                   workspaces_root=str(tmp_path), parent=main)
    # main 视角: 通过命名空间拿到 worker 并 inject
    main.namespace["worker"].inject({"type": "run", "input": "干活"})
    assert _wait(worker) == "work-done"                      # eventual 读
