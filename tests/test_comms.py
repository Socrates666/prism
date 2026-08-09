"""多 agent 通讯测试(阶段 6, 原则 16: 读 eventual / 写 inbox)。

基础设施(actor 线程 + inbox + inject)阶段 2 已有; 这里验证跨 agent 通讯 + eventual 读。
"""
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


def _wait(agent, timeout=3.0):
    """eventual 读: 轮询 last_result 直到非空(原则 16 直接属性访问)。"""
    t0 = time.time()
    while not agent.last_result and time.time() - t0 < timeout:
        time.sleep(0.02)
    return agent.last_result


def test_inject_run_processes_async(tmp_path):             # [C1]
    bob = spawn("bob", FakeModel([("bob-hi", [])]), workspaces_root=str(tmp_path))
    bob.inject({"type": "run", "input": "hello"})
    assert _wait(bob) == "bob-hi"


def test_inject_msg_processes(tmp_path):                   # [C2]
    bob = spawn("bob", FakeModel([("got-it", [])]), workspaces_root=str(tmp_path))
    bob.inject({"type": "msg", "from": "alice", "text": "do x"})
    assert _wait(bob) == "got-it"


def test_main_reads_bob_last_result(tmp_path):             # [C3] eventual 读
    bob = spawn("bob", FakeModel([("bob-done", [])]), workspaces_root=str(tmp_path))
    bob.inject({"type": "run", "input": "go"})
    # 主视角: 直接属性访问读 bob 状态(eventual consistency, 原则 16)
    assert _wait(bob) == "bob-done"


def test_inject_returns_immediately(tmp_path):             # [C4] 不阻塞调用方
    bob = spawn("bob", FakeModel([("x", [])]), workspaces_root=str(tmp_path))
    t0 = time.time()
    bob.inject({"type": "run", "input": "..."})
    assert time.time() - t0 < 0.05                         # 递条子立即返回


def test_spawn_registers_in_parent_namespace(tmp_path):    # 跨 agent 便利
    main = Agent("main", model=FakeModel([]))
    bob = spawn("bob", FakeModel([("b", [])]), workspaces_root=str(tmp_path), parent=main)
    assert main.namespace.get("bob") is bob                # 主 agent 命名空间有 bob
    bob2 = main.namespace["bob"]                           # 主 agent 能拿到并 inject
    bob2.inject({"type": "run", "input": "hi"})
    assert _wait(bob2) == "b"
