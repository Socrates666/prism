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
import os
import unicodedata


# ── 色彩能力探测(truecolor → 256 → 单色 降级链) ─────────────────────────
# 默认偏 truecolor(与历史行为一致); 256 色终端自动降级; PRISM_COLOR 可强制。
def _detect_color_mode() -> int:
    """0=单色 1=256色 2=truecolor。"""
    env = os.environ.get("PRISM_COLOR", "").lower()
    if env in ("truecolor", "24bit", "2"):
        return 2
    if env in ("256", "1"):
        return 1
    if env in ("mono", "0", "off", "none"):
        return 0
    if os.environ.get("NO_COLOR"):
        return 0
    ct = os.environ.get("COLORTERM", "").lower()
    if "truecolor" in ct or "24bit" in ct:
        return 2
    if os.environ.get("WT_SESSION"):              # Windows Terminal
        return 2
    if os.environ.get("TERM_PROGRAM") in ("vscode", "ghostty", "wezterm", "iTerm.app"):
        return 2
    if "256color" in os.environ.get("TERM", ""):
        return 1                                  # 256 色终端: RGB 自动降级
    return 2                                      # 无明确信号时保持 truecolor(不回退)


_COLOR_MODE = _detect_color_mode()


def color_mode() -> int:
    """当前色彩能力(诊断用): 0=单色 1=256色 2=truecolor。"""
    return _COLOR_MODE


def _rgb_to_256(c) -> int:
    """RGB → 最近 xterm-256 索引(6×6×6 立方体 + 灰阶, 两候选取近)。"""
    r, g, b = c
    cube = lambda v: round(v / 255 * 5)           # noqa: E731
    idx = 16 + 36 * cube(r) + 6 * cube(g) + cube(b)
    gray = round((r + g + b) / 3 / 255 * 23) + 232

    def dist(i: int) -> int:
        if i >= 232:
            v = (i - 232) * 255 // 23
            rgb = (v, v, v)
        else:
            t = i - 16
            rgb = (t // 36 * 51, t // 6 % 6 * 51, t % 6 * 51)
        return (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2

    return min((idx, gray), key=dist)


def char_width(ch: str) -> int:
    """单字符显示宽度(1 或 2)。控制字符按 0。"""
    if not ch or ord(ch) < 32:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1

# ── 颜色名 → pi dark 主题 RGB(从 pi dark.json 对齐) ─────────────────────────
# sgr() 把 RGB 转 38;2;r;g;b(truecolor), 256 索引转 38;5;i, 基本色转 30+i
_COLOR = {
    "black": (0, 0, 0), "red": (204, 102, 102), "green": (181, 189, 104),
    "yellow": (255, 255, 0), "blue": (95, 135, 255), "magenta": (149, 117, 205),
    "cyan": (0, 215, 255), "white": (212, 212, 212),
    "accent": (138, 190, 183), "grey": (128, 128, 128), "gray": (128, 128, 128),
    "default": None,
}

_STYLE_ATTR = {"bold", "italic", "dim", "underline"}


def _fg_code(c) -> str | None:
    """颜色(int 索引 / RGB 元组) → ANSI fg 码。RGB 按色彩能力降级(truecolor/256/无)。"""
    if c is None:
        return None
    if isinstance(c, tuple):
        if _COLOR_MODE >= 2:
            return f"38;2;{c[0]};{c[1]};{c[2]}"     # truecolor
        if _COLOR_MODE == 1:
            return f"38;5;{_rgb_to_256(c)}"          # 256 色终端降级
        return None                                   # 单色
    if 0 <= c < 8:
        return str(30 + c)
    if 8 <= c < 16:
        return str(90 + c - 8)
    return f"38;5;{c}"                            # 256 色


def _bg_code(c) -> str | None:
    f = _fg_code(c)
    if f is None:
        return None
    if f.startswith("38;"):
        return "48;" + f[3:]                      # 38;2;...→48;2;... / 38;5;...→48;5;...
    if f.startswith("3"):
        return "4" + f[1:]                        # 30..37 → 40..47
    if f.startswith("9"):
        return "10" + f[1:]                       # 90..97 → 100..107
    return f


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
            codes.append(_fg_code(self.fg))
        if self.bg is not None:
            codes.append(_bg_code(self.bg))
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
        elif p.startswith("#") and len(p) == 7:
            h = p[1:]
            delta = replace(delta, fg=(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
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
    """把样式段排成 width 列的若干行(按显示宽度, 支持全宽 CJK)。跨行保留样式。"""
    if width <= 0:
        return [list(segs)] if segs else [[]]
    rows: list[list[tuple[str, Style]]] = [[]]
    col = 0
    for text, style in segs:
        for ch in text:
            cw = char_width(ch)
            if rows[-1] and col + cw > width:   # 放不下且本行非空 → 换行
                rows.append([]); col = 0
            rows[-1].append((ch, style)); col += cw
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
