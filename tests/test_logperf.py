"""REQ-G6 回归: transcript 容量上限 / 视口惰性物化 / resize 滚动锚。

P1: entries 有界(超限头部丢弃, 非全清); P2: _units 只物化视口附近窗口;
P3: 宽度变化后按内容锚重定位, 锚 entry 内容仍在视口。
"""
import re

from prism.tui.buffer import Buffer
from prism.tui.markup import Style
from prism.tui.widgets import RichLog


class _App:
    """给 widget.draw 喂 theme 的桩(不走完整 App)。"""
    from prism.tui.app import DARK as _DARK
    _themes = {"dark": _DARK}
    def style(self, t): return self._themes["dark"].get(t, Style())


def _log() -> RichLog:
    l = RichLog(id="t"); l.app = _App(); return l


def _screen(log: RichLog, rows: int, cols: int) -> str:
    b = Buffer(cols, rows); log.draw(b, 0, 0, cols, rows)
    return "\n".join("".join(c.ch for c in row) for row in b.grid)


# ── P1: 容量上限 ───────────────────────────────────────────────────────────
def test_entries_capped_head_dropped():
    log = RichLog()
    for i in range(3000):
        log.write("L%04d" % i)
    assert len(log.entries) == 2000          # 上限生效
    assert log.entries[0][1] == "L1000"      # 头部丢弃, 非全清
    assert log.entries[-1][1] == "L2999"     # 尾部(最新)保留


def test_entries_cap_applies_to_blocks_too():
    log = _log()
    for i in range(2100):
        log.user("m%04d" % i)
    assert len(log.entries) == 2000
    assert log.entries[0][1]["body"] == ["m0100"]


# ── P2: 视口惰性物化 ───────────────────────────────────────────────────────
def test_units_windowed_not_full():
    log = _log()
    for i in range(2500):
        log.write("L%04d token" % i)
    assert len(log.entries) == 2000
    _screen(log, 24, 80)                     # 贴底渲染
    assert len(log._units) <= 800
    log.scroll_home()
    _screen(log, 24, 80)                     # 滚顶渲染
    assert len(log._units) <= 800
    assert "L0500" in _screen(log, 24, 80)   # 顶部可见最老存活条目


def test_scroll_up_extends_window_content_continuous():
    log = _log()
    for i in range(300):
        log.write("L%04d" % i)
    _screen(log, 24, 80)
    for _ in range(40):                      # 连续上滚越过窗口头: 增补物化, 不丢内容
        log.scroll_up(5)
    s = _screen(log, 24, 80)
    assert re.search(r"L\d{4}", s)
    assert len(log._units) <= 800 + 24 * 3   # 回收后有界(单次增补余量内)


# ── P3: resize 滚动锚 ──────────────────────────────────────────────────────
def test_resize_keeps_anchor_entry_visible():
    log = _log()
    for i in range(40):
        log.write("T%02d " % i + "x" * 90)
    log.scroll_end(); _screen(log, 24, 80)
    for _ in range(12):
        log.scroll_up(1)
    s80 = _screen(log, 24, 80)
    m = re.search(r"T\d\d", s80)
    assert m, s80[:200]
    anchor = m.group(0)
    log._invalidate()
    s40 = _screen(log, 24, 40)               # 宽度减半, 同一 _top 已指向不同内容
    assert anchor in s40, (anchor, s40[:300])


def test_streaming_while_scrolled_up_does_not_jump():
    log = _log()
    for i in range(100):
        log.write("L%04d" % i)
    log.scroll_end(); _screen(log, 24, 80)
    for _ in range(30):
        log.scroll_up(1)
    top = re.search(r"L\d{4}", _screen(log, 24, 80)).group(0)
    for i in range(100, 160):                # 流式追加: 视口不跳
        log.write("L%04d" % i)
    assert re.search(r"L\d{4}", _screen(log, 24, 80)).group(0) == top
