"""内置 widgets(对齐 textual 的命名: Header / RichLog / Static / Input) + Footer。"""
from __future__ import annotations
import time
from .markup import Style, parse_markup, wrap_segments, strip_markup, char_width
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
        buf.write(x + 1, y, f"◆ {self.title}", accent)
        buf.write_markup(x + w - 1 - len(self.hint) - 1, y, f"[dim]{self.hint}[/dim]")


# ── RichLog(可滚动 transcript, pi 风格块) ───────────────────────────────────
class _LineUnit:
    """一行(已 wrap)。"""
    def __init__(self, row): self.row = row; self.height = 1
    def draw(self, buf, x, y, w):
        buf.write_segments(x + 1, y, self.row)   # 1 格左缩进(对齐 pi outputPad)


class _BlockUnit:
    """pi 风格块: 全宽背景色带 + 1 格留白, 零边框字符(对齐 pi-tui Box)。"""
    def __init__(self, b, body_rows):
        self.b = b; self.body_rows = body_rows
        self.height = 2 + max(1, len(body_rows))   # 上下各 1 行 padding
    def draw(self, buf, x, y, w):
        b = self.b; h = self.height; bg = b.get("bg")
        if bg is not None:
            buf.fill_bg(x, y, w, h, bg)            # 全宽铺背景
        for r, row in enumerate(self.body_rows or [[]]):
            segs = [(t, s.merge(Style(bg=bg))) for t, s in row] if bg is not None else row
            buf.write_segments(x + 1, y + 1 + r, segs)   # 左留 1 格


class RichLog(Widget):
    """滚动日志区, pi 风格块状条目。

    - write(markup)         普通行(向后兼容)
    - user(text)            用户消息块(背景)
    - tool_start(...)→ref   工具调用 pending 块, 返回可变引用
    - tool_end(ref, ...)    升级为 success/error 块
    - thinking(text)        思考块(dim italic, 背景)
    - cognitive(...)        认知块(直觉/反思)
    """
    can_focus = False

    def __init__(self, id: str | None = None, wrap: bool = True) -> None:
        super().__init__(id)
        self.wrap = wrap
        self.entries: list = []          # [("line", markup)] 或 [("block", dict)]
        self._follow = True              # 贴底跟随
        self._top = 0                    # 顶部跳过的 unit 数
        self._cache_iw = -1
        self._units: list = []
        self._last_ih = 24

    # ── 内容 API ────────────────────────────────────────────────────────
    @property
    def lines(self) -> list[str]:
        """纯文本快照(测试兼容)。"""
        out = []
        for kind, payload in self.entries:
            if kind == "line":
                out.append(payload)
            else:
                if payload.get("title"):
                    out.append(payload["title"])
                out.extend(payload["body"])
        return out

    def _invalidate(self) -> None:
        self._cache_iw = -1

    def write(self, markup: str) -> None:
        for piece in markup.split("\n"):
            self.entries.append(("line", piece))
        self._invalidate()

    def clear(self) -> None:
        self.entries.clear(); self._invalidate()

    def user(self, text: str) -> None:
        # pi: 纯背景色带, 无标题无边框
        self.entries.append(("block", {
            "bg": self._bg("user_bg"), "body": [text],
        }))
        self._invalidate()

    def tool_start(self, name: str, args_str: str = "") -> dict:
        # pi: bold 工具名内联在首行(非标题栏), args dim 跟后
        head = f"[bold]{name}[/bold]" + (f"  [dim]{args_str}[/dim]" if args_str else "")
        b = {"name": name, "bg": self._bg("tool_pending_bg"), "body": [head]}
        self.entries.append(("block", b))
        self._invalidate()
        return b

    def tool_end(self, ref: dict, result: str, is_error: bool) -> None:
        # pi: 状态只靠背景色传达(绿/红), 工具名保持 bold, 结果追加在下方
        ref["bg"] = self._bg("tool_error_bg" if is_error else "tool_success_bg")
        head = f"[bold]{ref.get('name', '?')}[/bold]"
        ref["body"] = [head] + ([result] if result else [])
        self._invalidate()

    def thinking(self, text: str) -> None:
        # pi: 思考块, dim italic 文本 + 淡背景, 无标题
        self.entries.append(("block", {
            "bg": self._bg("thinking_bg"), "body": [f"[dim italic]{text}[/dim italic]"],
        }))
        self._invalidate()

    def cognitive(self, stage: str, content: str, based_on=None) -> None:
        # pi 风格: bold 标签内联 + 内容, 背景色带, 无标题栏
        label = {"intuition": "◈ intuition", "reflect": "↺ reflect"}.get(stage, stage)
        body = (f"[bold]{label}[/bold] {content}"
                + (f"  [dim](based_on {based_on})[/dim]" if based_on else ""))
        self.entries.append(("block", {
            "bg": self._bg("cognitive_bg"), "body": [body],
        }))
        self._invalidate()

    def _st(self, tok: str) -> Style:
        return self.app.style(tok) if self.app else Style()

    def _bg(self, tok: str):
        return self.app.style(tok) if self.app else None

    # ── 滚动(unit 粒度, 块始终完整) ─────────────────────────────────────
    def _disp_w(self) -> int:
        return self._cache_iw if self._cache_iw > 0 else 76

    def _ensure_units(self, iw: int) -> list:
        if iw != self._cache_iw:
            self._cache_iw = iw
            self._units = []
            body_iw = max(1, iw - 2)   # 全宽色带: 左右各 1 格留白, 无边框
            for kind, payload in self.entries:
                if kind == "line":
                    segs = parse_markup(payload)
                    rows = wrap_segments(segs, max(1, iw - 2)) if self.wrap else [segs]
                    for row in (rows or [[]]):
                        self._units.append(_LineUnit(row))
                else:
                    body_rows = []
                    for ln in payload["body"]:
                        body_rows += wrap_segments(parse_markup(ln), body_iw) or [[]]
                    self._units.append(_BlockUnit(payload, body_rows))
        return self._units

    def _bottom_start(self, ih: int) -> int:
        units = self._ensure_units(self._disp_w())
        start = len(units); acc = 0
        while start > 0 and acc + units[start - 1].height <= ih:
            start -= 1; acc += units[start].height
        return start

    def scroll_up(self, n: int = 3) -> None:
        if self._follow:
            self._follow = False
            self._top = self._bottom_start(self._last_ih)
        self._top = max(0, self._top - n)

    def scroll_down(self, n: int = 3) -> None:
        self._follow = False
        self._top += n
        if self._top >= len(self._ensure_units(self._disp_w())):
            self._follow = True

    def scroll_home(self) -> None:
        self._follow = False; self._top = 0

    def scroll_end(self) -> None:
        self._follow = True

    # ── 布局/绘制 ─────────────────────────────────────────────────────────
    def measure(self, width: int) -> int:
        return 1

    def draw(self, buf, x, y, w, h) -> None:
        # pi 消息区无边框: 块自带全宽背景, 直接堆叠
        iw, ih = max(1, w), max(1, h)
        self._last_ih = ih
        units = self._ensure_units(iw)
        total = len(units)
        start = self._bottom_start(ih) if self._follow else max(0, min(self._top, total))
        if self._follow:
            self._top = start
        yy = y
        for u in units[start:]:
            if yy + u.height > y + ih:
                break
            u.draw(buf, x, yy, iw)
            yy += u.height


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
        return 2

    def draw(self, buf, x, y, w, h) -> None:
        import os
        # 第1行: cwd(dim)
        cwd = os.path.basename(os.getcwd()) or os.getcwd()
        buf.write_markup(x, y, f"[dim] {cwd}[/dim]")
        # 第2行: 右侧 model · thinking · busy spinner
        model = getattr(self.app, "model_name", "") or ""
        agent = getattr(self.app, "agent", None)
        th = getattr(getattr(agent, "model", None), "thinking_level", None) if agent else None
        right = f"{model} · thinking {th or 'off'}"
        if getattr(self.app, "_agent_busy", False):
            frame = self._SPIN[int(time.time() * 8) % len(self._SPIN)]
            right = f"{frame} {right}"
        buf.write_markup(max(x, x + w - len(right) - 1), y + 1, f"[dim]{right}[/dim]")
