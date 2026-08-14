"""REQ-A 验收: bracketed paste —— 粘贴多行文本逐行提交回归。

固化 CHECKS [A1]-[A3]: VT 解析产单个 __paste__ key; App 派发粘贴进输入框不触发提交;
普通 enter 提交行为不回归。
"""
from prism.shell import PrismApp
from prism.tui.terminal import Key, _parse_vt


def test_a1_parse_vt_bracketed_paste():
    # [A1] \x1b[200~ ... \x1b[201~ 整段产出单个 __paste__, 段内 \r 不变 enter
    keys = _parse_vt(b"abc\x1b[200~line1\rline2\r\x1b[201~def")
    pastes = [k for k in keys if k.key == "__paste__"]
    assert len(pastes) == 1, [k.key for k in keys]
    assert "line1\rline2" in pastes[0].char, repr(pastes[0].char)
    enters = [k for k in keys if k.key == "enter"]
    assert len(enters) == 0, "paste newlines must not become enter keys"


def test_a2_dispatch_paste_inserts_without_submit():
    # [A2] 粘贴进输入框保留换行, 不触发 _input_submitted
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    calls = []
    app._input_submitted = lambda *a, **k: calls.append(1)
    app._dispatch_key(Key(key="__paste__", char="def foo():\n    return 42"))
    app._drain()
    assert "def foo():" in dock.value and "return 42" in dock.value, repr(dock.value)
    assert calls == [], calls


def test_a3_real_enter_still_submits():
    # [A3] 普通 enter 提交行为不得回归
    app = PrismApp()
    app.run(headless=True)
    dock = app.query_one("#dock")
    calls = []
    app._input_submitted = lambda *a, **k: calls.append(1)
    dock.value = "hi"
    dock.pos = 2
    dock.on_key(Key(key="enter", char=""))
    assert calls == [1], calls
