"""App 基类 —— textual 风格 API 的自研实现核心。

对外 API(与 textual 心智一致):
  - 类属性 ``CSS`` / ``TITLE``
  - ``compose()`` / ``on_mount()`` / ``on_key(key)`` / ``on_input_submitted(event)``
  - ``run()`` 主循环(原始终端)
  - ``call_from_thread(fn, *a, **k)`` 跨线程安全调度(agent 后台线程 emit 必经此路)
  - ``query_one(sel)`` / ``request_render()`` / ``theme`` / ``style(token)``
"""
from __future__ import annotations
import queue as _q
import threading
import time
from typing import Any, Callable

from .markup import Style
from .buffer import Buffer, render_diff, render_plain
from .css import parse_css, ComputedStyle, Stylesheet
from .widget import Widget, layout
from .terminal import Terminal


# ── 内置主题(对齐 pi token 体系) ───────────────────────────────────────────
DARK = {
    "accent": Style(fg=6), "primary": Style(fg=4),
    "success": Style(fg=2), "error": Style(fg=1), "warning": Style(fg=3),
    "muted": Style(dim=True), "dim": Style(dim=True), "text": Style(),
    "thinking_text": Style(dim=True, italic=True),
    "border_muted": Style(fg=238, dim=True), "user": Style(fg=2),
    # pi 风格块背景(256 色索引)
    "user_bg": 236, "tool_pending_bg": 236, "tool_success_bg": 22,
    "tool_error_bg": 52, "thinking_bg": 235, "cognitive_bg": 237,
}
LIGHT = {
    "accent": Style(fg=4), "primary": Style(fg=5),
    "success": Style(fg=2), "error": Style(fg=1), "warning": Style(fg=3),
    "muted": Style(dim=True), "dim": Style(dim=True), "text": Style(),
    "thinking_text": Style(dim=True, italic=True),
    "border_muted": Style(fg=250, dim=True), "user": Style(fg=2),
    "user_bg": 254, "tool_pending_bg": 254, "tool_success_bg": 194,
    "tool_error_bg": 217, "thinking_bg": 254, "cognitive_bg": 253,
}


class App:
    CSS: str = ""
    TITLE: str = "App"

    def __init__(self) -> None:
        self.theme: str = "dark"
        self._themes: dict[str, dict] = {"dark": DARK, "light": LIGHT}
        self.available_themes: dict[str, dict] = self._themes
        self._widgets: list[Widget] = []
        self._focusable: list[Widget] = []
        self._focus_idx: int = -1
        self._calls: _q.Queue = _q.Queue()
        self._dirty = True
        self._quit = threading.Event()
        self._rows = 24
        self._cols = 80
        self._term: Terminal | None = None
        self._last_ctrlc = 0.0
        self._sheet: Stylesheet = Stylesheet()
        # 子类可填: 运行态
        self._agent_busy = False
        self.model_name = ""

    # ── 子类钩子 ─────────────────────────────────────────────────────────
    def compose(self) -> list[Widget]:
        return []

    def on_mount(self) -> None:
        pass

    def on_key(self, key) -> None:
        pass

    def on_input_submitted(self, event) -> None:
        pass

    # ── 主题 / 样式 ──────────────────────────────────────────────────────
    def style(self, token: str) -> Style:
        return self._themes.get(self.theme, DARK).get(token, Style())

    # ── 跨线程调度 ───────────────────────────────────────────────────────
    def call_from_thread(self, fn: Callable, *args: Any, **kw: Any) -> None:
        """把 fn 丢到主循环线程执行(agent 后台线程改 UI 必经此路)。"""
        self._calls.put((fn, args, kw))

    def request_render(self) -> None:
        self._dirty = True

    # ── 查询 ─────────────────────────────────────────────────────────────
    def query_one(self, sel: str) -> Widget | None:
        if sel.startswith("#"):
            for w in self._widgets:
                if w.id == sel[1:]:
                    return w
        else:
            for w in self._widgets:
                if type(w).__name__ == sel:
                    return w
        return None

    def _style_for(self, w: Widget) -> ComputedStyle:
        return self._sheet.for_widget(w.id, type(w).__name__)

    # ── 内部: 装配 ───────────────────────────────────────────────────────
    def _build(self) -> None:
        self._sheet = parse_css(self.CSS) if self.CSS else Stylesheet()
        self._widgets = list(self.compose())
        # 展开子 compose
        flat: list[Widget] = []
        stack = list(self._widgets)
        while stack:
            w = stack.pop(0)
            w.mount(self)
            flat.append(w)
            for c in w.compose():
                stack.insert(0, c)
        self._widgets = flat
        self._focusable = [w for w in flat if w.can_focus]
        if self._focusable:
            self._focus_idx = 0
            self._focusable[0].focus()

    def _input_submitted(self, event) -> None:
        self.on_input_submitted(event)

    # ── 主循环 ───────────────────────────────────────────────────────────
    def run(self, *, headless: bool = False, cols: int = 80, rows: int = 24) -> None:
        self._build()
        self._rows, self._cols = rows, cols
        self.on_mount()
        if headless:
            return  # 单测用: 装配 + on_mount 后直接返回, 不进终端
        with Terminal() as term:
            self._term = term
            prev: Buffer | None = None
            last_render = 0.0
            while not self._quit.is_set():
                self._drain()
                # 按键
                key = term.poll_key(0.05)
                while key is not None:
                    if key.key == "__resize__":
                        self._dirty = True
                        prev = None
                    else:
                        self._dispatch_key(key)
                    key = term.poll_key(0.0)
                # 尺寸
                r, c = term.size()
                if (r, c) != (self._rows, self._cols):
                    self._rows, self._cols = r, c
                    self._dirty = True
                    prev = None
                # busy 时持续刷帧(spinner 动画)
                now = time.time()
                if self._agent_busy and now - last_render > 0.12:
                    self._dirty = True
                if self._dirty:
                    buf = self._render_frame(self._rows, self._cols)
                    term.write(render_diff(prev, buf))
                    prev = buf
                    self._dirty = False
                    last_render = now

    def _drain(self) -> None:
        ran = False
        while True:
            try:
                fn, args, kw = self._calls.get_nowait()
            except _q.Empty:
                break
            try:
                fn(*args, **kw)
            except Exception as e:  # noqa
                self._log_err(e)
            ran = True
        if ran:
            self._dirty = True

    def _log_err(self, e: Exception) -> None:
        log = self.query_one("#transcript")
        if isinstance(log, type(None)) or log is None:
            return
        from .widgets import RichLog
        if isinstance(log, RichLog):
            log.write(f"[red]✗ {type(e).__name__}: {e}[/red]")

    def _dispatch_key(self, key) -> None:
        k = key.key
        # Ctrl+C: 清空 / 双击退出(pi 同款)
        if k == "ctrl+c":
            inp = self._focusable[self._focus_idx] if self._focus_idx >= 0 else None
            if inp is not None and getattr(inp, "value", ""):
                inp.clear()
                self.request_render()
                return
            now = time.time()
            if now - self._last_ctrlc < 1.0:
                self._quit.set()
                return
            self._last_ctrlc = now
            log = self.query_one("#transcript")
            from .widgets import RichLog
            if isinstance(log, RichLog):
                log.write("[dim](Ctrl+C again to quit)[/dim]")
            self.request_render()
            return
        # Tab 循环焦点
        if k == "tab":
            self._cycle_focus()
            return
        # 滚动键 → transcript(即便焦点在 Input)
        log = self.query_one("#transcript")
        from .widgets import RichLog
        if isinstance(log, RichLog):
            if k == "pageup":
                log.scroll_up(max(1, self._rows // 2)); self.request_render(); return
            if k == "pagedown":
                log.scroll_down(max(1, self._rows // 2)); self.request_render(); return
            if k == "home":
                log.scroll_home(); self.request_render(); return
            if k == "end":
                log.scroll_end(); self.request_render(); return
        # 先给焦点 widget
        if self._focus_idx >= 0 and self._focusable[self._focus_idx].on_key(key):
            self.request_render()
            return
        # 再给 app
        self.on_key(key)
        self.request_render()

    def _cycle_focus(self) -> None:
        if not self._focusable:
            return
        if self._focus_idx >= 0:
            self._focusable[self._focus_idx].blur()
        self._focus_idx = (self._focus_idx + 1) % len(self._focusable)
        self._focusable[self._focus_idx].focus()
        self.request_render()

    # ── 渲染一帧到 buffer(可单测) ─────────────────────────────────────────
    def _render_frame(self, rows: int, cols: int) -> Buffer:
        buf = Buffer(cols, rows)
        styles = self._style_for
        regions = layout(self._widgets, styles, rows, cols)
        for w, (x, y, w_, h) in zip(self._widgets, regions):
            if h <= 0:
                continue
            try:
                w.draw(buf, x, y, w_, h)
            except Exception:  # noqa
                pass
        return buf

    def render_to_string(self, rows: int = 24, cols: int = 80) -> str:
        """无终端渲染快照(测试 / 调试用)。"""
        if not self._widgets:
            self._build()
        return render_plain(self._render_frame(rows, cols))

    # ── 退出 ─────────────────────────────────────────────────────────────
    def exit(self) -> None:
        self._quit.set()
