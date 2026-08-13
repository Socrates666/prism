"""prism 自研 TUI(textual 接口相近, 零 textual/rich 依赖)。

对外导出与 textual 同名的概念, 便于上层平迁:
    App, ComposeResult, Header, Input, RichLog, Static, Widget
"""
from .app import App
from .widget import Widget, layout
from .buffer import Buffer, render_diff, render_plain
from .markup import Style, parse_markup, wrap_segments, strip_markup
from .widgets import Header, RichLog, Static, Input, Footer
from .css import parse_css, Stylesheet, ComputedStyle
from .terminal import Terminal, Key

# textual 兼容别名(上层 import 行可不改)
ComposeResult = list  # compose() yield → 我们用 list


def run(app: App) -> None:
    app.run()


__all__ = [
    "App", "Widget", "Buffer", "render_diff", "render_plain",
    "Style", "parse_markup", "wrap_segments", "strip_markup",
    "Header", "RichLog", "Static", "Input", "Footer",
    "parse_css", "Stylesheet", "ComputedStyle",
    "Terminal", "Key", "ComposeResult", "run",
]
