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


def test_guard_backups_and_allows_write(tmp_path, monkeypatch):   # [C3] 阶段14: 备份+放行
    """写 prism/ → 自动备份 + 放行(不再 PermissionError)。"""
    import prism.guard as g
    core = tmp_path / "prism"; core.mkdir()
    (core / "mod.py").write_text("X = 1\n")
    monkeypatch.setattr(g, "_PRISM_CORE", core)
    monkeypatch.setattr(g, "_backup_dir", lambda: tmp_path / "bak")
    (tmp_path / "bak").mkdir()
    g._backups.clear()
    with g.guarded_open(core / "mod.py", "w") as f:
        f.write("X = 2\n")
    assert (core / "mod.py").read_text() == "X = 2\n"     # 放行(不再拦)
    assert len(g._backups) == 1                            # 备份了
    assert g._backups[0][1].read_text() == "X = 1\n"       # 备份原内容


def test_verify_reverts_when_reload_fails(tmp_path, monkeypatch):  # 自动回退
    """reload 失败(语法/import 错)→ 还原备份 + emit error。"""
    import prism.guard as g
    core = tmp_path / "prism"; core.mkdir()
    orig = core / "mod.py"; orig.write_text("changed")
    bak = tmp_path / "mod.bak"; bak.write_text("original")
    g._backups.clear(); g._backups.append((orig, bak))
    monkeypatch.setattr("importlib.reload",
                        lambda m: (_ for _ in ()).throw(SyntaxError("bad")))
    monkeypatch.setattr(g, "_file_to_module", lambda p: "prism.mod")
    import sys
    monkeypatch.setitem(sys.modules, "prism.mod", object())   # 自动还原, 避免污染后续 test
    errs = []
    ok = g.verify_and_revert(lambda e: errs.append(e))
    assert not ok                                         # 回退了
    assert orig.read_text() == "original"                 # 还原
    assert errs                                           # emit error


def test_revert_latest_restores(tmp_path):               # /revert 手动回退
    """revert_latest 还原最近改动 + 弹栈。"""
    import prism.guard as g
    core = tmp_path / "prism"; core.mkdir()
    orig = core / "mod.py"; orig.write_text("changed")
    bak = tmp_path / "mod.bak"; bak.write_text("original")
    g._backups.clear(); g._backups.append((orig, bak))
    name = g.revert_latest(lambda e: None)
    assert name == "mod.py"
    assert orig.read_text() == "original"
    assert g._backups == []                               # 弹出


def test_list_backups(tmp_path):                         # /backups 列
    import prism.guard as g
    g._backups.clear()
    g._backups.append((tmp_path / "a.py", tmp_path / "a.bak"))
    assert g.list_backups() == [("a.py", "a.bak")]


def test_file_to_module_mapping():
    from prism.guard import _file_to_module, _PRISM_CORE
    assert _file_to_module(_PRISM_CORE / "agent.py") == "prism.agent"
    assert _file_to_module(_PRISM_CORE / "__init__.py") == "prism"
    assert _file_to_module(_PRISM_CORE / "sub" / "x.py") == "prism.sub.x"   # 多 parts
    assert _file_to_module(_PRISM_CORE.parent / "ext" / "x.py") is None  # 非 prism/
    assert _file_to_module(_PRISM_CORE / "x.txt") is None                # 非 .py


def test_backup_dir_creates_real_dir(tmp_path, monkeypatch):
    import prism.guard as g
    monkeypatch.setattr(g, "_PRISM_CORE", tmp_path / "prism")
    d = g._backup_dir()                                  # 真实 mkdir
    assert d.exists() and d.name == "backups"


def test_verify_no_changes_returns_true():
    import prism.guard as g
    g._backups.clear()
    assert g.verify_and_revert(lambda e: None) is True   # 无改动 → True


def test_backup_missing_file_returns_none(tmp_path):
    import prism.guard as g
    assert g._backup(tmp_path / "nope.py") is None       # 文件不存在 → None


def test_agent_execute_verify_fails_reverts(tmp_path, monkeypatch):  # verify 失败→回退
    """agent 改 → reload 失败 → 自动回退 + error。"""
    import sys
    import prism.guard as g
    core = tmp_path / "prism"; core.mkdir()
    (core / "mod.py").write_text("X = 1")
    monkeypatch.setattr(g, "_PRISM_CORE", core)
    g._backups.clear()
    monkeypatch.setattr("importlib.reload",
                        lambda m: (_ for _ in ()).throw(SyntaxError("bad")))
    monkeypatch.setitem(sys.modules, "prism.mod", object())
    a = Agent("a", model=FakeModel([]), actor=False)
    status, detail = a.execute(f"open(r'{core / 'mod.py'}', 'w').write('X = 2')")
    assert status == "error"
    assert "回退" in detail
    assert (core / "mod.py").read_text() == "X = 1"      # 还原备份


def test_agent_execute_verify_ok_after_edit(tmp_path, monkeypatch):  # agent 改→verify ok
    """agent.execute 改 prism/ → 备份 + verify_and_revert → 提示重启。"""
    import prism.guard as g
    core = tmp_path / "prism"; core.mkdir()
    (core / "mod.py").write_text("X = 1\n")
    monkeypatch.setattr(g, "_PRISM_CORE", core)
    g._backups.clear()
    a = Agent("a", model=FakeModel([]), actor=False)
    status, detail = a.execute(f"open(r'{core / 'mod.py'}', 'w').write('X = 2')")
    assert status == "ok"
    assert "重启" in detail                               # verify ok 提示重启


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
