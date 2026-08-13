"""黑盒 TUI: PrismApp 自研引擎 headless 验证结构/焦点/路由(不调 LLM)。

自研引擎 transcript 内容可读回(self.lines), 故可断言渲染文本。
"""
import time
from prism.shell import PrismApp
from prism.tui.widgets import Input
from prism.tui.terminal import Key


def mount() -> PrismApp:
    app = PrismApp()
    app.run(headless=True)          # 装配 + on_mount, 不进终端
    return app


def submit(app: PrismApp, value: str):
    dock = app.query_one("#dock")
    dock.value = value
    dock.pos = len(value)
    dock.on_key(Key(key="enter", char=""))     # 走 Input 提交路径(提交后自清, 与真实键入一致)
    app._drain()
    return app.query_one("#transcript")


def press(app: PrismApp, *keys: str) -> None:
    for k in keys:
        key = Key(key=k, char=k) if len(k) == 1 else Key(key=k, char="")
        app._dispatch_key(key)
    app._drain()


def lines(app: PrismApp) -> list[str]:
    return app.query_one("#transcript").lines


# ── 结构 ──────────────────────────────────────────────────────────────────
def test_tui_mounts_main_agent_and_widgets():
    app = mount()
    assert app.agent is not None
    assert app.agent.kind == "main"
    assert app.query_one("#transcript") is not None
    assert app.query_one("#dock") is not None
    assert app.query_one("#footer") is not None       # pi 风格四段式


def test_tui_input_focused_by_default():
    """编辑器默认聚焦; 键盘始终进 Input(transcript 不抢焦点)。"""
    app = mount()
    dock = app.query_one("#dock")
    assert app._focusable[app._focus_idx] is dock
    press(app, "a", "b", "c")
    assert dock.value == "abc"


def test_tui_at_route_unknown_agent_no_crash():
    """@未知 agent → 报错写 transcript, 但 app 不崩。"""
    app = mount()
    log = submit(app, "@ghost hello")
    assert any("ghost" in l for l in log.lines)
    assert app.query_one("#dock").value == ""         # 提交后清空


def test_tui_empty_at_message_no_crash():
    app = mount()
    log = submit(app, "@Prism")
    assert any("@ 了就得说事" in l for l in log.lines)


def test_tui_empty_input_noop():
    app = mount()
    before = len(lines(app))
    submit(app, "   ")
    assert len(lines(app)) == before              # 空输入不 echo, transcript 不增长


class FakeModel:
    def __init__(self, script): self.script = list(script); self.i = 0
    def chat_stream(self, m, tools=None):
        text, tcs = self.script[self.i]; self.i += 1
        if text: yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def test_tui_slash_model_switches():
    app = mount()
    submit(app, "/model glm-4.7")
    assert app.agent.model.model == "glm-4.7"


def test_tui_slash_thinking_off():
    app = mount()
    submit(app, "/thinking off")
    assert app.agent.thinking_level == "off"


def test_tui_python_exec_sets_namespace():
    app = mount()
    submit(app, "x = 42")
    assert app.agent.namespace.get("x") == 42


def test_tui_python_exec_error_shown():
    app = mount()
    log = submit(app, "1/0")
    assert any("ZeroDivisionError" in l for l in log.lines)


def test_tui_slash_unknown_command():
    app = mount()
    log = submit(app, "/nope")
    assert any("未知指令" in l for l in log.lines)


def test_tui_at_prism_runs_with_fake_model():
    app = mount()
    from prism.cognitive import NullIntuition
    app.agent.intuition = NullIntuition()   # 覆盖小模型直觉, 测试不连网调 glm-4.5-air
    app.agent.model = FakeModel([("prism-reply", [])])
    submit(app, "@Prism hi")
    for _ in range(100):
        time.sleep(0.05)
        if app.agent.last_result:
            break
    assert app.agent.last_result == "prism-reply"
