"""阶段12 运行时接通测试: theme 口子 + 子 agent emit + /spawn。"""
import asyncio
from prism.shell import PrismApp, ThemeCtl
from prism.commands import load_commands


def test_themectl_set_dispatches_to_call_from_thread():
    calls = []

    class FakeApp:
        def call_from_thread(self, fn, *a):
            calls.append((fn.__name__, a))

    ThemeCtl(FakeApp()).set("nord")
    assert calls == [("_apply", ("nord",))]


def test_themectl_list_sorted():
    class FakeApp:
        available_themes = {"nord": 1, "dark": 2, "forest": 3}

    assert ThemeCtl(FakeApp()).list() == ["dark", "forest", "nord"]


def test_tui_theme_in_namespace():
    async def run():
        async with PrismApp().run_test() as pilot:
            ns = pilot.app.agent.namespace
            assert "theme" in ns and isinstance(ns["theme"], ThemeCtl)
    asyncio.run(run())


def test_make_subagent_emit_callable_and_safe():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.call_from_thread = lambda *a, **k: None   # mock: 不真跨线程(避免 pilot 死锁)
            emit = pilot.app.make_subagent_emit("bob")
            assert callable(emit)
            for ev in [{"type": "message_update", "delta": "hi"},
                       {"type": "message_end"},
                       {"type": "tool_execution_start", "tool_name": "x"},
                       {"type": "tool_execution_end", "is_error": False, "result": "ok"},
                       {"type": "error", "error": "boom"}]:
                emit(ev)
            await pilot.pause()
    asyncio.run(run())


def test_spawn_command_creates_subagent(monkeypatch):
    cmds = load_commands("ext")
    created = []

    class FakeSub:
        kind = "sub"
        def apply_prompt(self, sections, name=None, kind="main"): pass

    def fake_spawn(name, model, *, emit=None, parent=None, **kw):
        s = FakeSub()
        created.append((name, parent, emit))
        if parent is not None:
            parent.namespace[name] = s
        return s

    monkeypatch.setattr("prism.spawn.spawn", fake_spawn)
    monkeypatch.setattr("prism.model.OpenAIModel", lambda *a, **k: None)

    class FakeApp:
        def make_subagent_emit(self, n):
            return lambda e: None

    class FakeAgent:
        def __init__(self):
            self.namespace = {}

    ctx = {"app": FakeApp(), "agent": FakeAgent(), "commands": cmds}
    r = cmds["spawn"].run("bob", ctx)
    assert "已 spawn" in r
    assert created[0][0] == "bob"
    assert "bob" in ctx["agent"].namespace
    assert ctx["agent"].namespace["bob"].kind == "sub"
