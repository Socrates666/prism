"""固化 REQ-C: 流式回复区 #current 高度钳制(max-height)验收合同 C1-C3。

对应修复:
  - prism/tui/css.py      ComputedStyle.max_height + parse max-height
  - prism/tui/widget.py   layout() auto 分支 clamp max-height
  - prism/tui/widgets.py  Static.draw 贴底(画末尾 h 行)
  - prism/shell.py        #current { max-height: 6 }

C4(全测试套件绿)由 pytest 自身运行覆盖。
"""
import os
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")  # 仅过 OpenAI() 构造, 零网络

from prism.shell import PrismApp
from prism.tui.widget import layout


def _regions(app, rows=24, cols=80):
    regions = layout(app._widgets, app._style_for, rows, cols)
    return {(w.id or "").lstrip("#"): regions[i] for i, w in enumerate(app._widgets)}


def _screen(app, rows=24, cols=80):
    buf = app._render_frame(rows, cols)
    return "\n".join("".join(c.ch for c in row) for row in buf.grid)


# [C1] 长流式: #current 高度被钳制, transcript 不被挤没, dock/footer 不出屏, 末行可见
def test_c1_long_streaming_clamped_and_tail_visible():
    app = PrismApp(); app.run(headless=True)
    cur = app.query_one("#current")
    cur.update("\n".join("L%02d " % i + "x" * 70 for i in range(60)))
    app._drain()
    buf = app._render_frame(24, 80)
    idx = _regions(app)
    assert idx["current"][3] <= 8, idx["current"]
    assert idx["transcript"][3] >= 1, idx["transcript"]
    assert idx["dock"][1] + idx["dock"][3] <= 24, idx["dock"]
    assert idx["footer"][1] + idx["footer"][3] <= 24, idx["footer"]
    screen = "\n".join("".join(c.ch for c in row) for row in buf.grid)
    assert "L59" in screen, "streaming tail not visible"


# [C2] 短内容: auto 语义保留, 不裁剪, 全部行可见
def test_c2_short_content_not_truncated():
    app = PrismApp(); app.run(headless=True)
    cur = app.query_one("#current")
    cur.update("\n".join("S%d" % i for i in range(4)))
    app._drain()
    idx = _regions(app)
    assert idx["current"][3] == 4, idx["current"]
    screen = _screen(app)
    for i in range(4):
        assert ("S%d" % i) in screen, "short content truncated: S%d" % i


# [C3] 空内容闲置态: dock/footer 不出屏(无回归)
def test_c3_idle_no_regression():
    app = PrismApp(); app.run(headless=True)
    app._drain()
    app._render_frame(24, 80)
    idx = _regions(app)
    assert idx["dock"][1] + idx["dock"][3] <= 24, idx["dock"]
    assert idx["footer"][1] + idx["footer"][3] <= 24, idx["footer"]
