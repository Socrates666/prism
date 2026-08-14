"""思考块单标签验收(用户裁决 2026-08-14: 一次思考只要一个标签)。

固化:
  [T1] 连续 thinking 行(流式逐行 flush 场景)只有首行带[思考]标签, 续行无标签缩进
  [T2] 其他输出(消息/用户/工具)打断后, 新思考重新带标签
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("PRISM_INTUITION", "off")

from prism.shell import PrismApp


def _log():
    app = PrismApp(); app.run(headless=True)
    return app, app.query_one("#transcript")


def _plain_lines(log):
    # entries 里思考行的渲染文本(去 markup)
    from prism.tui.markup import strip_markup
    return [strip_markup(p) for k, p in log.entries if k == "line"]


def test_t1_one_label_per_thinking_block():
    _, log = _log()
    log.thinking("第一行推理")            # 流式: 每次 flush 一行
    log.thinking("第二行推理")
    log.thinking("第三行推理")
    lines = _plain_lines(log)
    labeled = [ln for ln in lines if ln.startswith("思考")]
    cont = [ln for ln in lines if "推理" in ln and not ln.startswith("思考")]
    assert len(labeled) == 1, lines
    assert len(cont) == 2, lines
    assert all(ln.startswith("  ") for ln in cont), "续行应缩进"


def test_t2_interruption_relabels():
    _, log = _log()
    log.thinking("推理A")
    log.write("模型回答")                 # 打断(消息)
    log.thinking("推理B")
    lines = _plain_lines(log)
    labeled = [ln for ln in lines if ln.startswith("思考")]
    assert len(labeled) == 2, lines
