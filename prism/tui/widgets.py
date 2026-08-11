"""内置 widgets(对齐 textual 的命名: Header / RichLog / Static / Input) + Footer。"""
from __future__ import annotations
import time
from .markup import Style, parse_markup, wrap_segments, strip_markup
from .buffer import char_width
from .widget import Widget


# ── Header ─────────────────────────────────────────────────────────────────
class Header(Widget):
    """顶栏: 标题(左) + 快捷键提示(右)。1 行, 无边框。"""
    can_focus = False

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id)
        self.title = "Prism"
        self.hint = "/ commands · @ agents · python"

    def measure(self, width: int) -> int:
        return 1

    def draw(self, buf, x, y, w, h) -> None:
        accent = self.app.style("accent")
        dim = self.app.style("dim")
        buf.write(x + 1, y, f"◆ {self.title}", accent)
        buf.write_markup(x + w - 1 - len(self.hint) - 1, y, f"[dim]{self.hint}[/dim]")


# ── RichLog(可滚动 transcript) ─────────────────────────────────────────────
class RichLog(Widget):
    """滚动日志区。write(markup) 追加一行; PgUp/PgDn/Home/End 滚动。"""
    can_focus = False

    def __init__(self, id: str | None = None, wrap: bool = True) -> None:
        super().__init__(id)
        self.wrap = wrap
        self.lines: list[str] = []
        self._scroll: int | None = None   # None = 自动贴底
        self._cache_w = -1
        self._rows: list[list[tuple[str, Style]]] = []

    # ── 内容 ─────────────────────────────────────────────────────────────
    def write(self, markup: str) -> None:
        for piece in markup.split("\n"):
            self.lines.append(piece)
        if self._scroll is None:
            pass  # 贴底, draw 时自然显示最新
        else:
            self._scroll += markup.count("\n") + 1  # 跟随新内容

    def clear(self) -> None:
        self.lines.clear()
        self._cache_w = -1

    # ── 滚动 ─────────────────────────────────────────────────────────────
    def _disp_w(self) -> int:
        return self._cache_w if self._cache_w > 0 else 80

    def scroll_up(self, n: int) -> None:
        total = len(self._ensure_rows(self._disp_w()))
        if self._scroll is None:
            self._scroll = total
        self._scroll = max(0, self._scroll - n)

    def scroll_down(self, n: int) -> None:
        if self._scroll is None:
            return
        self._scroll += n
        total = len(self._ensure_rows(self._disp_w()))
        if self._scroll >= total:
            self._scroll = None

    def scroll_home(self) -> None:
        self._scroll = 0

    def scroll_end(self) -> None:
        self._scroll = None

    # ── 布局/绘制 ─────────────────────────────────────────────────────────
    def measure(self, width: int) -> int:
        return 1  # transcript 通常是 fr, 不靠 measure

    def _inner(self, w: int, h: int) -> tuple[int, int, int, int]:
        """(ix, iy, iw, ih) 内容区(去掉边框 + padding)。"""
        return 2, 1, max(1, w - 4), max(1, h - 2)

    def _ensure_rows(self, iw: int) -> list[list[tuple[str, Style]]]:
        if iw != self._cache_w:
            self._cache_w = iw
            self._rows = []
            for ln in self.lines:
                segs = parse_markup(ln)
                wrapped = wrap_segments(segs, iw) if self.wrap else [segs]
                if not wrapped:
                    wrapped = [[]]
                self._rows.extend(wrapped)
        return self._rows

    def draw(self, buf, x, y, w, h) -> None:
        ix, iy, iw, ih = self._inner(w, h)
        # 边框
        border = self.app.style("border_muted")
        buf.box(x, y, w, h, border_style=border)
        rows = self._ensure_rows(iw)
        total = len(rows)
        # 决定可视窗口
        if self._scroll is None:
            start = max(0, total - ih)
        else:
            start = min(self._scroll, max(0, total - ih))
        # 顶部滚动指示
        if start > 0:
            buf.write(x + w - 3, y, "▲", self.app.style("dim"))
        if start + ih < total:
            buf.write(x + w - 3, y + h - 1, "▼", self.app.style("dim"))
        # 绘制可见行
        for r in range(ih):
            idx = start + r
            if idx >= total:
                break
            buf.write_segments(ix, y + iy + r, rows[idx])


# ── Static(单块静态文本, streaming 缓冲) ────────────────────────────────────
class Static(Widget):
    can_focus = False
    def __init__(self, id: str | None = None, content: str = "") -> None:
        super().__init__(id)
        self.content = content

    def update(self, content: str) -> None:
        self.content = content

    def measure(self, width: int) -> int:
        iw = max(1, width - 2)
        rows = wrap_segments(parse_markup(self.content), iw) or [[]]
        return max(1, len(rows))

    def draw(self, buf, x, y, w, h) -> None:
        iw = max(1, w - 2)
        rows = wrap_segments(parse_markup(self.content), iw) or [[]]
        text_style = self.app.style("thinking_text")
        for r in range(h):
            if r >= len(rows):
                break
            segs = [(t, text_style.merge(s)) for t, s in rows[r]]
            buf.write_segments(x + 1, y + r, segs)


# ── Input(多行编辑器 + 光标) ─────────────────────────────────────────────────
class Input(Widget):
    """编辑器。Enter 提交, Shift+Enter 换行(pi 同款)。边框颜色 = accent。"""

    max_lines = 6

    class Submitted:
        def __init__(self, value: str, input: "Input") -> None:
            self.value = value
            self.input = input

    def __init__(self, id: str | None = None, placeholder: str = "") -> None:
        super().__init__(id)
        self.value = ""
        self.pos = 0
        self.placeholder = placeholder

    def measure(self, width: int) -> int:
        nlines = max(1, self.value.count("\n") + 1)
        return max(3, min(self.max_lines + 2, nlines + 2))

    # ── 光标 ─────────────────────────────────────────────────────────────
    def _cursor_rc(self) -> tuple[int, int]:
        before = self.value[:self.pos]
        row = before.count("\n")
        col = len(before) - (before.rfind("\n") + 1 if "\n" in before else 0)
        return row, col

    def _line_starts(self) -> list[int]:
        starts = [0]
        for i, ch in enumerate(self.value):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    # ── 编辑 ─────────────────────────────────────────────────────────────
    def _insert(self, s: str) -> None:
        self.value = self.value[:self.pos] + s + self.value[self.pos:]
        self.pos += len(s)

    def _delete_back(self) -> None:
        if self.pos > 0:
            self.value = self.value[:self.pos - 1] + self.value[self.pos:]
            self.pos -= 1

    def _delete_fwd(self) -> None:
        if self.pos < len(self.value):
            self.value = self.value[:self.pos] + self.value[self.pos + 1:]

    def clear(self) -> None:
        self.value = ""
        self.pos = 0

    def on_key(self, key) -> bool:
        k = key.key
        if key.is_printable():
            self._insert(key.char)
            return True
        if k == "enter":
            if key.shift:
                self._insert("\n")
            else:
                self.app._input_submitted(self.Submitted(self.value, self))
                self.clear()
            return True
        if k == "backspace":
            self._delete_back(); return True
        if k == "delete":
            self._delete_fwd(); return True
        if k == "left":
            self.pos = max(0, self.pos - 1); return True
        if k == "right":
            self.pos = min(len(self.value), self.pos + 1); return True
        if k == "home":
            self.pos = self._line_starts()[self._cursor_rc()[0]]; return True
        if k == "end":
            rc = self._cursor_rc()
            nxt = self.value.find("\n", self._line_starts()[rc[0]])
            self.pos = nxt if nxt != -1 else len(self.value); return True
        if k == "up":
            self._move_line(-1); return True
        if k == "down":
            self._move_line(1); return True
        if k == "ctrl+a":
            self.pos = self._line_starts()[self._cursor_rc()[0]]; return True
        if k == "ctrl+e":
            return self.on_key(type(key)(key="end", char="", ctrl=True))
        if k == "ctrl+u":
            ls = self._line_starts()[self._cursor_rc()[0]]
            self.value = self.value[:ls] + self.value[self.pos:]
            self.pos = ls; return True
        if k == "ctrl+k":
            nxt = self.value.find("\n", self.pos)
            self.value = self.value[:self.pos] + self.value[(nxt + 1 if nxt != -1 else len(self.value)):]
            return True
        if k == "ctrl+w":
            self._delete_word(); return True
        return False

    def _move_line(self, d: int) -> None:
        row, col = self._cursor_rc()
        starts = self._line_starts()
        tgt = row + d
        if tgt < 0 or tgt >= len(starts):
            return
        line_start = starts[tgt]
        line_end = self.value.find("\n", line_start)
        line = self.value[line_start:line_end if line_end != -1 else len(self.value)]
        # 按显示宽度定位列
        acc, cx = 0, 0
        while cx < len(line) and acc + char_width(line[cx]) <= col:
            acc += char_width(line[cx]); cx += 1
        self.pos = line_start + cx

    def _delete_word(self) -> None:
        i = self.pos
        while i > 0 and self.value[i - 1] == " ":
            i -= 1
        while i > 0 and self.value[i - 1] != " " and self.value[i - 1] != "\n":
            i -= 1
        self.value = self.value[:i] + self.value[self.pos:]
        self.pos = i

    # ── 绘制 ─────────────────────────────────────────────────────────────
    def draw(self, buf, x, y, w, h) -> None:
        border = self.app.style("accent") if self._focused else self.app.style("border_muted")
        buf.box(x, y, w, h, border_style=border)
        ix, iw, ih = x + 1, max(1, w - 2), max(1, h - 2)
        lines = self.value.split("\n") if self.value else [""]
        # 多行时滚动让光标行可见
        crow, ccol = self._cursor_rc()
        top = max(0, crow - ih + 1) if crow >= ih else 0
        text_style = self.app.style("text")
        for r in range(ih):
            li = top + r
            if li >= len(lines):
                break
            line = lines[li]
            if not self.value and self.placeholder and r == 0:
                buf.write_markup(ix, y + 1 + r, f"[dim]{self.placeholder}[/dim]")
                continue
            buf.write(ix, y + 1 + r, line, text_style)
        # 光标(反相)
        vis_row = crow - top
        if 0 <= vis_row < ih:
            # 计算显示列
            line = lines[crow]
            acc, cx = 0, 0
            while cx < len(line) and acc < ccol:
                acc += char_width(line[cx]); cx += 1
            cx_screen = ix + acc
            if cx_screen < x + w - 1:
                cy = y + 1 + vis_row
                # 反相该格
                cell = buf.grid[cy][cx_screen] if cy < buf.rows and cx_screen < buf.cols else None
                ch = cell.ch if cell and cell.ch else " "
                buf.put(cx_screen, cy, ch, Style(fg=0, bg=37))


# ── Footer(cwd · session · model · busy) ────────────────────────────────────
class Footer(Widget):
    _SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    can_focus = False

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id)

    def measure(self, width: int) -> int:
        return 1

    def draw(self, buf, x, y, w, h) -> None:
        dim = self.app.style("dim")
        accent = self.app.style("accent")
        sep = " · "
        # 左: cwd
        import os
        cwd = os.path.basename(os.getcwd()) or os.getcwd()
        left = f" {cwd}"
        cx = buf.write_markup(x, y, f"[dim]{left}[/dim]")
        # 中: model
        model = getattr(self.app, "model_name", "") or ""
        if model:
            cx = buf.write(cx, y, sep, dim)
            cx = buf.write_markup(cx, y, f"[accent]{model}[/accent]")
        # 右: busy / idle
        if getattr(self.app, "_agent_busy", False):
            frame = self._SPIN[int(time.time() * 8) % len(self._SPIN)]
            right = f"{frame} working "
            buf.write_markup(x + w - len(right), y, f"[accent]{right}[/accent]")
        else:
            right = " ● idle "
            buf.write_markup(x + w - len(right), y, f"[dim]{right}[/dim]")
