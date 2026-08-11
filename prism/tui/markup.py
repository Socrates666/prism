"""rich 风格 markup → 样式段。零依赖(纯标准库)。

支持 prism 实际使用的子集:
  - 样式: bold / italic / dim / underline
  - 颜色名: black red green yellow blue magenta cyan white (+ 数字 SGR 码)
  - 组合: ``[bold cyan]``, ``[dim italic]``, ``[red bold]``
  - 闭合: ``[/]``(弹一层) 或 ``[/bold cyan]``(按用法也当弹一层)
  - 转义: ``\\\\[`` → 字面 ``[``

语义: 栈式嵌套, 当前有效样式 = 栈上各层 delta 的归约(bold 等取并集, 颜色取栈顶最近的)。
与 rich 行为一致到 prism 用到的程度。
"""
from __future__ import annotations
from dataclasses import dataclass, replace

# ── 颜色名 → 256 色索引(0..255) ───────────────────────────────────────────
# sgr() 再把索引转成 ANSI 码: <8 → 30+i, <16 → 90+(i-8), 否则 38;5;i
_COLOR = {
    "black": 0, "red": 1, "green": 2, "yellow": 3,
    "blue": 4, "magenta": 5, "cyan": 6, "white": 7,
    "bright_black": 8, "bright_red": 9, "bright_green": 10, "bright_yellow": 11,
    "bright_blue": 12, "bright_magenta": 13, "bright_cyan": 14, "bright_white": 15,
    "grey": 240, "gray": 240,
    "default": None,
}

_STYLE_ATTR = {"bold", "italic", "dim", "underline"}


def _index_to_fg(idx: int) -> str:
    if 0 <= idx < 8:
        return str(30 + idx)
    if 8 <= idx < 16:
        return str(90 + idx - 8)
    return f"38;5;{idx}"


def _index_to_bg(idx: int) -> str:
    if 0 <= idx < 8:
        return str(40 + idx)
    if 8 <= idx < 16:
        return str(100 + idx - 8)
    return f"48;5;{idx}"


@dataclass(frozen=True)
class Style:
    """一段文本的样式。None 表示不指定(透传下层)。"""
    bold: bool = False
    italic: bool = False
    dim: bool = False
    underline: bool = False
    fg: int | None = None
    bg: int | None = None

    @staticmethod
    def empty() -> "Style":
        return Style()

    def merge(self, delta: "Style") -> "Style":
        """把一层 delta 合进当前(下层=self, delta 压在上面)。"""
        return Style(
            bold=self.bold or delta.bold,
            italic=self.italic or delta.italic,
            dim=self.dim or delta.dim,
            underline=self.underline or delta.underline,
            fg=delta.fg if delta.fg is not None else self.fg,
            bg=delta.bg if delta.bg is not None else self.bg,
        )

    def sgr(self) -> str:
        """该样式对应的 SGR 参数串(不含 \\x1b[ 与 m)。空样式 → '0'。"""
        if self == Style.empty():
            return "0"
        codes: list[str] = []
        if self.bold:
            codes.append("1")
        if self.dim:
            codes.append("2")
        if self.italic:
            codes.append("3")
        if self.underline:
            codes.append("4")
        if self.fg is not None:
            codes.append(_index_to_fg(self.fg))
        if self.bg is not None:
            codes.append(_index_to_bg(self.bg))
        return ";".join(codes) if codes else "0"


# ── 解析 ─────────────────────────────────────────────────────────────────
def _parse_tag(body: str) -> Style:
    """``bold cyan`` → Style(bold, fg=cyan)。闭合标签体以 / 开头时返回 None。"""
    delta = Style()
    for part in body.split():
        p = part.strip().lower()
        if p in _STYLE_ATTR:
            delta = replace(delta, **{p: True})
        elif p in _COLOR:
            v = _COLOR[p]
            if v is not None:
                delta = replace(delta, fg=v)
        elif p.isdigit():
            delta = replace(delta, fg=int(p))
        # 未知属性忽略(宽容)
    return delta


def parse_markup(text: str) -> list[tuple[str, Style]]:
    """把 markup 文本解析成 (纯文本片段, 有效样式) 列表。"""
    out: list[tuple[str, Style]] = []
    stack: list[Style] = []          # delta 栈
    buf = []
    i, n = 0, len(text)

    def current() -> Style:
        cur = Style.empty()
        for d in stack:
            cur = cur.merge(d)
        return cur

    def flush():
        if buf:
            out.append(("".join(buf), current()))
            buf.clear()

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] == "[":
            buf.append("[")
            i += 2
            continue
        if ch == "[":
            j = text.find("]", i + 1)
            if j != -1:
                body = text[i + 1:j]
                if body.startswith("/"):
                    flush()
                    if stack:
                        stack.pop()
                else:
                    flush()
                    stack.append(_parse_tag(body))
                i = j + 1
                continue
        buf.append(ch)
        i += 1
    flush()
    return out


# ── 换行(保留样式) ───────────────────────────────────────────────────────
def wrap_segments(segs: list[tuple[str, Style]], width: int) -> list[list[tuple[str, Style]]]:
    """把样式段列表排成 width 列的若干行。跨行处保留样式。"""
    if width <= 0:
        return [[s] if s[0] else [] for s in segs] or [[]]
    rows: list[list[tuple[str, Style]]] = [[]]
    col = 0

    def push(text: str, style: Style):
        nonlocal col
        rows[-1].append((text, style))
        col += len(text)

    for text, style in segs:
        k = 0
        while k < len(text):
            space = width - col
            if space <= 0:
                rows.append([])
                col = 0
                space = width
            chunk = text[k:k + space]
            push(chunk, style)
            k += len(chunk)
            if col >= width:
                rows.append([])
                col = 0
    if not rows[-1] and len(rows) > 1:
        # trailing empty line artifact
        pass
    return rows


def strip_markup(text: str) -> str:
    """去掉所有 markup 标签, 只留纯文本(用于宽度计算 / footer)。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] == "[":
            out.append("[")
            i += 2
            continue
        if ch == "[":
            j = text.find("]", i + 1)
            if j != -1:
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)
