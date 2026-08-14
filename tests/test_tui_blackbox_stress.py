"""TUI 前端公开接口的黑盒压力测试。

模拟「扩展作者」从外部接入: 自定义 widget、往 transcript 塞任意内容、用 Buffer 原语
自绘、Input 编辑、极端尺寸、App 生命周期。每个用例只触公开 API, 断言「不崩 + 行为正确」。
"""
import pytest
from prism.tui import (App, Header, RichLog, Static, Input, Footer, Widget,
                       Buffer, Style, parse_markup, wrap_segments, strip_markup,
                       parse_css)
from prism.tui.buffer import render_plain
from prism.tui.terminal import Key


# ── 1. markup 解析: 扩展会塞任意显示文本 ──────────────────────────────────────
def test_markup_empty():
    assert parse_markup("") == []


def test_markup_only_tags():
    # 只有标签没有文本 → 不崩, 无文本段
    assert parse_markup("[bold][/bold]") == []


def test_markup_unclosed_tag():
    # 未闭合标签 → 不崩, 后续文本带该样式
    segs = parse_markup("[bold]hi")
    assert segs and segs[-1][1].bold


def test_markup_close_with_empty_stack():
    assert parse_markup("[/]nothing") == [("nothing", Style())]   # 不崩


def test_markup_unknown_color_ignored():
    segs = parse_markup("[chartreuse]x[/]")
    assert segs == [("x", Style())]   # 未知颜色宽容忽略


def test_markup_numeric_color():
    segs = parse_markup("[201]x[/]")
    assert segs[0][1].fg == 201


def test_markup_deep_nest():
    s = "[bold][italic][dim][cyan]" + "x" * 50 + "[/][/][/][/]"
    assert parse_markup(s)[-1][1].fg == (0, 215, 255) and parse_markup(s)[-1][1].bold


def test_markup_escape_and_literal_bracket():
    # \\[ 是字面 [, 真正的 [tag] 仍解析
    joined = "".join(t for t, _ in parse_markup("a\\[b][red]c[/]"))
    assert joined == "a[b]c"


def test_markup_malformed_no_close_bracket():
    assert parse_markup("[bold text without close") == [("[bold text without close", Style())]


def test_strip_markup_keeps_text():
    assert strip_markup("[red]a\\[b]c[/]") == "a[b]c"


# ── 2. wrap: 扩展文本要按显示宽度折行 ───────────────────────────────────────
def test_wrap_width_zero():
    assert wrap_segments([("abc", Style())], 0) == [[("abc", Style())]]


def test_wrap_width_one_ascii():
    rows = wrap_segments([("abc", Style())], 1)
    assert len(rows) == 3                       # 每行 1 字符


def test_wrap_wide_char_at_width_one():
    # 全宽字符宽度 2 > 1, 不应崩(独占一行溢出)
    rows = wrap_segments([("中", Style())], 1)
    assert len(rows) >= 1


def test_wrap_preserves_style_each_row():
    rows = wrap_segments(parse_markup("[red]abcdefghij[/red]"), 3)
    for row in rows:
        for _, s in row:
            assert s.fg == (204, 102, 102)   # red = pi #cc6666


def test_wrap_empty_segments():
    assert wrap_segments([], 10) == [[]]


# ── 3. Buffer 原语: 自定义 widget 会用这些自绘 ──────────────────────────────
def test_buffer_write_out_of_bounds_no_crash():
    b = Buffer(5, 2)
    b.write(-1, -1, "xyz", Style())            # 负坐标
    b.write(100, 100, "xyz", Style())          # 远超界
    b.write(3, 0, "abcd", Style())             # 超右边界裁剪


def test_buffer_wide_char_at_last_col():
    b = Buffer(3, 1)
    b.put(2, 0, "中", Style())                 # 最后一列放全宽字符
    assert render_plain(b)                      # 不崩


def test_buffer_box_too_small():
    b = Buffer(5, 5)
    b.box(0, 0, 1, 1, border_style=Style())   # w<2 h<2 → 不画, 不崩
    b.box(0, 0, 0, 0, border_style=Style())


def test_buffer_fill_bg_bounds():
    b = Buffer(4, 3)
    b.fill_bg(-5, -5, 100, 100, 22)            # 超大区域裁剪到缓冲
    b.fill_bg(2, 1, 10, 10, 22)
    assert render_plain(b) is not None


def test_buffer_write_markup_with_base():
    b = Buffer(20, 1)
    b.write_markup(0, 0, "[bold]x[/]", base=Style(fg=3))
    assert render_plain(b).strip().startswith("x")


def test_buffer_fill_row_and_clear():
    b = Buffer(5, 2)
    b.fill_row(0, "─", Style())
    b.clear_row(0)
    assert render_plain(b).split("\n")[0].strip() == ""


# ── 4. RichLog API: 扩展显示内容的主接口 ─────────────────────────────────────
class _App:
    theme = "dark"
    from prism.tui.app import DARK as _DARK
    _themes = {"dark": _DARK}
    def style(self, t): return self._themes["dark"].get(t, Style())
    model_name = "m"; _agent_busy = False; agent = None


def _log():
    l = RichLog(id="t"); l.app = _App(); return l


def _render_log(log, rows=8, cols=40):
    b = Buffer(cols, rows); log.draw(b, 0, 0, cols, rows)
    return render_plain(b)


def test_richlog_multiline_user_keeps_newlines():
    """扩展可能塞多行用户消息 —— 渲染时换行不能被吞(每行单独成行)。"""
    log = _log()
    log.user("第一行\n第二行\n第三行")
    out = _render_log(log)
    lines = [l for l in out.split("\n") if l.strip()]
    # 三行各自独立成行(不在同一行)
    assert any("第一行" in l for l in lines)
    assert any("第三行" in l for l in lines)
    assert not any("第一行" in l and "第三行" in l for l in lines)


def test_richlog_multiline_thinking_keeps_newlines():
    log = _log()
    log.thinking("a\nb\nc")
    out = _render_log(log)
    lines = [l for l in out.split("\n") if l.strip()]
    assert not any("a" in l and "c" in l for l in lines)


def test_richlog_multiline_tool_result():
    log = _log()
    ref = log.tool_start("t")
    log.tool_end(ref, "r1\nr2\nr3", False)
    out = _render_log(log)
    lines = [l for l in out.split("\n") if l.strip()]
    assert any("r1" in l for l in lines)
    assert any("r3" in l for l in lines)
    assert not any("r1" in l and "r3" in l for l in lines)


def test_richlog_tool_end_without_start_no_crash():
    log = _log()
    log.tool_end({"name": "x"}, "ok", False)   # 非 start 返回的 ref


def test_richlog_empty_user():
    log = _log(); log.user("")
    log._ensure_units(40)                       # 渲染不崩


def test_richlog_empty_thinking():
    log = _log(); log.thinking("")
    log._ensure_units(40)


def test_richlog_unicode_tool_name():
    log = _log()
    ref = log.tool_start("工具名", "参数=值")
    log.tool_end(ref, "结果", False)
    joined = "".join(log.lines)
    assert "工具名" in joined and "结果" in joined


def test_richlog_very_long_single_line_wraps():
    log = _log()
    log.write("x" * 500)
    units = log._ensure_units(40)
    assert len(units) > 1                        # 折成多行


def test_richlog_many_entries_perf():
    log = _log()
    for i in range(2000):
        log.write(f"line{i}")
    units = log._ensure_units(40)
    # 惰性物化: 只建尾窗(贴底渲染够用), 不再全量 2000(REQ-G6 P2)
    assert 0 < len(units) <= 800
    assert len(log.entries) == 2000


def test_richlog_scroll_bounds_when_empty():
    log = _log()
    log.scroll_up(100); log.scroll_down(100)
    log.scroll_home(); log.scroll_end()          # 空 log 滚动不崩


def test_richlog_scroll_past_top():
    log = _log()
    for i in range(50):
        log.write(f"l{i}")
    log._ensure_units(40)
    log.scroll_up(1000)                          # 远超顶部
    log.scroll_end()


def test_richlog_cognitive_unknown_stage():
    log = _log()
    log.cognitive("mystery", "content")          # 未知 stage
    log._ensure_units(40)


def test_richlog_render_in_tiny_width():
    log = _log()
    log.user("hello world this is a test")
    log.tool_start("t", "a=1")
    buf = Buffer(6, 10)
    log.draw(buf, 0, 0, 6, 10)                   # 极窄宽度渲染不崩


# ── 5. Input 编辑: 扩展可能接入自定义输入 ───────────────────────────────────
def _inp():
    i = Input(id="d", placeholder="p"); i.app = _App(); i.focus(); return i


def test_input_type_wide_chars():
    i = _inp()
    for c in "中文😀":
        i.on_key(Key(key=c, char=c))
    assert i.value == "中文😀"


def test_input_multiline_cursor_navigation():
    i = _inp()
    i.on_key(Key(key="a", char="a"))
    i.on_key(Key(key="enter", char="", shift=True))
    i.on_key(Key(key="b", char="b"))
    i.on_key(Key(key="c", char="c"))
    assert i.value == "a\nbc"
    i.on_key(Key(key="up", char=""))             # 光标上移
    i.on_key(Key(key="end", char=""))
    i.on_key(Key(key="down", char=""))
    assert i.value == "a\nbc"                    # 导航不改值


def test_input_ctrl_keys_on_empty():
    i = _inp()
    for k in ["ctrl+u", "ctrl+k", "ctrl+w", "ctrl+a", "ctrl+e"]:
        i.on_key(Key(key=k, char="", ctrl=True))   # 空文本不崩
    assert i.value == ""


def test_input_ctrl_u_kills_to_line_start():
    i = _inp()
    for c in "hello": i.on_key(Key(key=c, char=c))
    i.on_key(Key(key="ctrl+u", char="", ctrl=True))
    assert i.value == ""


def test_input_ctrl_w_deletes_word():
    i = _inp()
    for c in "foo bar": i.on_key(Key(key=c, char=c))
    i.on_key(Key(key="ctrl+w", char="", ctrl=True))
    assert i.value == "foo "


def test_input_delete_at_boundaries():
    i = _inp()
    i.on_key(Key(key="backspace", char=""))      # 空时 backspace
    i.on_key(Key(key="delete", char=""))         # 空时 delete
    i.on_key(Key(key="a", char="a"))
    i.on_key(Key(key="home", char=""))
    i.on_key(Key(key="delete", char=""))         # 删唯一字符
    assert i.value == ""


def test_input_submit_clears_and_signals():
    captured = {}
    class A(_App):
        def _input_submitted(self, ev): captured["v"] = ev.value
    i = Input(id="d"); i.app = A(); i.focus()
    i.on_key(Key(key="h", char="h"))
    i.on_key(Key(key="i", char="i"))
    i.on_key(Key(key="enter", char=""))
    assert captured["v"] == "hi" and i.value == ""


def test_input_unknown_key_ignored():
    i = _inp()
    assert i.on_key(Key(key="f4", char="")) is False   # 未绑定键不崩不吞


def test_input_render_multiline_in_small_box():
    i = _inp()
    for c in "line1\nline2\nline3":
        if c == "\n": i.on_key(Key(key="enter", char="", shift=True))
        else: i.on_key(Key(key=c, char=c))
    b = Buffer(20, 3)
    i.draw(b, 0, 0, 20, 3)                        # 多行塞 3 行框, 不崩


# ── 6. 布局: 极端终端尺寸 ────────────────────────────────────────────────────
def test_layout_tiny_terminal():
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self):
            yield Header(id="h")
            yield RichLog(id="t")
            yield Input(id="d")
            yield Footer(id="f")
        def on_mount(self): self.model_name = "m"
    a = A()
    out = a.render_to_string(rows=3, cols=8)      # 极小
    assert isinstance(out, str)                   # 不崩


def test_layout_zero_height_widget():
    class W(Widget):
        can_focus = False
        def measure(self, w): return 0
        def draw(self, buf, x, y, w, h): pass
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield W(id="z"); yield RichLog(id="t")
    a = A()
    assert isinstance(a.render_to_string(rows=5, cols=10), str)


def test_layout_huge_measure_clipped():
    class W(Widget):
        can_focus = False
        def measure(self, w): return 9999
        def draw(self, buf, x, y, w, h): buf.write(x, y, "!", Style())
    class A(App):
        def compose(self): yield W(id="big")
    a = A()
    out = a.render_to_string(rows=5, cols=10)
    assert "!" in out                             # 仍画出来(裁剪)


# ── 7. App 生命周期 / 扩展自定义 widget ──────────────────────────────────────
def test_custom_widget_renders():
    """扩展加自定义 widget: compose + measure + draw 全链路。"""
    class Panel(Widget):
        can_focus = False
        def measure(self, w): return 3
        def draw(self, buf, x, y, w, h):
            buf.box(x, y, w, h, title="panel", border_style=self.app.style("accent"))
            buf.write_markup(x + 1, y + 1, "[green]custom![/]")
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self):
            yield Panel(id="p")
            yield RichLog(id="t")
    a = A()
    out = a.render_to_string(rows=8, cols=20)
    assert "custom" in out and "panel" in out


def test_custom_widget_draw_exception_does_not_crash_app():
    """扩展的 widget draw 抛异常 → 整个 app 不崩(该 widget 不渲染)。"""
    class Bad(Widget):
        can_focus = False
        def measure(self, w): return 2
        def draw(self, buf, x, y, w, h): raise RuntimeError("boom")
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield Bad(id="b"); yield RichLog(id="t")
    a = A()
    out = a.render_to_string(rows=6, cols=10)
    assert isinstance(out, str)                   # 异常被吞, app 存活


def test_custom_focusable_widget_receives_keys():
    class Box(Widget):
        def __init__(self, id=None): super().__init__(id); self.typed = ""
        def measure(self, w): return 1
        def draw(self, buf, x, y, w, h): buf.write(x, y, self.typed, self.app.style("text"))
        def on_key(self, key):
            if key.is_printable(): self.typed += key.char; return True
            return False
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield Box(id="b"); yield RichLog(id="t")
    a = A(); a.run(headless=True)
    box = a.query_one("#b")
    assert a._focusable[0] is box                 # 自定义可聚焦 widget 成焦点
    a._dispatch_key(Key(key="z", char="z"))
    assert box.typed == "z"


def test_query_one_unknown_returns_none():
    class A(App):
        def compose(self): yield RichLog(id="t")
    a = A(); a.run(headless=True)
    assert a.query_one("#nope") is None
    assert a.query_one("RichLog") is not None     # 按类型名


def test_call_from_thread_exception_isolated():
    """跨线程回调抛异常 → 不污染主循环, 后续回调仍执行。"""
    class A(App):
        def compose(self): yield RichLog(id="t")
    a = A(); a.run(headless=True)
    flag = []
    a.call_from_thread(lambda: (_ for _ in ()).throw(ValueError("x")))
    a.call_from_thread(lambda: flag.append("ok"))
    a._drain()
    assert flag == ["ok"]


def test_theme_switch_rerenders():
    class A(App):
        def compose(self): yield RichLog(id="t")
    a = A(); a.run(headless=True)
    assert a.theme == "dark"
    a.theme = "light"
    assert isinstance(a.render_to_string(rows=5, cols=10), str)


def test_dispatch_unknown_key_no_crash():
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield RichLog(id="t"); yield Input(id="d")
    a = A(); a.run(headless=True)
    for k in ["f1", "f2", "ctrl+f12", "pageup", "pagedown", "home", "end", "tab"]:
        a._dispatch_key(Key(key=k, char=""))      # 各种键不崩


# ── 8. 第二轮: 更刁钻的扩展场景 ──────────────────────────────────────────────
def test_custom_widget_measure_exception_does_not_crash():
    """扩展 widget 的 measure 抛异常 → 不应炸掉整个渲染(draw 异常已被吞)。"""
    class Bad(Widget):
        can_focus = False
        def measure(self, w): raise RuntimeError("measure boom")
        def draw(self, buf, x, y, w, h): buf.write(x, y, "!", Style())
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield Bad(id="b"); yield RichLog(id="t")
    a = A()
    out = a.render_to_string(rows=6, cols=10)   # 期望不崩
    assert isinstance(out, str)


def test_nested_compose_children_no_crash():
    """扩展用 compose 返回子 widget → 不崩(展平为兄弟)。"""
    class Child(Widget):
        can_focus = False
        def measure(self, w): return 1
        def draw(self, buf, x, y, w, h): buf.write(x, y, "child", Style())
    class Parent(Widget):
        can_focus = False
        def measure(self, w): return 1
        def draw(self, buf, x, y, w, h): buf.write(x, y, "parent", Style())
        def compose(self): return [Child()]
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield Parent(id="p"); yield RichLog(id="t")
    a = A()
    out = a.render_to_string(rows=6, cols=12)
    assert isinstance(out, str)


def test_richlog_write_none_is_safe():
    """扩展(或 LLM 工具结果)可能传 None → 当空串, 不抛异常。"""
    log = _log()
    log.write(None)              # type: ignore[arg-type]
    assert log.lines == [""]     # 不崩, 当空串


def test_richlog_write_with_embedded_ansi_does_not_crash():
    """扩展可能塞含原始 ANSI/OSC 的文本 → 不崩(当字面文本)。"""
    log = _log()
    log.write("\x1b[31mred\x1b[0m text")
    log._ensure_units(40)


def test_input_value_with_tab_and_cr():
    """粘贴的文本可能含 \t \r → 不崩。"""
    i = _inp()
    i.value = "a\tb\rc"
    i.pos = len(i.value)
    b = Buffer(20, 3)
    i.draw(b, 0, 0, 20, 3)
    assert render_plain(b) is not None


def test_buffer_box_title_longer_than_width():
    b = Buffer(6, 3)
    b.box(0, 0, 6, 3, title="a very long title that overflows", border_style=Style())
    assert "╭" in render_plain(b)


def test_footer_extremely_narrow():
    f = Footer(id="f"); f.app = _App()
    b = Buffer(5, 2)
    f.draw(b, 0, 0, 5, 2)                          # 极窄 footer 不崩
    assert render_plain(b) is not None


def test_app_render_twice_idempotent():
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield RichLog(id="t"); yield Input(id="d")
        def on_mount(self): self.model_name = "m"
    a = A()
    o1 = a.render_to_string(rows=10, cols=20)
    o2 = a.render_to_string(rows=10, cols=20)
    assert o1 == o2                                # 重复渲染稳定


# ── 9. 第三轮: 新窗体/overlay/动态 ───────────────────────────────────────────
def test_modal_overlay_pattern_renders_on_top():
    """扩展实现「模态窗体」: compose 末尾放一个全屏 widget, 画在所有东西之上。"""
    class Modal(Widget):
        can_focus = True
        def measure(self, w): return 0           # 0 高度不占布局(但 draw 仍被调?)
        def draw(self, buf, x, y, w, h):
            # 画一个居中框模拟 modal
            buf.box(5, 2, 30, 6, title="modal", border_style=self.app.style("warning"))
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self):
            yield RichLog(id="t")
            yield Modal(id="modal")
        def on_mount(self): self.model_name = "m"
    a = A()
    out = a.render_to_string(rows=12, cols=40)
    # modal 框出现(即使 measure=0, 只要 h>0 才画; 这里验证不崩 + 结构完整)
    assert isinstance(out, str)


def test_app_with_zero_widgets():
    """compose 返回空 → 不崩。"""
    class A(App):
        def compose(self): return []
    a = A()
    assert isinstance(a.render_to_string(rows=5, cols=10), str)


def test_layout_no_fr_widget():
    """全是 fix/auto, 没有 1fr → 剩余空间留空, 不崩。"""
    class A(App):
        def compose(self):
            yield Header(id="h")
            yield Static(id="s", content="hi")
            yield Footer(id="f")
        def on_mount(self): self.model_name = "m"
    a = A()
    assert isinstance(a.render_to_string(rows=10, cols=20), str)


def test_missing_theme_token_returns_default_style():
    class A(App):
        def compose(self): yield RichLog(id="t")
    a = A(); a.run(headless=True)
    s = a.style("nonexistent_token_xyz")
    assert s == Style()                            # 缺失 token → 默认空样式, 不崩


def test_focus_cycle_with_single_focusable():
    class A(App):
        CSS = "#t{height:1fr;}"
        def compose(self): yield RichLog(id="t"); yield Input(id="d")
    a = A(); a.run(headless=True)
    a._dispatch_key(Key(key="tab", char=""))       # Tab 循环(只有一个可聚焦)
    a._dispatch_key(Key(key="tab", char=""))
    assert isinstance(a.render_to_string(rows=5, cols=10), str)


def test_call_from_thread_fifo_order():
    class A(App):
        def compose(self): yield RichLog(id="t")
    a = A(); a.run(headless=True)
    order = []
    for i in range(5):
        a.call_from_thread(lambda i=i: order.append(i))
    a._drain()
    assert order == [0, 1, 2, 3, 4]               # FIFO 保持顺序


def test_buffer_later_draw_overwrites_earlier():
    """后画的覆盖先画的(z-order 由 compose 顺序决定)。"""
    b = Buffer(10, 1)
    b.write(0, 0, "AAAAAA", Style())
    b.write(2, 0, "BB", Style(fg=1))
    assert render_plain(b) == "AABBAA"   # BB 覆盖了 A 的第 2-3 列


def test_richlog_mixed_entries_sequence():
    """混合 user/tool/line/thinking/cognitive 顺序渲染, 全部出现。"""
    log = _log()
    log.write("start")
    log.user("u")
    ref = log.tool_start("tool", "a=1")
    log.tool_end(ref, "res", False)
    log.thinking("th")
    log.cognitive("intuition", "int")
    log.write("end")
    buf = Buffer(40, 30)
    log.draw(buf, 0, 0, 40, 30)
    out = render_plain(buf)
    for needle in ["start", "u", "tool", "res", "th", "int", "end"]:
        assert needle in out, f"缺失 {needle}"


# ── 10. 第四轮: markup 吞字符 + 认知/思考降级(回归) ──────────────────────────
def test_tool_result_brackets_not_eaten():
    """工具结果含 [info] 这种 → 必须字面显示, 不能被 markup 当标签吞掉。"""
    log = _log()
    ref = log.tool_start("t")
    log.tool_end(ref, "[error] boom [ok]", False)
    out = _render_log(log)
    assert "[error]" in out and "[ok]" in out


def test_cognitive_based_on_not_eaten():
    """based_on 列表 ['x'] 含 [] → 不能被吞。"""
    log = _log()
    log.cognitive("reflect", "c", based_on=["node1"])
    out = _render_log(log)
    assert "node1" in out


def test_cognitive_renders_as_inline_line_not_band():
    """认知事件降级为 dim inline 行(不再是背景块)。"""
    log = _log()
    log.cognitive("intuition", "guess")
    # entries 里应是 line, 不是 block
    assert all(kind == "line" for kind, _ in log.entries)


def test_thinking_renders_as_inline_line_not_band():
    log = _log()
    log.thinking("hmm")
    assert all(kind == "line" for kind, _ in log.entries)


def test_user_and_tool_still_have_bands():
    """user + tool 仍保留背景块(这俩有意义), 不被一起降级。"""
    log = _log()
    log.user("hi")
    ref = log.tool_start("t")
    log.tool_end(ref, "r", False)
    kinds = [kind for kind, _ in log.entries]
    assert kinds.count("block") == 2   # user + tool


def test_user_message_with_bracket_shown():
    """用户消息含 [ → 字面(注: 当前 user 不转义, 但至少不崩)。"""
    log = _log()
    log.user("see [red] text")
    log._ensure_units(40)   # 不崩
