"""覆盖率缺口补充(冲 100%): 各模块未覆盖的错误/边缘路径。"""
import sys
import time
import types
import json
import pytest

from prism.agent_loop import run_agent_loop, Tool
from prism.agent import Agent, _user_ns
from prism.patch import PatchRegistry
from prism.registry import Registry
from prism.memory import FileMemory
from prism.spawn import make_file_tools, spawn
from prism.model import OpenAIModel


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "delta", "text": "r"}
        yield {"type": "done", "tool_calls": []}

    def chat(self, m):
        return "summary"


# ── agent 缺口 ──────────────────────────────────────
def test_agent_execute_ok_and_error():
    a = Agent("a", model=_M(), actor=False)
    assert a.execute("x=1")[0] == "ok"
    assert a.execute("1/0")[0] == "error"


def test_agent_chat_calls_run():
    a = Agent("a", model=_M(), actor=False)
    a.chat("hi")
    assert a.last_result == "r"


def test_agent_stop_sets_abort():
    a = Agent("a", model=_M(), actor=False)
    a.stop()
    assert a.abort.is_set()


def test_agent_compact_empty_and_with_messages():
    a = Agent("a", model=_M(), actor=False)
    assert a.compact() == ""                           # 空 messages
    a.messages = [{"role": "user", "content": "x"}]
    assert a.compact("extra") == "summary"
    assert len(a.messages) == 1


def test_agent_custom_system_prompt_string_overrides():
    a = Agent("a", model=_M(), system_prompt="CUSTOM", actor=False)
    assert a.system_prompt == "CUSTOM"


def test_agent_emit_tracks_reasoning_and_errors():
    a = Agent("a", model=_M(), actor=False)
    a.emit({"type": "reasoning", "text": "think"})
    assert a.streaming_reasoning == "think"
    a.emit({"type": "tool_execution_end", "is_error": True, "result": "boom"})
    assert "boom" in a.error_message
    a.emit({"type": "error", "error": "bad"})
    assert a.error_message == "bad"


def test_agent_subscriber_exception_swallowed():
    a = Agent("a", model=_M(), actor=False)

    def bad_sub(e):
        raise RuntimeError("x")
    a.subscribe(bad_sub)
    a.emit({"type": "agent_start"})                    # subscriber 抛但不传播


def test_user_ns_no_ipython():
    fake = types.ModuleType("IPython")
    fake.get_ipython = lambda: (_ for _ in ()).throw(ImportError("nope"))
    real = sys.modules.get("IPython")
    sys.modules["IPython"] = fake
    try:
        assert _user_ns() == {}
    finally:
        if real:
            sys.modules["IPython"] = real
        else:
            sys.modules.pop("IPython", None)


def test_actor_loop_emits_error_on_handler_exception():
    class BoomM:
        model = "b"
        thinking_level = None

        def chat_stream(self, m, tools=None):
            raise RuntimeError("model boom")
    a = Agent("a", model=BoomM(), actor=True)
    errs = []
    a.subscribe(lambda e: errs.append(e))
    a.inject({"type": "run", "input": "x"})
    for _ in range(40):
        if any(e.get("type") == "error" for e in errs):
            break
        time.sleep(0.05)
    assert any(e.get("type") == "error" for e in errs)


def test_h_msg_handler_runs():
    a = Agent("a", model=_M(), actor=False)
    a._h_msg({"from": "bob", "text": "hi"})
    assert a.last_result == "r"


# ── agent_loop 缺口 ─────────────────────────────────
def test_loop_abort_breaks_during_stream():
    import threading
    abort = threading.Event()

    class AbortM:
        def chat_stream(self, m, tools=None):
            abort.set()
            yield {"type": "delta", "text": "x"}
            yield {"type": "done", "tool_calls": []}
    run_agent_loop(AbortM(), "s", "g", [], lambda e: None, abort=abort)


def test_loop_retry_gives_up_after_max():
    class BoomM:
        def chat_stream(self, m, tools=None):
            raise RuntimeError("always")
    with pytest.raises(RuntimeError):
        run_agent_loop(BoomM(), "s", "g", [], lambda e: None, max_retries=2)


# ── model 缺口 ──────────────────────────────────────
def test_model_chat_nonstream_method():
    m = OpenAIModel.__new__(OpenAIModel)
    resp = type("R", (), {"choices": [type("C", (), {"message": type("Msg", (), {"content": "hello"})()})()]})()

    class FC:
        chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(lambda **k: resp)})()})()
    m.client = FC(); m.model = "t"; m.thinking_level = None; m._first_timeout = 5
    assert m.chat([{"role": "user", "content": "x"}]) == "hello"


def test_non_stream_create_error_yields_empty_done():
    m = OpenAIModel.__new__(OpenAIModel)

    def boom(**k):
        raise RuntimeError("down")
    FC = type("FC", (), {"chat": type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(boom)})()})()})
    m.client = FC(); m.model = "t"; m.thinking_level = None; m._first_timeout = 5
    assert list(m._non_stream([{"role": "user", "content": "x"}], None)) == [{"type": "done", "tool_calls": []}]


# ── registry 缺口 ───────────────────────────────────
def test_registry_prompt_skill_get():
    r = Registry()
    r.prompt("p", "text")
    r.skill("s", {"x": 1})
    assert r.get_prompt("p") == "text"
    assert r.get_skill("s") == {"x": 1}
    assert r.get_prompt("nope") is None
    assert r.get_skill("nope") is None


# ── patch 缺口 ──────────────────────────────────────
def test_patch_has():
    reg = PatchRegistry()
    assert reg.has("emit") is False
    reg.before("emit", lambda ctx: None)
    assert reg.has("emit") is True


# ── spawn 缺口 ──────────────────────────────────────
def test_make_file_tools_read_missing_and_ls_nondir(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tools = {t.name: t for t in make_file_tools(ws)}
    assert tools["read"].execute({"path": "nope"})[0] == "error"
    (ws / "f").write_text("x")
    assert tools["ls"].execute({"path": "f"})[0] == "error"


def test_spawn_with_emit_sets_hook(tmp_path):
    emits = []
    bob = spawn("bob", _M(), emit=lambda e: emits.append(e), workspaces_root=str(tmp_path))
    assert bob.hooks["emit"] is not None
    assert bob.workspace == tmp_path / "bob"


# ── memory 缺口 ─────────────────────────────────────
def test_memory_keys_empty(tmp_path):
    assert FileMemory(tmp_path).keys() == []
