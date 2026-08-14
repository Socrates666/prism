"""固化 REQ-G7: 视觉渲染七连修(批判轮1/3 P1×7)验收合同 [VC1]-[VC8]。

对应修复:
  - prism/tui/app.py      主题灰阶阶梯 + border_muted 对比度 + _render_frame
                          画 CSS border + page_bg 全铺底 + _page_rgb()
  - prism/tui/widgets.py  Static 空内容 0 行 + 样式读 CSS color / Input 光标主题反相
                          / Footer spinner accent 不 dim + idle 键位提示
  - prism/shell.py        #current color $text + #status/#current 闲置归零 + 折射中去 markup

VC9(全测试套件绿)由 pytest 自身运行覆盖。
注意: markup._COLOR 是模块级全局, VC6 切 light 后必须 finally 还原 dark。
"""
import os
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")  # 仅过 OpenAI() 构造, 零网络

from prism.shell import PrismApp
from prism.tui import markup
from prism.tui.app import DARK, LIGHT
from prism.tui.widget import layout


def _app() -> PrismApp:
    app = PrismApp(); app.run(headless=True)
    app._drain()
    return app


def _screen(buf) -> str:
    return "\n".join("".join(c.ch for c in row) for row in buf.grid)


def _lum(c):
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# [VC1] 背景透传原生(用户裁决): 默认无显式色带处 bg=None; PRISM_PAGE_BG=paint 恢复全铺
def test_vc1_page_bg_native_passthrough(monkeypatch):
    monkeypatch.delenv("PRISM_PAGE_BG", raising=False)
    app = _app()
    buf = app._render_frame(24, 80)
    bgs = {c.style.bg for row in buf.grid for c in row}
    assert None in bgs, "默认应透传原生(bg=None 存在)"
    monkeypatch.setenv("PRISM_PAGE_BG", "paint")
    buf2 = app._render_frame(24, 80)
    none_bg = sum(1 for row in buf2.grid for c in row if c.style.bg is None)
    assert none_bg == 0, none_bg


# [VC2] 全帧零边框字符(用户裁决: pi 无边框含输入区), dock 有 ❯ 提示符且着色
def test_vc2_fully_borderless_input_prompt():
    from prism.tui.widget import layout as _layout
    app = _app()
    buf = app._render_frame(24, 80)
    screen = _screen(buf)
    assert "╭" not in screen and "╰" not in screen, "全帧应零边框字符(含输入区)"
    regions = _layout(app._widgets, app._style_for, 24, 80)
    idx = {(w.id or "").lstrip("#"): regions[i] for i, w in enumerate(app._widgets)}
    dx, dy, dw, dh = idx["dock"]
    pcells = [c for row in buf.grid[dy:dy + dh] for c in row[dx:dx + dw]
              if not c.cont and c.ch == "❯"]
    assert pcells, "输入区应有 ❯ 提示符"
    assert all(isinstance(c.style.fg, tuple) for c in pcells), "❯ 未着色"


# [VC3] 闲置空行归零(#current/#status 空=0 行), status 有内容时按需占 1 行
def test_vc3_idle_rows_collapse_status_on_demand():
    app = _app()
    regions = layout(app._widgets, app._style_for, 24, 80)
    idx = {(w.id or "").lstrip("#"): regions[i] for i, w in enumerate(app._widgets)}
    assert idx["current"][3] == 0, idx["current"]
    assert idx["status"][3] == 0, idx["status"]
    app.query_one("#status").update("◇ 折射中")
    app._drain()
    regions2 = layout(app._widgets, app._style_for, 24, 80)
    idx2 = {(w.id or "").lstrip("#"): regions2[i] for i, w in enumerate(app._widgets)}
    assert idx2["status"][3] == 1, idx2["status"]
    assert idx2["transcript"][3] >= 1, idx2["transcript"]


# [VC4] 流式区用正文本色($text)且非斜体(不再被画成思考样式)
def test_vc4_streaming_text_uses_text_style():
    app = _app()
    cur = app.query_one("#current")
    cur.update("流式回答正文样例")
    app._drain()
    buf = app._render_frame(24, 80)
    cells = [c for row in buf.grid for c in row if c.ch == "流"]
    assert cells, "content not rendered"
    c0 = cells[0]
    assert c0.style.fg == (212, 212, 212), c0.style.fg
    assert not c0.style.italic, "streaming text still italic"


# [VC5] 灰阶两两分离(muted/thinking_text/tool_output), border_muted 对 page ≥3:1
def test_vc5_gray_ladder_and_border_contrast():
    for T in (DARK, LIGHT):
        trio = [T["muted"].fg, T["thinking_text"].fg, T["tool_output"].fg]
        assert len(set(trio)) == 3, trio
        ct = _contrast(T["border_muted"].fg, T["page_bg"].fg)
        assert ct >= 3.0, ct


# [VC6] 光标主题化: 浅色下不再出现硬编码 (220,220,220) 反相底
def test_vc6_cursor_themed_no_hardcoded_bg():
    try:
        app = _app()
        app.theme = "light"
        dock = app.query_one("#dock")
        dock.value = "ab"; dock.pos = 1
        app._drain()
        buf = app._render_frame(24, 80)
        bgs = {c.style.bg for row in buf.grid for c in row}
        assert (220, 220, 220) not in bgs, "hardcoded cursor bg remains"
    finally:
        markup.set_color_theme("dark")


# [VC7] busy 可见指示: Footer spinner 已随底栏移除, 由 #status 折射中... 承担(真实 emit 路径)
def test_vc7_spinner_not_dim_and_colored():
    app = _app()
    app.agent.hooks["emit"]({"type": "agent_start"})
    app._drain()
    buf = app._render_frame(24, 80)
    assert "折射中" in _screen(buf), "busy 应有折射中可见指示"
    app.agent.hooks["emit"]({"type": "agent_end"})
    app._drain()


# [VC8] footer idle 键位提示(/help 帮助 · esc 中断 · ctrl+j 换行)
def test_vc8_footer_idle_keymap_hint():
    # 输入区无键位/路由提示(用户裁决 2026-08-14: 只留 ❯); 横幅的 /help 指针不在此列,
    # 引导由 /help 与报错态(B3)承担
    from prism.tui.widget import layout as _layout
    app = _app()
    buf = app._render_frame(24, 80)
    regions = _layout(app._widgets, app._style_for, 24, 80)
    idx = {(w.id or "").lstrip("#"): regions[i] for i, w in enumerate(app._widgets)}
    dx, dy, dw, dh = idx["dock"]
    dock_screen = "\n".join("".join(c.ch for c in row[dx:dx + dw]) for row in buf.grid[dy:dy + dh])
    assert "❯" in dock_screen, "❯ 提示符缺失"
    assert "/help" not in dock_screen and "帮助" not in dock_screen \
        and "问事" not in dock_screen, "输入区不应有提示残留"
