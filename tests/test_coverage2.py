"""覆盖率缺口补充 2: router/patch/spawn/model/agent_loop/shell emit/__init__。"""
import sys
import types
import pytest

from prism.agent import Agent, _user_ns
from prism.agent_loop import run_agent_loop, Tool
from prism.model import ModelBackend, OpenAIModel
from prism.patch import PatchRegistry
from prism.spawn import make_file_tools
import prism.router as router_mod


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


# ── agent: IPython 可用 + python tool ──
def test_user_ns_with_ipython():
    fake = types.ModuleType("IPython")

    class Shell:
        user_ns = {"x": 1}
    fake.get_ipython = lambda: Shell()
    real = sys.modules.get("IPython")
    sys.modules["IPython"] = fake
    try:
        assert _user_ns() == {"x": 1}
    finally:
        if real:
            sys.modules["IPython"] = real
        else:
            sys.modules.pop("IPython", None)


def test_python_tool_execute_ok_and_error():
    a = Agent("a", model=_M(), actor=False)
    py = a._tools()[0]                                  # python tool
    assert "ok" in py.execute({"code": "x=1"})
    assert "error" in py.execute({"code": "1/0"})
    assert "hello" in py.execute({"code": "print('hello')"})   # print 输出进 result


# ── agent_loop: tool 不存在 / args error / tool 异常 / reasoning ──
def _tc(name="t", args="{}"):
    return {"id": "1", "type": "function", "function": {"name": name, "arguments": args}}


def test_loop_unknown_tool_emits_error():
    class MM:
        def chat_stream(self, m, tools=None):
            yield {"type": "done", "tool_calls": [_tc("ghost")]}
    ev = []
    run_agent_loop(MM(), "s", "g", [], lambda e: ev.append(e))
    assert any(e.get("is_error") for e in ev if e.get("type") == "tool_execution_end")


def test_loop_tool_args_parse_error_swallowed():
    tool = Tool("t", "", {"type": "object", "properties": {}}, lambda a: "ok")

    class MM:
        def chat_stream(self, m, tools=None):
            yield {"type": "done", "tool_calls": [_tc("t", "NOT JSON")]}
    run_agent_loop(MM(), "s", "g", [tool], lambda e: None)   # 不崩


def test_loop_tool_execute_exception():
    tool = Tool("t", "", {"type": "object", "properties": {}},
                lambda a: (_ for _ in ()).throw(ValueError("boom")))

    class MM:
        def chat_stream(self, m, tools=None):
            yield {"type": "done", "tool_calls": [_tc("t")]}
    ev = []
    run_agent_loop(MM(), "s", "g", [tool], lambda e: ev.append(e))
    assert any(e.get("is_error") and "ValueError" in e.get("result", "") for e in ev)


def test_loop_reasoning_forwarded():
    class MM:
        def chat_stream(self, m, tools=None):
            yield {"type": "reasoning", "text": "think"}
            yield {"type": "delta", "text": "ans"}
            yield {"type": "done", "tool_calls": []}
    ev = []
    run_agent_loop(MM(), "s", "g", [], lambda e: ev.append(e))
    assert any(e.get("type") == "reasoning" for e in ev)


# ── model ──
def test_model_backend_chat_abstract():
    with pytest.raises(NotImplementedError):
        ModelBackend().chat([])


def test_model_backend_chat_stream_abstract():
    with pytest.raises(NotImplementedError):
        ModelBackend().chat_stream([])


def test_chat_stream_empty_choices_and_end():
    m = OpenAIModel.__new__(OpenAIModel)
    chunks = [type("C", (), {"choices": []})(), type("C", (), {"choices": []})()]

    class FC:
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(lambda **k: iter(chunks))})()})()
    m.client = FC(); m.model = "t"; m.thinking_level = None; m._first_timeout = 5
    ev = list(m.chat_stream([{"role": "user", "content": "x"}]))
    assert ev[-1]["type"] == "done"


def test_chat_stream_producer_error_raises():
    m = OpenAIModel.__new__(OpenAIModel)

    class FC:
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(lambda **k: (_ for _ in ()).throw(RuntimeError("x")))})()})()
    m.client = FC(); m.model = "t"; m.thinking_level = None; m._first_timeout = 5
    with pytest.raises(RuntimeError):
        list(m.chat_stream([{"role": "user", "content": "x"}]))


# ── patch after 异常 ──
def test_patch_after_exception_emits():
    emits = []
    reg = PatchRegistry(emit=lambda e: emits.append(e))
    reg.after("execute_tools", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")))
    reg.run_after("execute_tools", {})
    assert any(e.get("phase") == "after" for e in emits)


# ── spawn read 目录抛 ──
def test_make_file_tools_read_directory(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tools = {t.name: t for t in make_file_tools(ws)}
    (ws / "d").mkdir()
    assert tools["read"].execute({"path": "d"})[0] == "error"


# ── router at_route + register ──
def _with_fake_ipython(ns_factory):
    fake = types.ModuleType("IPython")
    fake.get_ipython = lambda: ns_factory()
    real = sys.modules.get("IPython")
    sys.modules["IPython"] = fake
    return real  # 返回旧值供恢复


def test_router_at_route_calls_chat():
    class A:
        def chat(self, m): self.last = m
    a = A()
    real = _with_fake_ipython(lambda: type("S", (), {"user_ns": {"alice": a}})())
    try:
        router_mod.at_route("alice", "hi")
        assert a.last == "hi"
    finally:
        if real: sys.modules["IPython"] = real
        else: sys.modules.pop("IPython", None)


def test_router_at_route_not_agent_raises():
    real = _with_fake_ipython(lambda: type("S", (), {"user_ns": {"x": 123}})())
    try:
        with pytest.raises(TypeError):
            router_mod.at_route("x", "hi")
    finally:
        if real: sys.modules["IPython"] = real
        else: sys.modules.pop("IPython", None)


def test_router_register():
    class FakeIP:
        input_transformers_post = []
        user_ns = {}
    ip = FakeIP()
    router_mod.register(ip)
    assert router_mod._transform in ip.input_transformers_post
    assert "at_route" in ip.user_ns and "at_error" in ip.user_ns


# ── commands load 缺 NAME + missing dir ──
def test_load_commands_missing_name_run(tmp_path):
    from prism.commands import load_commands
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "bad.py").write_text("X = 1\n")    # 缺 NAME/run
    errs = []
    assert load_commands(tmp_path, emit=lambda e: errs.append(e)) == {}
    assert len(errs) == 1


def test_load_commands_missing_dir(tmp_path):
    from prism.commands import load_commands
    assert load_commands(tmp_path / "nope") == {}


# ── __init__ load_ipython_extension ──
def test_load_ipython_extension_registers():
    import prism
    class FakeIP:
        input_transformers_post = []
        user_ns = {}
    ip = FakeIP()
    prism.load_ipython_extension(ip)
    assert router_mod._transform in ip.input_transformers_post


# ── shell emit 全分支(headless 自研引擎) ──
def test_shell_emit_all_branches():
    from prism.shell import PrismApp
    app = PrismApp()
    app.run(headless=True)
    emit = app.agent.hooks["emit"]
    for ev in [{"type": "message_update", "delta": "a\nb"},
               {"type": "message_end"},
               {"type": "reasoning", "text": "t\nu"},
               {"type": "tool_execution_start", "tool_name": "x", "args": {}},
               {"type": "tool_execution_end", "is_error": True, "result": "bad"},
               {"type": "error", "error": "e"},
               {"type": "patch_error", "phase": "around", "point": "p", "error": "x"}]:
        emit(ev)
    app._drain()       # 跑完所有跨线程调度, 不崩即过


def test_shell_flush_current_on_error():
    """流式中 error → flush_current 把已收到的 current 写入 transcript。"""
    from prism.shell import PrismApp
    app = PrismApp()
    app.run(headless=True)
    emit = app.agent.hooks["emit"]
    emit({"type": "message_update", "delta": "partial"})   # current = "partial"
    emit({"type": "error", "error": "boom"})               # flush_current 写 "partial"
    app._drain()
    assert "partial" in app.query_one("#transcript").lines


def test_tui_slash_unknown_command():
    from prism.shell import PrismApp
    from prism.tui.widgets import Input
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    dock.value = "/nope x"
    app.on_input_submitted(Input.Submitted("/nope x", dock))
    app._drain()
    assert any("未知指令" in l for l in app.query_one("#transcript").lines)


def test_tui_empty_input_noop():
    from prism.shell import PrismApp
    from prism.tui.widgets import Input
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    before = len(app.query_one("#transcript").lines)
    dock.value = "   "
    app.on_input_submitted(Input.Submitted("   ", dock))
    app._drain()
    # 空输入不 echo, transcript 不增长
    assert len(app.query_one("#transcript").lines) == before


def test_tui_python_exec_error_shown():
    from prism.shell import PrismApp
    from prism.tui.widgets import Input
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    dock.value = "1/0"
    app.on_input_submitted(Input.Submitted("1/0", dock))
    app._drain()
    assert any("ZeroDivisionError" in l for l in app.query_one("#transcript").lines)


def test_tui_revert_and_backups_builtin():              # 第一公民 /revert /backups
    from prism.shell import PrismApp
    from prism.tui.widgets import Input
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    for cmd in ["/revert", "/backups"]:
        dock.value = cmd
        app.on_input_submitted(Input.Submitted(cmd, dock))
        app._drain()


def test_tui_backups_with_changes():                     # /backups 有备份时列出
    from prism.shell import PrismApp
    from prism.tui.widgets import Input
    import prism.guard as g
    from pathlib import Path
    app = PrismApp()
    app.run(headless=True)
    g._backups.clear()
    g._backups.append((Path("a.py"), Path("a.bak")))
    dock = app.query_one("#dock")
    dock.value = "/backups"
    app.on_input_submitted(Input.Submitted("/backups", dock))
    app._drain()
    assert any("a.py" in l for l in app.query_one("#transcript").lines)
    g._backups.clear()


def test_load_commands_skips_underscore(tmp_path):
    from prism.commands import load_commands
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "_skip.py").write_text("NAME='x'\ndef run(a,c):return 1\n")
    assert load_commands(tmp_path) == {}


def test_load_ext_skips_underscore(tmp_path):
    from prism.registry import Registry, load_ext
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "_skip.py").write_text(
        "from prism.agent_loop import Tool\ndef register(r): r.tool(Tool('x','', {'type':'object','properties':{}}, lambda a:1))\n")
    assert load_ext(tmp_path, Registry()) == []
