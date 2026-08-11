"""自研 TUI 引擎单测(markup / buffer / css / layout / widgets / app 渲染)。"""
from prism.tui.markup import Style, parse_markup, wrap_segments, strip_markup
from prism.tui.buffer import Buffer, render_plain, render_diff, char_width
from prism.tui.css import parse_css
from prism.tui.widget import layout, Widget
from prism.tui.widgets import Header, RichLog, Static, Input, Footer
from prism.tui.app import App
from prism.tui.terminal import Key


# ── markup ─────────────────────────────────────────────────────────────────
def test_markup_bold_cyan_combo():
    segs = parse_markup("[bold cyan]x[/bold cyan]")
    assert segs == [("x", Style(bold=True, fg=6))]


def test_markup_stack_nesting():
    # 外层 bold, 内层 cyan → 内层片段 bold+cyan; 外层复位后仅 bold 应消失
    segs = parse_markup("[bold]a[cyan]b[/]c[/]")
    assert segs[1] == ("b", Style(bold=True, fg=6))     # 嵌套归约
    assert segs[2] == ("c", Style(bold=True))           # cyan 关闭, bold 仍在


def test_markup_escape_bracket():
    assert strip_markup("a\\[b]c") == "a[b]c"
    # 转义的 [ 不被当标签起点, 文本原样保留
    assert "".join(t for t, _ in parse_markup("a\\[b]c")) == "a[b]c"


def test_markup_256_sgr():
    assert Style(fg=240).sgr() == "38;5;240"            # 256 色
    assert Style(fg=6).sgr() == "36"                    # 基本色
    assert Style(fg=10).sgr() == "92"                   # bright
    assert Style(bold=True, fg=1).sgr() == "1;31"


def test_wrap_preserves_style_across_break():
    rows = wrap_segments(parse_markup("[red]abcdefghijklmnop[/red]"), 5)
    assert len(rows) == 4
    assert all(s == Style(fg=1) for _, s in rows[0])


# ── buffer ─────────────────────────────────────────────────────────────────
def test_buffer_box_and_plain():
    b = Buffer(20, 4)
    b.box(0, 0, 20, 4, title="t", border_style=Style(fg=6))
    out = render_plain(b)
    assert out.startswith("╭")
    assert "t" in out
    assert out.endswith("╯")


def test_buffer_wide_char_cjk():
    assert char_width("中") == 2
    assert char_width("a") == 1
    b = Buffer(6, 1)
    b.write(0, 0, "中文", Style())
    # 两个全宽字符占满 6 列
    assert render_plain(b) == "中文"


def test_render_diff_only_changed_rows():
    a = Buffer(10, 2); b = Buffer(10, 2)
    a.write(0, 0, "hello", Style()); a.write(0, 1, "world", Style())
    b.write(0, 0, "hello", Style()); b.write(0, 1, "WORLD", Style())
    diff = render_diff(a, b)
    assert "world" not in diff and "WORLD" in diff
    assert diff.count("\x1b[2;1H") == 1            # 只重定位到第 2 行一次


# ── css / layout ───────────────────────────────────────────────────────────
def test_css_heights():
    sheet = parse_css("""
#a { height: 3; }
#b { height: auto; min-height: 2; }
#c { height: 1fr; }
""")
    assert sheet.by_id["a"].height == ("fix", 3)
    assert sheet.by_id["b"].height == ("auto", 0)
    assert sheet.by_id["b"].min_height == 2
    assert sheet.by_id["c"].height == ("fr", 1)


def test_layout_vertical_flex():
    class W(Widget):
        def __init__(self, i, m): super().__init__(i); self._m = m
        def measure(self, width): return self._m
    ws = [W("a", 1), W("b", 2), W("c", 0)]          # c = fr
    sheet = parse_css("#c{height:1fr;}")
    styles = lambda w: sheet.for_widget(w.id, type(w).__name__)
    regs = layout(ws, styles, total_h=10, width=40)
    # a=1, b=2, c 吃剩余 7
    assert regs[0][3] == 1 and regs[1][3] == 2 and regs[2][3] == 7
    # 纵向堆叠 y 递增
    assert regs[0][1] == 0 and regs[1][1] == 1 and regs[2][1] == 3


# ── widgets ────────────────────────────────────────────────────────────────
class _StubApp:
    """给 widget.draw 喂 theme 的桩(不走完整 App)。"""
    theme = "dark"
    from prism.tui.app import DARK as _DARK
    _themes = {"dark": _DARK}
    def style(self, t): return self._themes["dark"].get(t, Style())
    model_name = "test-model"
    _agent_busy = False


def test_input_typing_and_submit_clears():
    inp = Input(id="d")
    captured = {}
    class A(_StubApp):
        def _input_submitted(self, ev): captured["v"] = ev.value
    inp.app = A()
    inp.focus()
    for c in "hello":
        inp.on_key(Key(key=c, char=c))
    assert inp.value == "hello"
    inp.on_key(Key(key="backspace", char=""))
    assert inp.value == "hell"
    inp.on_key(Key(key="enter", char=""))           # 提交 → 回调 + 自清
    assert captured["v"] == "hell"
    assert inp.value == ""


def test_input_multiline_shift_enter():
    inp = Input(id="d"); inp.app = _StubApp(); inp.focus()
    inp.on_key(Key(key="a", char="a"))
    inp.on_key(Key(key="enter", char="", shift=True))
    inp.on_key(Key(key="b", char="b"))
    assert inp.value == "a\nb"
    assert inp.measure(40) >= 4                      # 两行 + 边框


def test_input_renders_at_nonzero_y():
    """回归: Input 在非零纵偏移区域时内容/占位符不能被画到屏外。"""
    inp = Input(id="d", placeholder="PH"); inp.app = _StubApp(); inp.focus()
    b = Buffer(20, 10)
    inp.draw(b, 0, 6, 20, 3)                        # y=6
    out = render_plain(b)
    assert "PH" in out                              # 占位符落在框内


def test_richlog_scroll():
    log = RichLog(id="t"); log.app = _StubApp()
    for i in range(40):
        log.write(f"line{i}")
    units = log._ensure_units(80)          # 40 行 → 40 个 line unit
    assert len(units) == 40
    assert log._follow is True             # 初始贴底
    log.scroll_up(5)                       # 40 unit, ih=24 → 贴底起点 16, 减 5 = 11
    assert log._follow is False
    assert log._top == 11
    log.scroll_end()
    assert log._follow is True             # 回到贴底


# ── app headless render ─────────────────────────────────────────────────────
def test_app_render_contains_all_regions():
    class A(App):
        CSS = "#t{height:1fr;border:round $accent;padding:0 1;}"
        def compose(self):
            h = Header(id="h"); h.title = "Prism"
            t = RichLog(id="t"); t.write("[bold green]❯[/] hi")
            yield h; yield t
            yield Footer(id="f")
        def on_mount(self): self.model_name = "m"
    a = A()
    out = a.render_to_string(rows=10, cols=40)
    assert "◆ Prism" in out
    assert "❯ hi" in out
    assert "idle" in out
