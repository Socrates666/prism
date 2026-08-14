"""App 基类 —— textual 风格 API 的自研实现核心。

对外 API(与 textual 心智一致):
  - 类属性 ``CSS`` / ``TITLE``
  - ``compose()`` / ``on_mount()`` / ``on_key(key)`` / ``on_input_submitted(event)``
  - ``run()`` 主循环(原始终端)
  - ``call_from_thread(fn, *a, **k)`` 跨线程安全调度(agent 后台线程 emit 必经此路)
  - ``query_one(sel)`` / ``request_render()`` / ``theme`` / ``style(token)``
"""
from __future__ import annotations
import os
import queue as _q
import threading
import time
from dataclasses import replace
from typing import Any, Callable

from .markup import Style, set_color_theme
from .buffer import Buffer, render_diff, render_plain
from .css import parse_css, ComputedStyle, Stylesheet
from .widget import Widget, layout
from .terminal import Terminal


# ── 内置主题(对齐 pi token 体系) ───────────────────────────────────────────
def _h(s: str):
    """hex(#rrggbb) → (r,g,b) 元组(truecolor)。"""
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


# pi dark.json 对齐(软色 Tomorrow Night 系; bg token 存裸 RGB 元组)
DARK = {
    "accent": Style(fg=_h("8abeb7")), "primary": Style(fg=_h("5f87ff")),
    "border": Style(fg=_h("5f87ff")), "border_accent": Style(fg=_h("00d7ff")),
    # 灰阶阶梯(三语义分离): thinking_text #808080 < muted #8a8a8a < tool_output #9a9a9a
    # border_muted #6a6a6a 对 page_bg 纯黑 #000000 ≈5.4:1(≥3:1, 失焦输入框边框清晰)
    "border_muted": Style(fg=_h("6a6a6a")),
    "success": Style(fg=_h("b5bd68")), "error": Style(fg=_h("cc6666")),
    "warning": Style(fg=_h("ffff00")), "muted": Style(fg=_h("8a8a8a")),
    "dim": Style(fg=_h("666666")), "text": Style(fg=_h("d4d4d4")),
    "thinking_text": Style(fg=_h("808080"), italic=True),
    "user": Style(fg=_h("d4d4d4")), "tool_output": Style(fg=_h("9a9a9a")),
    "custom_label": Style(fg=_h("9575cd")), "md_heading": Style(fg=_h("f0c674")),
    "user_bg": _h("343541"), "tool_pending_bg": _h("282832"),
    "tool_success_bg": _h("283228"), "tool_error_bg": _h("3c2828"),
    "thinking_bg": _h("282832"), "cognitive_bg": _h("2d2838"),
    "code_bg": _h("1e1e26"),                       # 模型输出代码块背景(比 tool_pending 深, 区隔状态块)
    "page_bg": Style(fg=_h("000000")),             # 整页铺底纯黑(用户裁决 2026-08-14, 旧 #18181e 灰蓝)
    # editor_border 不在表内: style() 实时解析(默认 DeepPink / PRISM_INPUT_BORDER=accent)
}
LIGHT = {
    "accent": Style(fg=_h("5a8080")), "primary": Style(fg=_h("547da7")),
    "border": Style(fg=_h("547da7")), "border_accent": Style(fg=_h("547da7")),
    # 灰阶阶梯(暗主题镜像, 越重要越深): tool_output #565656 < muted #616161 < thinking_text #6c6c6c
    # border_muted #909090 对 page_bg #ffffff ≈3.2:1(≥3:1)
    "border_muted": Style(fg=_h("909090")),
    "success": Style(fg=_h("588458")), "error": Style(fg=_h("aa5555")),
    "warning": Style(fg=_h("9a7326")), "muted": Style(fg=_h("616161")),
    "dim": Style(fg=_h("767676")), "text": Style(fg=_h("1f2328")),
    "thinking_text": Style(fg=_h("6c6c6c"), italic=True),
    "user": Style(fg=_h("1f2328")), "tool_output": Style(fg=_h("565656")),
    "custom_label": Style(fg=_h("9575cd")), "md_heading": Style(fg=_h("9a7326")),
    "user_bg": _h("e8e8e8"), "tool_pending_bg": _h("e8e8f0"),
    "tool_success_bg": _h("e8f0e8"), "tool_error_bg": _h("f0e8e8"),
    "thinking_bg": _h("e8e8f0"), "cognitive_bg": _h("ede7f6"),
    "code_bg": _h("f0f0f5"),                       # 浅色版代码块背景
    "page_bg": Style(fg=_h("ffffff")),             # 整页铺底色(RGB 存 fg, _page_rgb() 取)
    # editor_border 不在表内: style() 实时解析(默认深玫红 d63384 / accent 模式随主题)
}


class App:
    CSS: str = ""
    TITLE: str = "App"

    def __init__(self) -> None:
        self._theme: str = "dark"
        set_color_theme("dark")   # 同步 markup 全局色表(防御同进程前序 app 残留)
        self._themes: dict[str, dict] = {"dark": DARK, "light": LIGHT}
        self.available_themes: dict[str, dict] = self._themes
        self._widgets: list[Widget] = []
        self._overlays: list[dict] = []   # 浮层: [{id, widget, x, y, w, h}] 后画覆盖主布局
        self._overlay_seq: int = 0
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
    @property
    def theme(self) -> str:
        return self._theme

    @theme.setter
    def theme(self, name: str) -> None:
        self._theme = name
        set_color_theme(name)   # markup 命名色随主题(浅色下重映射语义 4 色)

    def style(self, token: str) -> Style:
        if token == "editor_border":
            # 聚焦输入框边框实时读环境(免 reload 可测/可切):
            # 默认 DeepPink(pi-faithful); PRISM_INPUT_BORDER=accent 换主题 accent(批判轮 D 方案)
            if os.environ.get("PRISM_INPUT_BORDER", "").lower() == "accent":
                return self._themes.get(self._theme, DARK)["accent"]
            return Style(fg=_h("d63384" if self._theme == "light" else "ff1493"))
        return self._themes.get(self._theme, DARK).get(token, Style())

    def _page_rgb(self):
        """page_bg token 的 RGB(整页铺底色, 缺 token 时返回 None 不铺)。"""
        return self.style("page_bg").fg

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
        # 输入历史: 提交即记录(连续重复去重), 供单行 up/down 回溯(存于 Input 自身)
        inp = getattr(event, "input", None)
        v = getattr(event, "value", "")
        if inp is not None and getattr(inp, "history", None) is not None:
            if v.strip() and (not inp.history or inp.history[-1] != v):
                inp.history.append(v)
            inp._hist_idx = len(inp.history)
        # 补全浮层残留: Enter 提交不走 _on_input_changed, 浮层不会自关 → 提交即关
        hide = getattr(self, "_hide_cmd_overlay", None)
        if callable(hide):
            hide()
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
        # Ctrl+C: busy→中断(不清输入) / 有文→清空+反馈 / 空→双击退出(pi 同款三分支)
        if k == "ctrl+c":
            log = self.query_one("#transcript")
            from .widgets import RichLog
            if self._agent_busy and getattr(self, "agent", None) is not None:
                self.agent.stop()
                if isinstance(log, RichLog):
                    log.write("[yellow]⏹ 已中断[/yellow]")
                self.request_render()
                return
            inp = self._focusable[self._focus_idx] if self._focus_idx >= 0 else None
            if inp is not None and getattr(inp, "value", ""):
                inp.clear()
                if isinstance(log, RichLog):
                    log.write("[dim]（已清空）[/dim]")
                self.request_render()
                return
            now = time.time()
            if now - self._last_ctrlc < 1.0:
                self._quit.set()
                return
            self._last_ctrlc = now
            if isinstance(log, RichLog):
                log.write("[dim]（再按一次 Ctrl+C 退出）[/dim]")
            self.request_render()
            return
        # Tab: dock 聚焦时交 on_tab 钩子(@agent 填充); 否则循环焦点
        if k == "tab":
            inp = self._focusable[self._focus_idx] if self._focus_idx >= 0 else None
            if not self.on_tab(inp):
                self._cycle_focus()
            return
        # 补全浮层激活: up/down 归补全导航(不滚 transcript); Escape 关浮层不透传
        # (与 busy 中断冲突时浮层优先 —— 先关浮层, 再按一次 Esc 才中断)
        comp = getattr(self, "_completion_active", None)
        if callable(comp) and comp():
            mv = getattr(self, "_completion_move", None)
            if k in ("up", "down") and callable(mv):
                mv(-1 if k == "up" else 1)
                self.request_render()
                return
            if k == "escape":
                hide = getattr(self, "_hide_cmd_overlay", None)
                if callable(hide):
                    hide()
                self.request_render()
                return
        # 滚动键 → transcript(即便焦点在 Input)
        log = self.query_one("#transcript")
        from .widgets import RichLog
        if isinstance(log, RichLog):
            if k == "pageup":
                log.scroll_up(max(1, self._rows // 2)); self.request_render(); return
            if k == "pagedown":
                log.scroll_down(max(1, self._rows // 2)); self.request_render(); return
            if k in ("home", "end"):
                # 多行编辑 → 行首/行尾归输入框; 单行/未吃掉 → 回退 transcript 滚动
                w = self._focusable[self._focus_idx] if self._focus_idx >= 0 else None
                if w is not None and "\n" in (getattr(w, "value", "") or "") and w.on_key(key):
                    self.request_render(); return
                (log.scroll_home if k == "home" else log.scroll_end)()
                self.request_render(); return
        # 其余先给焦点 widget(up/down: 补全导航已在上拦, 此处单行翻历史/多行移行)
        if self._focus_idx >= 0 and self._focusable[self._focus_idx].on_key(key):
            self.request_render()
            return
        # 再给 app
        self.on_key(key)
        self.request_render()

    def on_tab(self, inp) -> bool:
        """Tab 钩子: 聚焦 widget 是 inp。返回 True 拦截(不焦点切换), False 放行。默认放行。"""
        return False

    def _on_input_changed(self, value: str) -> None:
        """Input value 变化钩子(输入字符/backspace)。默认 no-op, 子类重写(如 / 补全)。"""
        pass

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
                cs = styles(w)
                if cs.border and w_ >= 2 and h >= 2:
                    # CSS border 不再是死代码: 先画框, widget 内容区内缩 2 格
                    buf.box(x, y, w_, h, border_style=self.style(cs.border_token))
                    if w_ > 2 and h > 2:
                        w.draw(buf, x + 1, y + 1, w_ - 2, h - 2)
                else:
                    w.draw(buf, x, y, w_, h)
            except Exception:  # noqa
                pass
        # 浮层(overlay): 主布局画完后叠在上方(后画的覆盖) —— completion popup 等
        for ov in list(self._overlays):
            try:
                ov["widget"].draw(buf, ov["x"], ov["y"], ov["w"], ov["h"])
            except Exception:  # noqa
                pass
        # page_bg 全铺底: widget 多数只写 fg(bg=None 透传终端默认底, 浅暗错配全糊),
        # 帧尾给所有无底色 cell 补 page_bg —— 消息块/光标等显式 bg 原样保留
        page = self._page_rgb()
        if page is not None:
            for row in buf.grid:
                for c in row:
                    if c.style.bg is None:
                        c.style = replace(c.style, bg=page)
        return buf

    def show_overlay(self, widget, x: int, y: int, w: int, h: int) -> int:
        """显示浮层: widget 画到 buf 的 (x,y,w,h) 区域, 覆盖主布局。返回 overlay id(供 hide)。"""
        self._overlay_seq += 1
        widget.app = self
        self._overlays.append({"id": self._overlay_seq, "widget": widget,
                               "x": x, "y": y, "w": w, "h": h})
        self.request_render()
        return self._overlay_seq

    def hide_overlay(self, ov_id: int) -> None:
        """隐藏浮层(按 show_overlay 返回的 id)。"""
        self._overlays = [o for o in self._overlays if o["id"] != ov_id]
        self.request_render()

    def render_to_string(self, rows: int = 24, cols: int = 80) -> str:
        """无终端渲染快照(测试 / 调试用)。"""
        if not self._widgets:
            self._build()
        return render_plain(self._render_frame(rows, cols))

    # ── 退出 ─────────────────────────────────────────────────────────────
    def exit(self) -> None:
        self._quit.set()
