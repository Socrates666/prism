"""文本内核回归: TAB 展开 / 词边界折行 / 零宽字符占列(REQ-G1 批判轮4实证固化)。"""
from prism.tui.buffer import Buffer
from prism.tui.markup import Style, char_width, parse_markup, wrap_segments


def _rowtext(row) -> str:
    out = ""
    for seg in row:
        out += seg[0] if isinstance(seg, tuple) else str(seg)
    return out


# ── T1: TAB 按 8 列 tab-stop 展开, 不再静默蒸发 ────────────────────────────
def test_tab_expansion():
    b = Buffer(30, 2)
    b.write(0, 0, "a\tb", Style.empty())
    b.write(0, 1, "\t\trm -f *.o", Style.empty())
    row0 = "".join(c.ch for c in b.grid[0])
    row1 = "".join(c.ch for c in b.grid[1])
    assert b.grid[0][8].ch == "b", row0          # a 在 0, tab 蹦到 8
    assert b.grid[1][16].ch == "r", row1         # 两个 tab 蹦到 16
    assert row1.strip().startswith("rm -f"), row1


# ── T2: 英文单词不被劈开 ───────────────────────────────────────────────────
def test_word_wrap_keeps_words_intact():
    rows = wrap_segments(
        parse_markup("The configuration parameter determines how the renderer processes long words"), 20)
    texts = [_rowtext(r) for r in rows]
    assert any("configuration" in t for t in texts), texts
    assert any("parameter" in t for t in texts), texts
    assert any("renderer" in t for t in texts), texts


def test_word_wrap_long_token_hard_split():
    rows2 = wrap_segments(parse_markup("supercalifragilisticexpialidocious is long"), 10)
    joined2 = "".join(_rowtext(r) for r in rows2)
    assert "supercalifragilisticexpialidocious" in joined2, joined2  # 硬切但不丢字符


def test_word_wrap_cjk_and_tag_no_leak():
    rows3 = wrap_segments(parse_markup("这是很长的中文句子必须折行显示才行呢"), 8)
    assert len(rows3) >= 2, [_rowtext(r) for r in rows3]             # CJK 任意可断
    rows4 = wrap_segments(parse_markup("[bold cyan]跨行标签内容测试[/bold cyan]"), 6)
    t4 = "".join(_rowtext(r) for r in rows4)
    assert "[" not in t4 and "bold" not in t4, t4                    # 标签不泄漏


# ── T3: 零宽字符(组合附标/ZWJ/VS16)占 0 列 ─────────────────────────────────
def test_zero_width_chars():
    assert char_width("\u0301") == 0     # 组合重音
    assert char_width("\u200d") == 0     # ZWJ
    assert char_width("\ufe0f") == 0     # VS16
    assert char_width("中") == 2
    assert char_width("a") == 1
    b = Buffer(20, 1)
    b.write(0, 0, "cafe\u0301XYZ", Style.empty())
    assert b.grid[0][4].ch == "X", "".join(c.ch for c in b.grid[0])  # 组合符不占列
    b2 = Buffer(20, 1)
    b2.write(0, 0, "a\u200db", Style.empty())
    assert b2.grid[0][1].ch == "b", "".join(c.ch for c in b2.grid[0])
    b3 = Buffer(20, 1)
    b3.write(0, 0, "\U0001F468\u200D\U0001F469\u200D\U0001F467Z", Style.empty())
    xs = [x for x in range(20) if b3.grid[0][x].ch == "Z"]
    assert xs and 2 <= xs[0] <= 6, xs   # emoji ZWJ 序列 ≈ 6 列而非 8
