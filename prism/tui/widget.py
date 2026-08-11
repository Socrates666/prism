"""Widget 基类 + 纵向 flex 布局(textual 同款心智: compose/measure/draw)。

高度模型(对齐 textual CSS):
  - fix  → 固定行
  - auto → widget.measure(width) 决定(内容驱动)
  - fr   → 弹性, 吃掉剩余空间(通常只有一个 fr widget = transcript)
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import App
    from .buffer import Buffer


class Widget:
    can_focus: bool = True

    def __init__(self, id: str | None = None) -> None:
        self.id = id
        self._focused = False
        self.app: "App | None" = None

    # ── 生命周期 ─────────────────────────────────────────────────────────
    def mount(self, app: "App") -> None:
        self.app = app

    def compose(self) -> list["Widget"]:
        return []

    def measure(self, width: int) -> int:
        """auto 高度: 内容需要多少行。默认 1。"""
        return 1

    def draw(self, buf: "Buffer", x: int, y: int, w: int, h: int) -> None:
        raise NotImplementedError

    # ── 焦点 / 输入 ──────────────────────────────────────────────────────
    def focus(self) -> None:
        self._focused = True

    def blur(self) -> None:
        self._focused = False

    def on_key(self, key) -> bool:
        """返回 True 表示吃掉该按键。"""
        return False


def layout(widgets: list[Widget], styles, total_h: int, width: int) -> list[tuple[int, int, int, int]]:
    """纵向 flex 布局。返回每个 widget 的 (x, y, w, h)。"""
    regions: list[tuple[int, int, int, int]] = []
    # 1. 算各自需求高度
    needs: list[int] = []
    fr_idx: list[int] = []
    fixed_sum = 0
    for i, w_ in enumerate(widgets):
        cs = styles(w_)
        kind, n = cs.height
        if kind == "fix":
            hgt = max(cs.min_height, n)
            needs.append(hgt)
            fixed_sum += hgt
        elif kind == "auto":
            hgt = max(cs.min_height, w_.measure(width))
            needs.append(hgt)
            fixed_sum += hgt
        else:  # fr
            needs.append(0)
            fr_idx.append(i)
    # 2. 分配 fr 剩余
    remaining = total_h - fixed_sum
    if fr_idx:
        share = max(0, remaining) // len(fr_idx)
        for i in fr_idx:
            needs[i] = share
    # 3. 堆叠
    y = 0
    for i, w_ in enumerate(widgets):
        hgt = needs[i]
        regions.append((0, y, width, hgt))
        y += hgt
    return regions
