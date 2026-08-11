"""离屏 cell 缓冲 + box 绘制 + 按行 diff 刷新。零依赖。

渲染策略(仿 pi): 每行末追加全 SGR reset, 样式不跨行继承。只在"该行有变化"时
重画该行, 最小化输出、避免闪烁。支持 CJK 全宽字符。
"""
from __future__ import annotations
import unicodedata
from dataclasses import dataclass
from .markup import Style, parse_markup, wrap_segments


def char_width(ch: str) -> int:
    """单字符显示宽度(1 或 2)。控制字符按 0。"""
    if not ch or ord(ch) < 32:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


@dataclass
class Cell:
    ch: str = " "
    style: Style = None  # type: ignore[assignment]
    cont: bool = False   # 宽字符的后续占位列


def _blank() -> Cell:
    return Cell(ch=" ", style=Style.empty())


class Buffer:
    """(cols × rows) 离屏网格。坐标系: x=列(0..cols-1), y=行(0..rows-1)。"""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = max(1, cols)
        self.rows = max(1, rows)
        self.grid: list[list[Cell]] = [[_blank() for _ in range(self.cols)]
                                       for _ in range(self.rows)]

    # ── 基元 ─────────────────────────────────────────────────────────────
    def put(self, x: int, y: int, ch: str, style: Style) -> None:
        """放一个字符(自动处理宽字符占两列)。越界静默裁剪。"""
        if y < 0 or y >= self.rows or x < 0 or x >= self.cols:
            return
        w = char_width(ch)
        if w == 0:
            return
        cell = Cell(ch=ch, style=style)
        self.grid[y][x] = cell
        if w == 2:
            if x + 1 < self.cols:
                self.grid[y][x + 1] = Cell(ch="", style=style, cont=True)
            else:  # 宽字符贴边放不下 → 退一格
                self.grid[y][x] = _blank()
                if x - 1 >= 0:
                    self.grid[y][x - 1] = Cell(ch=ch, style=style)
                    # 理论上还需标记 x-2, 但贴边情况罕见, 容忍

    def write(self, x: int, y: int, text: str, style: Style) -> int:
        """从 (x,y) 起写一段纯文本(已剥 markup 或本身无 markup)。返回结束列。"""
        cx = x
        for ch in text:
            if cx >= self.cols:
                break
            self.put(cx, y, ch, style)
            cx += char_width(ch) or 1
        return cx

    def write_segments(self, x: int, y: int, segs: list[tuple[str, Style]]) -> int:
        """写样式段列表(markup 已 parse)。返回结束列。"""
        cx = x
        for text, style in segs:
            for ch in text:
                if cx >= self.cols:
                    return cx
                self.put(cx, y, ch, style)
                cx += char_width(ch) or 1
        return cx

    def write_markup(self, x: int, y: int, markup: str, base: Style | None = None) -> int:
        """写一段 markup 文本(自动 parse)。"""
        segs = parse_markup(markup)
        if base is not None:
            segs = [(t, base.merge(s)) for t, s in segs]
        return self.write_segments(x, y, segs)

    def fill_row(self, y: int, ch: str = " ", style: Style | None = None) -> None:
        if y < 0 or y >= self.rows:
            return
        st = style or Style.empty()
        for x in range(self.cols):
            self.grid[y][x] = Cell(ch=ch, style=st) if char_width(ch) else _blank()

    def clear_row(self, y: int) -> None:
        self.fill_row(y, " ")

    def clear(self) -> None:
        for y in range(self.rows):
            self.clear_row(y)

    # ── box ──────────────────────────────────────────────────────────────
    def box(self, x: int, y: int, w: int, h: int, *,
            title: str = "", border_style: Style | None = None,
            title_style: Style | None = None) -> None:
        """圆角边框, 顶行居中写 title。w/h 含边框。"""
        if w < 2 or h < 2:
            return
        bs = border_style or Style.empty()
        ts = title_style or bs
        x2, y2 = x + w - 1, y + h - 1
        # 四角
        self.put(x, y, "╭", bs);   self.put(x2, y, "╮", bs)
        self.put(x, y2, "╰", bs);  self.put(x2, y2, "╯", bs)
        # 水平
        for cx in range(x + 1, x2):
            self.put(cx, y, "─", bs)
            self.put(cx, y2, "─", bs)
        # 垂直
        for cy in range(y + 1, y2):
            self.put(x, cy, "│", bs)
            self.put(x2, cy, "│", bs)
        # title
        if title:
            t = f" {title} "
            # 居中, 但别超出
            tx = x + max(1, (w - len(t)) // 2)
            self.write(tx, y, t, ts)

    # ── 内容裁剪辅助 ─────────────────────────────────────────────────────
    def clear_region(self, x: int, y: int, w: int, h: int) -> None:
        for ry in range(y, min(y + h, self.rows)):
            for rx in range(x, min(x + w, self.cols)):
                self.grid[ry][rx] = _blank()


# ── diff 渲染 ─────────────────────────────────────────────────────────────
ESC = "\x1b["


def _row_to_ansi(row: list[Cell]) -> str:
    """一行 cell → ANSI 字符串。仅在样式变化时发 SGR, 行末 reset。"""
    parts: list[str] = []
    cur_sgr: str | None = None
    for cell in row:
        if cell.cont:
            continue
        sgr = cell.style.sgr()
        if sgr != cur_sgr:
            parts.append(f"{ESC}{sgr}m")
            cur_sgr = sgr
        parts.append(cell.ch if cell.ch else " ")
    parts.append(f"{ESC}0m")
    return "".join(parts)


def _row_equal(a: list[Cell], b: list[Cell]) -> bool:
    if len(a) != len(b):
        return False
    for ca, cb in zip(a, b):
        if ca.ch != cb.ch or ca.style != cb.style:
            return False
    return True


def render_diff(prev: Buffer, cur: Buffer) -> str:
    """生成把 prev 变成 cur 的最小 ANSI 串。prev 为 None 时全画。"""
    out: list[str] = []
    for y in range(cur.rows):
        prow = prev.grid[y] if prev and y < prev.rows else None
        crow = cur.grid[y]
        if prow is not None and _row_equal(prow, crow):
            continue
        out.append(f"{ESC}{y + 1};1H")  # 移到该行首列
        out.append(_row_to_ansi(crow))
    return "".join(out)


def render_plain(buf: Buffer) -> str:
    """无 ANSI 的纯文本快照(测试用)。"""
    lines = []
    for row in buf.grid:
        line = []
        for cell in row:
            if cell.cont:
                continue
            line.append(cell.ch if cell.ch else " ")
        lines.append("".join(line).rstrip())
    return "\n".join(lines)
