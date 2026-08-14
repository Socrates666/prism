"""固化 REQ-F: 模型输出代码块围栏吞噬 + 背景块视觉区隔(验收合同 F1-F3)。

对应修复:
  - prism/tui/widgets.py  RichLog.write 按 ``` 围栏行拆段: 围栏行不渲染, 代码段走
    _BlockUnit 背景块 + nowrap(不折行); 未闭合围栏半块稳态渲染; 状态跨 write 续块
  - prism/shell.py         flush_current / message_end / 子agent flush 对模型输出
    转义 [ (防 arr[0] 被 markup 当数字色标签吞掉)
  - prism/tui/app.py       新增 code_bg token(dark/light)

F4(全测试套件绿)由 pytest 自身运行覆盖。
"""
import os
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")  # 仅过 OpenAI() 构造, 零网络

from prism.shell import PrismApp
from prism.tui.app import DARK


def _emit(app, *events):
    emit = app.agent.hooks["emit"]
    for e in events:
        emit(e)
    app._drain()


def _frame(app, rows=40, cols=100):
    buf = app._render_frame(rows, cols)
    return "\n".join("".join(c.ch for c in row) for row in buf.grid), buf


# [F1] 围栏不泄漏上屏, 代码体与围栏前后正文都可见
def test_f1_fence_swallowed_code_and_prose_visible():
    app = PrismApp(); app.run(headless=True)
    _emit(app,
        {"type": "agent_start"},
        {"type": "message_update",
         "delta": "这是代码：\n```python\ndef foo():\n    return 42\n```\n完毕"},
        {"type": "message_end"})
    screen, _ = _frame(app)
    assert "```" not in screen, "fence leaked on screen"
    assert "def foo():" in screen, "code body missing"
    assert "return 42" in screen, "code return missing"
    assert "完毕" in screen, "prose after block missing"


# [F2] 代码行有背景块, 正文行没有(视觉区隔成立)
def test_f2_code_line_has_bg_prose_does_not():
    app = PrismApp(); app.run(headless=True)
    _emit(app,
        {"type": "agent_start"},
        {"type": "message_update",
         "delta": "说明文字在这里\n```python\ndef foo():\n    return 42\n```"},
        {"type": "message_end"})
    _, buf = _frame(app)
    code_row = plain_row = None
    for y, row in enumerate(buf.grid):
        line = "".join(c.ch for c in row)
        if "def foo():" in line and code_row is None:
            code_row = y
        if "说明文字" in line and plain_row is None:
            plain_row = y
    assert code_row is not None, "code row not found"
    assert plain_row is not None, "prose row not found"
    cbg = {buf.grid[code_row][x].style.bg for x in range(4, 60)}
    assert cbg != {DARK["page_bg"].fg}, "code line has no bg block"
    pbg = {buf.grid[plain_row][x].style.bg for x in range(4, 60)}
    # 背景透传原生(用户裁决): 正文行底色=None, 但不得带代码块 bg
    assert pbg == {None}, "prose line unexpectedly has block bg"


# [F3] 无围栏纯文本的 [ 不被吞; 未闭合围栏稳态(代码体可见, 围栏标记不泄漏)
def test_f3_plain_bracket_and_unclosed_fence_stable():
    app = PrismApp(); app.run(headless=True)
    _emit(app,
        {"type": "agent_start"},
        {"type": "message_update", "delta": "普通回答没有围栏 arr[0] 也没问题"},
        {"type": "message_end"},
        {"type": "agent_start"},
        {"type": "message_update", "delta": "未闭合围栏：\n```js\nlet x = 1;"},
        {"type": "message_end"})
    screen, _ = _frame(app)
    assert "普通回答" in screen
    assert "arr[0]" in screen, "bracket in plain stream swallowed"
    assert "let x = 1;" in screen, "unclosed fence body missing"
    assert "```" not in screen, "unclosed fence marker leaked"
