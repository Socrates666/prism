"""极小子集 CSS 解析(textual 用 CSS 驱动布局, 我们保留同构心智)。

支持的选择器: ``#id`` 与标签名(如 ``Screen``)。
支持的属性:
  - ``height: <int> | auto | <int>fr``
  - ``min-height: <int>``
  - ``border: round | none``  (颜色由 ``border-color: <token>`` 给, 缺省 accent)
  - ``border-color: $accent | $primary | <name>``
  - ``padding: <v> <h>``  (只取水平 h)
  - ``color: <token>``
  - ``layout: vertical``
$token($accent/$primary/$text) 由 App 主题解析成颜色。
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ComputedStyle:
    height: tuple[str, int] = ("auto", 0)   # ("fix",n)/("auto",0)/("fr",k)
    min_height: int = 0
    max_height: int = 0                     # 0 = 无上限(auto widget 内容截断上界)
    border: bool = False
    border_token: str = "accent"
    padding_x: int = 0
    color_token: str = ""
    layout: str = "vertical"


@dataclass
class Stylesheet:
    by_id: dict[str, ComputedStyle] = field(default_factory=dict)
    by_tag: dict[str, ComputedStyle] = field(default_factory=dict)

    def for_widget(self, wid: str | None, tag: str) -> ComputedStyle:
        """标签规则打底, id 规则覆盖(textual 同款优先级)。"""
        base = ComputedStyle()
        if tag in self.by_tag:
            base = _merge(base, self.by_tag[tag])
        if wid and wid in self.by_id:
            base = _merge(base, self.by_id[wid])
        return base


def _merge(a: ComputedStyle, b: ComputedStyle) -> ComputedStyle:
    return ComputedStyle(
        height=b.height if b.height != ("auto", 0) else a.height,
        min_height=b.min_height or a.min_height,
        max_height=b.max_height or a.max_height,
        border=b.border or a.border,
        border_token=b.border_token if b.border else a.border_token,
        padding_x=b.padding_x if b.padding_x else a.padding_x,
        color_token=b.color_token or a.color_token,
        layout=b.layout or a.layout,
    )


def _parse_height(v: str) -> tuple[str, int]:
    v = v.strip().lower()
    if v == "auto":
        return ("auto", 0)
    if v.endswith("fr"):
        return ("fr", int(v[:-2]) if v[:-2] else 1)
    return ("fix", int(v))


def parse_css(css: str) -> Stylesheet:
    sheet = Stylesheet()
    # 去注释
    css = "\n".join(l for l in css.splitlines() if not l.strip().startswith("/*"))
    for block in css.split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        decls: dict[str, str] = {}
        for decl in body.split(";"):
            decl = decl.strip()
            if not decl or ":" not in decl:
                continue
            k, v = decl.split(":", 1)
            decls[k.strip().lower()] = v.strip()
        cs = ComputedStyle()
        if "height" in decls:
            cs.height = _parse_height(decls["height"])
        if "min-height" in decls:
            cs.min_height = int(decls["min-height"])
        if "max-height" in decls:
            cs.max_height = int(decls["max-height"])
        b = decls.get("border", "").strip().lower()
        if b:
            cs.border = b != "none"
        bc = decls.get("border-color", "").strip()
        if bc.startswith("$"):
            bc = bc[1:]
        if bc:
            cs.border_token = bc
        if "padding" in decls:
            nums = decls["padding"].split()
            cs.padding_x = int(nums[1]) if len(nums) >= 2 else int(nums[0])
        col = decls.get("color", "").strip()
        if col.startswith("$"):
            col = col[1:]
        cs.color_token = col
        if "layout" in decls:
            cs.layout = decls["layout"].strip().lower()
        for sel in head.split(","):
            sel = sel.strip()
            if not sel:
                continue
            if sel.startswith("#"):
                sheet.by_id[sel[1:]] = _merge(sheet.by_id.get(sel[1:], ComputedStyle()), cs)
            else:
                sheet.by_tag[sel] = _merge(sheet.by_tag.get(sel, ComputedStyle()), cs)
    return sheet
