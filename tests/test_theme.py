"""REQ-D 验收: 输入框边框去 DeepPink + 浅色主题 markup 语义色可读。

固化 CHECKS [D1]-[D3]:
  [D1] 渲染帧不含 DeepPink(255,20,147) / 浅色玫红(214,51,132)。
  [D2] light 主题下 yellow/cyan/green markup 对白底对比度 ≥3:1(WCAG)。
  [D3] dark 主题下 yellow/cyan/green markup 照常着色(fg 为元组)。

注意: markup._COLOR 是模块级全局, 切 light 会污染同进程后续测试
(test_self_tui / test_tui_blackbox_stress 断言 dark cyan=(0,215,255)),
故每个用例 try/finally 还原 dark。
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")

from prism.shell import PrismApp
from prism.tui import markup


def _lum(c):
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _find_fg(buf, chars):
    """取 chars 中每个字的首个着色单元格 fg。

    注意: 跳过宽字符的续占位 cell(cont=True, ch='')—— 其 ch='' 在 Python 里
    满足 ``'' in '黄青绿'`` == True, 会让原版 CHECK 的 ``len(found)==3`` 误判为 4。
    这是 buffer.py 的全宽续位机制(超出本验收可改范围), 与主题修复无关。
    """
    found = {}
    for row in buf.grid:
        for c in row:
            if c.cont or not c.ch:
                continue
            if c.ch in chars and isinstance(c.style.fg, tuple) and c.ch not in found:
                found[c.ch] = c.style.fg
    return found


def test_d1_border_pink_default(monkeypatch):
    # [D1] 用户裁决(2026-08-14): 聚焦边框默认回归 DeepPink(pi-faithful); accent 为退出口
    try:
        monkeypatch.delenv("PRISM_INPUT_BORDER", raising=False)
        app = PrismApp(); app.run(headless=True)
        app._drain()
        buf = app._render_frame(24, 80)
        fgs = {c.style.fg for row in buf.grid for c in row if not c.cont}
        assert (255, 20, 147) in fgs, "默认应渲染 DeepPink 聚焦边框"
        assert (214, 51, 132) not in fgs, "浅色玫红不应出现在 dark 主题帧"
        monkeypatch.setenv("PRISM_INPUT_BORDER", "accent")
        buf2 = app._render_frame(24, 80)
        fgs2 = {c.style.fg for row in buf2.grid for c in row if not c.cont}
        assert (255, 20, 147) not in fgs2, "accent 模式不应有粉"
    finally:
        markup.set_color_theme("dark")


def test_d2_light_markup_contrast():
    # [D2] light 主题下 markup 三色对白底 ≥3:1
    try:
        app = PrismApp(); app.run(headless=True)
        app.theme = "light"
        app._drain()
        log = app.query_one("#transcript")
        log.write("[yellow]黄测[/yellow][cyan]青测[/cyan][green]绿测[/green]")
        app._drain()
        buf = app._render_frame(24, 80)
        found = _find_fg(buf, "黄青绿")
        assert len(found) == 3, found
        white = (255, 255, 255)
        for ch, fg in found.items():
            ct = _contrast(fg, white)
            assert ct >= 3.0, (ch, fg, ct)
    finally:
        markup.set_color_theme("dark")


def test_d3_dark_markup_still_colored():
    # [D3] dark 主题下 markup 三色照常着色(fg 元组, 暗色基色)
    try:
        app = PrismApp(); app.run(headless=True)
        app._drain()
        log = app.query_one("#transcript")
        log.write("[yellow]黄测[/yellow][cyan]青测[/cyan][green]绿测[/green]")
        app._drain()
        buf = app._render_frame(24, 80)
        found = _find_fg(buf, "黄青绿")
        assert len(found) == 3, found
        # dark 基色固定值(回归锚点, 防 light 覆盖意外泄漏)
        assert found["黄"] == (255, 255, 0)
        assert found["青"] == (0, 215, 255)
        assert found["绿"] == (181, 189, 104)
    finally:
        markup.set_color_theme("dark")
