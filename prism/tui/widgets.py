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
    """一行(已 wrap)。e = 所属 entry 索引(滚动内容锚用)。"""
    def __init__(self, row, e=0): self.row = row; self.height = 1; self.e = e
    def draw(self, buf, x, y, w):
        buf.write_segments(x + 1, y, self.row)   # 1 格左缩进(对齐 pi outputPad)


class _BlockUnit:
    """pi 风格块: 全宽背景色带 + 1 格留白, 零边框字符(对齐 pi-tui Box)。"""
    def __init__(self, b, body_rows, e=0):
        self.b = b; self.body_rows = body_rows
        self.height = 2 + max(1, len(body_rows))   # 上下各 1 行 padding
        self.e = e
    def draw(self, buf, x, y, w):
        b = self.b; h = self.height; bg = b.get("bg")
        if bg is not None:
            buf.fill_bg(x, y, w, h, bg)            # 全宽铺背景
        for r, row in enumerate(self.body_rows or [[]]):
            segs = [(t, s.merge(Style(bg=bg))) for t, s in row] if bg is not None else row
            buf.write_segments(x + 1, y + 1 + r, segs)   # 左留 1 格


class RichLog(Widget):
    """滚动日志区, pi 风格块状条目。

    - write(markup)         普通行 + ``` 代码块识别(围栏行不渲染, 代码段走背景块)
    - user(text)            用户消息块(背景)
    - tool_start(...)→ref   工具调用 pending 块, 返回可变引用
    - tool_end(ref, ...)    升级为 success/error 块
    - thinking(text)        思考块(dim italic, 背景)
    - cognitive(...)        认知块(直觉/反思)
    """
    can_focus = False

    # 物化窗口 unit 预算: 任何时刻 _units 有界(≈ 一屏的若干倍), resize/写入只重建窗口
    _WIN_UNITS = 800

    def __init__(self, id: str | None = None, wrap: bool = True) -> None:
        super().__init__(id)
        self.wrap = wrap
        self.entries: list = []          # [("line", markup)] 或 [("block", dict)]
        self.max_entries = 2000          # 容量上限: 超限从头部丢弃(长会话内存有界)
        self._follow = True              # 贴底跟随
        self._top = 0                    # 顶部跳过的 unit 数(_units 窗口内索引)
        self._cache_iw = -1
        self._units: list = []           # 物化窗口: 只覆盖 entries 的 [_w_e0, _w_e1)
        self._w_e0 = 0                   # 窗口覆盖的首 entry 索引
        self._w_e1 = 0                   # 窗口覆盖的末 entry 索引(开区间)
        self._w_tail = True              # 窗口是否触达真实尾部(贴底渲染前提)
        self._last_ih = 24
        self._code_open = False        # ``` 围栏开关(跨 write: 流式中途 flush 的半块后续续上)
        self._code_buf: list[str] = []

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

    def _append(self, item) -> None:
        # 统一 append 入口(write/user/tool_start/代码块全走这): 超容量从头部丢弃,
        # 窗口/锚索引随平移, 视口顶 unit 对象不变(下次重建按锚重定位, 不漂移)。
        self.entries.append(item)
        drop = len(self.entries) - self.max_entries
        if drop > 0:
            del self.entries[:drop]
            self._w_e0 = max(0, self._w_e0 - drop)
            self._w_e1 = max(0, self._w_e1 - drop)
            for u in self._units:
                u.e -= drop

    def write(self, markup: str) -> None:
        # 最小 markdown 代码块识别: 按 ``` 围栏行切分, 围栏行本身不渲染;
        # 代码段走背景块(与正文视觉区隔), 正文段照常逐行。
        # 围栏状态跨 write 保持 —— 流式中途被截断 flush 的半块, 余下文本仍按代码续上。
        # 注意: 代码体按调用方已转义的原文直接渲染(项目惯例: shell 侧 .replace("[", "\\["))。
        for ln in (markup or "").split("\n"):
            if ln.lstrip().startswith("```"):       # 围栏行: 只切换状态, 不进 entries
                self._flush_code()
                self._code_open = not self._code_open
            elif self._code_open:
                self._code_buf.append(ln)
            else:
                self._append(("line", ln))
        self._flush_code()     # 未闭合围栏(流式只出现开头 ```): 半块也照常渲染, 不吞正文
        self._invalidate()

    def _flush_code(self) -> None:
        # 代码段 → pi 风格背景块(复用 _BlockUnit), 不按词折行(保留缩进, 超长右侧裁剪)
        if self._code_buf:
            self._append(("block", {
                "bg": self._bg("code_bg"), "body": self._code_buf, "nowrap": True}))
            self._code_buf = []

    def clear(self) -> None:
        self.entries.clear()
        self._code_open = False; self._code_buf = []
        self._units = []; self._w_e0 = self._w_e1 = 0; self._w_tail = True
        self._invalidate()

    def user(self, text: str) -> None:
        # pi: 纯背景色带, 无标题无边框
        self._append(("block", {
            "bg": self._bg("user_bg"), "body": [text],
        }))
        self._invalidate()

    def tool_start(self, name: str, args_str: str = "") -> dict:
        # 行动: 中文阶段标签 + 工具名 + args, pi 风格背景色带
        head = f"[cyan]行动[/cyan] [bold]▸ {name}[/bold]" + (f"  [dim]{args_str}[/dim]" if args_str else "")
        b = {"name": name, "bg": self._bg("tool_pending_bg"), "body": [head]}
        self._append(("block", b))
        self._invalidate()
        return b

    def tool_end(self, ref: dict, result: str, is_error: bool) -> None:
        # 观察: ✓/✗ + 中文标签 + 工具名, 背景色传达状态(绿/红)
        ref["bg"] = self._bg("tool_error_bg" if is_error else "tool_success_bg")
        mark = "✗" if is_error else "✓"
        head = f"[bold]{mark} 观察 · {ref.get('name', '?')}[/bold]"
        safe = (result or "").replace("[", "\\[")
        ref["body"] = [head] + ([safe] if safe else [])
        self._invalidate()

    def thinking(self, text: str) -> None:
        # 思考: 中文阶段标签 + dim italic 推理内容
        for sub in (text or "").split("\n"):
            self.write(f"[blue]思考[/blue] [dim italic]▸ {sub}[/dim italic]" if sub else "")

    def cognitive(self, stage: str, content: str, based_on=None) -> None:
        # 认知(直觉/反思): 中文阶段标签 + dim italic 内容
        label = {"intuition": "直觉", "reflect": "反思"}.get(stage, stage or "·")
        color = "yellow" if stage == "reflect" else "magenta"
        bo = ""
        if based_on:
            safe = str(based_on).replace("[", "\\[")   # 防 [ 被当 markup 标签吞掉
            bo = f"  [dim](based_on {safe})[/dim]"
        self.write(f"[{color}]{label}[/{color}] [dim italic]▸ {content}[/dim italic]{bo}")

    def _st(self, tok: str) -> Style:
        return self.app.style(tok) if self.app else Style()

    def _bg(self, tok: str):
        return self.app.style(tok) if self.app else None

    # ── 滚动(unit 粒度, 块始终完整) ─────────────────────────────────────
    def _disp_w(self) -> int:
        return self._cache_iw if self._cache_iw > 0 else 76

    def _entry_units(self, kind, payload, iw: int, e: int) -> list:
        # 单个 entry → unit 列表(每 entry 至少 1 个 unit, 索引单调)
        us = []
        if kind == "line":
            segs = parse_markup(payload)
            rows = wrap_segments(segs, max(1, iw - 2)) if self.wrap else [segs]
            for row in (rows or [[]]):
                us.append(_LineUnit(row, e))
        else:
            body_iw = max(1, iw - 2)   # 全宽色带: 左右各 1 格留白, 无边框
            body_rows = []
            for ln in payload["body"]:
                for sub in ln.split("\n"):       # 多行内容按行拆(对齐 write)
                    segs = parse_markup(sub)
                    if payload.get("nowrap"):    # 代码块: 不折行(保留缩进, 超长右侧裁剪)
                        body_rows.append(segs)
                    else:
                        body_rows += wrap_segments(segs, body_iw) or [[]]
            us.append(_BlockUnit(payload, body_rows, e))
        return us

    def _build_tail(self, iw: int) -> None:
        # 尾窗: 从末尾往回物化 ~3 屏 + 滚动余量(贴底渲染 / 向上滚动起步), 不再全量重建
        need = self._last_ih * 3 + 64
        us: list = []
        acc = 0
        e = len(self.entries) - 1
        while e >= 0 and acc < need:
            es = self._entry_units(*self.entries[e], iw, e)
            us = es + us
            acc += sum(u.height for u in es)
            e -= 1
        self._units = us
        self._w_e0, self._w_e1 = e + 1, len(self.entries)
        self._w_tail = True

    def _build_at(self, iw: int, e0: int) -> None:
        # 锚窗: 从 e0 向前物化到预算上限(scroll_home / 内容锚重定位), _top 归锚首行
        us: list = []
        e = e0
        n = len(self.entries)
        while e < n and len(us) < self._WIN_UNITS:
            us += self._entry_units(*self.entries[e], iw, e)
            e += 1
        self._units = us
        self._w_e0, self._w_e1 = e0, e
        self._w_tail = False
        self._top = 0

    def _ensure_units(self, iw: int) -> list:
        # 贴底必须拿到尾窗: 缓存是锚窗时(如 scroll_home 后 scroll_end)强制重建
        if iw == self._cache_iw and not (self._follow and not self._w_tail):
            return self._units
        # 重建窗口。贴底 → 尾窗; 否则按内容锚(视口顶 unit 所属 entry + entry 内偏移)
        # 重定位 —— 宽度一变 unit 总数漂移, 同一 _top 会指向完全不同内容(锚点漂移)。
        ve = off = None
        if not self._follow and self._units:
            t = min(max(self._top, 0), len(self._units) - 1)
            ve = self._units[t].e
            i0 = next((i for i, u in enumerate(self._units) if u.e == ve), 0)
            off = max(0, t - i0)
        self._cache_iw = iw
        if ve is None:
            self._build_tail(iw)
        else:
            self._build_at(iw, min(max(ve, 0), max(0, len(self.entries) - 1)))
            if off:   # 尽量保住 entry 内行偏移(±几行内, 锚 entry 内容仍在视口)
                j = next((i for i, u in enumerate(self._units) if u.e == ve), 0)
                cnt = sum(1 for u in self._units if u.e == ve)
                self._top = min(j + min(off, cnt - 1), max(0, len(self._units) - 1))
        return self._units

    def _extend_up(self, iw: int) -> None:
        # 视口顶滚出窗口头: 向上增补 ~2 屏物化; 预算满时先回收窗口尾(远端不可见区)
        if len(self._units) >= self._WIN_UNITS:
            k = max(0, self._top + self._last_ih + 64)
            if k < len(self._units):
                self._w_e1 = self._units[k - 1].e + 1 if k > 0 else self._w_e0
                self._units = self._units[:k]
        add: list = []
        acc = 0
        e = self._w_e0 - 1
        while e >= 0 and acc < self._last_ih * 2 + 16:
            es = self._entry_units(*self.entries[e], iw, e)
            add = es + add
            acc += sum(u.height for u in es)
            e -= 1
        self._units = add + self._units
        self._top += len(add)            # 头插平移: _top 指向同一内容
        self._w_e0 = e + 1

    def _extend_down(self, iw: int) -> None:
        # 视口顶滚出窗口尾: 向下增补 ~2 屏物化; 预算满时先回收窗口头(远端不可见区)
        if len(self._units) >= self._WIN_UNITS:
            k = self._top - self._last_ih - 64
            if k > 0:
                self._w_e0 = self._units[k].e
                self._units = self._units[k:]
                self._top -= k           # 头部裁剪平移: _top 指向同一内容
        acc = 0
        e = self._w_e1
        while e < len(self.entries) and acc < self._last_ih * 2 + 16:
            es = self._entry_units(*self.entries[e], iw, e)
            self._units += es
            acc += sum(u.height for u in es)
            e += 1
        self._w_e1 = e

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
        self._top -= n
        iw = self._disp_w()
        while self._top < 0 and self._w_e0 > 0:
            self._extend_up(iw)
        if self._top < 0:
            self._top = 0

    def scroll_down(self, n: int = 3) -> None:
        self._follow = False
        self._top += n
        iw = self._disp_w()
        units = self._ensure_units(iw)
        while self._top >= len(units) and self._w_e1 < len(self.entries):
            self._extend_down(iw)
            units = self._units
        if self._top >= len(units):
            self._follow = True

    def scroll_home(self) -> None:
        self._follow = False
        self._build_at(self._disp_w(), 0)

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

    def _wrap_rows(self, iw: int) -> list:
        # \n 是硬断行(对齐 RichLog): 先按行拆, 再各自软折行, 否则整篇被当成一条流贪婪折叠。
        rows: list = []
        for piece in self.content.split("\n"):
            rows += wrap_segments(parse_markup(piece), iw) or [[]]
        return rows or [[]]

    def measure(self, width: int) -> int:
        # 空内容不占行(闲置时 #current/#status 归零, 不再各浪费 1 行纯空白)
        if not self.content.strip():
            return 0
        iw = max(1, width - 2)
        return max(1, len(self._wrap_rows(iw)))

    def draw(self, buf, x, y, w, h) -> None:
        iw = max(1, w - 2)
        rows = self._wrap_rows(iw)
        # 文本色读 CSS color 声明(#current → $text 正文色, #status → $accent),
        # 不再写死 thinking_text —— 正在生成的主回答不该比历史还弱
        cs = self.app._style_for(self) if self.app else None
        tok = (cs.color_token if cs else "") or "text"
        text_style = self.app.style(tok) if self.app else Style()
        # 流式贴底: 内容超过 h 行时只画末尾 h 行, 保证最新内容可见
        off = max(0, len(rows) - h)
        for r in range(h):
            if r + off >= len(rows):
                break
            segs = [(t, text_style.merge(s)) for t, s in rows[r + off]]
            buf.write_segments(x + 1, y + r, segs)


class SelectList(Widget):
    """可选列表(pi 风格 completion popup): items + 选中高亮 + 滚动窗口。

    items: [{"value", "description"?}]; up/down 移 selected(循环); Tab 取 selected_value 补全。
    """
    can_focus = False

    def __init__(self, items, id=None, max_visible=8):
        super().__init__(id)
        self.items = items
        self.selected = 0
        self.max_visible = max_visible
        self._filtered = list(items)

    def set_filter(self, prefix: str) -> None:
        self._filtered = [i for i in self.items
                          if i["value"].lower().startswith(prefix.lower())]
        self.selected = 0

    def move(self, d: int) -> None:
        if self._filtered:
            self.selected = (self.selected + d) % len(self._filtered)

    def selected_value(self):
        return self._filtered[self.selected]["value"] if self._filtered else None

    def measure(self, width: int) -> int:
        return min(len(self._filtered), self.max_visible)

    def draw(self, buf, x, y, w, h) -> None:
        iw = max(1, w - 2)
        text_style = self.app.style("text") if self.app else None
        n = len(self._filtered)
        if n == 0:
            segs = parse_markup("[dim]  无匹配命令[/dim]")
            buf.write_segments(x + 1, y, [(t, text_style.merge(s)) for t, s in (segs[0] if segs else [])])
            return
        start = max(0, min(self.selected - self.max_visible // 2, n - self.max_visible))
        end = min(start + self.max_visible, n)
        row = 0
        for i in range(start, end):
            if row >= h:
                break
            item = self._filtered[i]
            is_sel = (i == self.selected)
            label = f"/{item['value']}"
            desc = item.get("description", "")
            line = (f"[bold cyan]▸ {label}[/bold cyan]" if is_sel else f"  [cyan]{label}[/cyan]")
            if desc:
                line += f"  [dim]{desc}[/dim]"
            for rrow in (wrap_segments(parse_markup(line), iw) or [[]]):
                if row >= h:
                    break
                buf.write_segments(x + 1, y + row, [(t, text_style.merge(s)) for t, s in rrow])
                row += 1
        if n > self.max_visible:                      # 滚动指示
            info = f"[dim]  ({self.selected + 1}/{n})[/dim]"
            segs = parse_markup(info)
            buf.write_segments(x + 1, y + min(end - start, h) - 1,
                               [(t, text_style.merge(s)) for t, s in (segs[0] if segs else [])])


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
        self.history: list[str] = []   # 输入历史(App._input_submitted 提交时记录)
        self._hist_idx = 0             # 历史游标: len(history) = 实时输入位
        self._draft = ""               # 离开实时位时暂存草稿(down 回底恢复)

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
        if k == "__paste__":
            # 粘贴整段原样插入(保留换行), 不触发提交。沿用 _insert 既有 max_lines 显示行为。
            self._insert(key.char)
            if hasattr(self.app, "_on_input_changed"):
                self.app._on_input_changed(self.value)
            return True
        if key.is_printable():
            self._insert(key.char)
            if hasattr(self.app, "_on_input_changed"):
                self.app._on_input_changed(self.value)
            return True
        if k == "enter":
            if key.shift:
                self._insert("\n")
            else:
                # 补全浮层激活: Enter 先取选中项回填(残缺前缀 /mod 不当命令提交)
                sel = getattr(self.app, "_cmd_selectlist", lambda: None)()
                val = sel.selected_value() if sel is not None else None
                if val:
                    self.value = f"/{val} "
                    self.pos = len(self.value)
                self.app._input_submitted(self.Submitted(self.value, self))
                self.clear()
            return True
        if k == "ctrl+j":
            # 跨平台稳定换行键(终端解码侧已把裸 \n 归一到 ctrl+j)
            self._insert("\n"); return True
        if k == "backspace":
            self._delete_back()
            if hasattr(self.app, "_on_input_changed"):
                self.app._on_input_changed(self.value)
            return True
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
            if hasattr(self.app, "_completion_active") and self.app._completion_active():
                self.app._completion_move(-1); return True
            if "\n" in self.value:
                self._move_line(-1)            # 多行: 行移动
            else:
                self._history_move(-1)         # 单行: 翻输入历史
            return True
        if k == "down":
            if hasattr(self.app, "_completion_active") and self.app._completion_active():
                self.app._completion_move(1); return True
            if "\n" in self.value:
                self._move_line(1)
            else:
                self._history_move(1)
            return True
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

    def _history_move(self, d: int) -> None:
        """单行 up/down 翻输入历史: 回填 value 且 pos 置末尾; 翻到尽头不动。"""
        n = len(self.history)
        if d < 0 and self._hist_idx >= n:      # 首次离开实时位 → 暂存草稿
            self._draft = self.value
        idx = self._hist_idx + d
        if idx < 0 or idx > n:                 # 顶到底: 不动
            return
        self._hist_idx = idx
        self.value = self._draft if idx >= n else self.history[idx]
        self.pos = len(self.value)

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
        border = self.app.style("editor_border") if self._focused else self.app.style("border_muted")
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
                # base=dim 主题色: [dim] 本身不带 fg, CJK 续占位 cell 会漏 fg=None
                buf.write_markup(ix, y + 1 + r, f"[dim]{self.placeholder}[/dim]",
                                 base=self.app.style("dim"))
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
                # 反相该格(主题色互换: fg=page 底, bg=正文 —— 浅色下不再 1.37:1 隐形)
                cell = buf.grid[cy][cx_screen] if cy < buf.rows and cx_screen < buf.cols else None
                ch = cell.ch if cell and cell.ch else " "
                page = self.app.style("page_bg").fg
                txt = self.app.style("text").fg
                buf.put(cx_screen, cy, ch, Style(fg=page, bg=txt))   # 反相光标(主题化)


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
        # dim 文字一律 base=dim 主题色([dim] 标签本身不带 fg, 全透传终端默认色会糊底)
        dimst = self.app.style("dim")
        # 第1行: cwd(dim)
        cwd = os.path.basename(os.getcwd()) or os.getcwd()
        buf.write_markup(x, y, f"[dim] {cwd}[/dim]", base=dimst)
        # 第2行: 右侧 model · thinking, busy 时前挂 spinner
        model = getattr(self.app, "model_name", "") or ""
        agent = getattr(self.app, "agent", None)
        th = getattr(getattr(agent, "model", None), "thinking_level", None) if agent else None
        right = f"{model} · thinking {th or 'off'}"
        if getattr(self.app, "_agent_busy", False):
            # busy: spinner 帧用 accent 着色, 整行不再 [dim](旧 dim 把 spinner 压到 <3:1)
            frame = self._SPIN[int(time.time() * 8) % len(self._SPIN)]
            line = f"{frame} {right}"
            rx = max(x, x + w - len(line) - 1)
            buf.write(rx, y + 1, frame, self.app.style("accent"))
            buf.write_markup(rx + 2, y + 1, right, base=self.app.style("text"))
        else:
            # idle: 左侧键位提示(busy 时让位给 spinner, 不叠加两套忙碌视觉)。
            # 先画 hint 再画右侧 model —— 窄屏重叠时右侧状态优先保住
            buf.write_markup(x, y + 1,
                             "[dim]/help 帮助 · esc 中断 · ctrl+j 换行[/dim]", base=dimst)
            buf.write_markup(max(x, x + w - len(right) - 1), y + 1,
                             f"[dim]{right}[/dim]", base=dimst)
