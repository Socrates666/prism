"""启动横幅三模式 + 聚焦输入框边框色(用户裁决: pi-faithful 彩色观感回归, 批判方案降为开关)。

固化:
  [B1] PRISM_BANNER=art → 5 行分光字母画 + 光谱五色着色 + ◆ 单行(可发现性保留)
  [B2] PRISM_BANNER=line → 单行, 无字母画(小屏紧凑, 批判轮1 的屏占关切)
  [B3] PRISM_BANNER=off → 无横幅
  [B4] 默认(未设) → 无 tty 环境按 24 行降级 line(测试环境即此), 不出字母画
  [B5] 边框: 默认 DeepPink(255,20,147); PRISM_INPUT_BORDER=accent → 主题 accent 无粉
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("PRISM_INTUITION", "off")

from prism.shell import PrismApp
from prism.tui import markup


def _frame(app):
    app._drain()
    return app._render_frame(24, 80)


def _fgs(buf):
    return {c.style.fg for row in buf.grid for c in row if not c.cont}


def test_b1_art_banner(monkeypatch):
    monkeypatch.setenv("PRISM_BANNER", "art")
    app = PrismApp(); app.run(headless=True)
    out = app.render_to_string(24, 80)
    assert "█" in out, "字母画未渲染"
    assert "◆ Prism" in out, "art 模式仍应带单行(可发现性)"
    fgs = _fgs(_frame(app))
    for rgb in ((255, 23, 68), (255, 208, 0), (0, 255, 123), (0, 212, 255), (200, 80, 255)):
        assert rgb in fgs, f"光谱色 {rgb} 缺失"
    markup.set_color_theme("dark")


def test_b2_line_banner(monkeypatch):
    monkeypatch.setenv("PRISM_BANNER", "line")
    app = PrismApp(); app.run(headless=True)
    out = app.render_to_string(24, 80)
    assert "◆ Prism" in out
    assert "█" not in out, "line 模式不应有字母画"


def test_b3_off_banner(monkeypatch):
    monkeypatch.setenv("PRISM_BANNER", "off")
    app = PrismApp(); app.run(headless=True)
    out = app.render_to_string(24, 80)
    assert "█" not in out, "off 模式不应有字母画"
    assert "/help 查看指令" not in out, "off 模式不应有横幅行"
    # Header 标题栏的 ◆ Prism 是常驻可发现性元素, 不受横幅开关影响


def test_b4_default_small_screen_line(monkeypatch):
    monkeypatch.delenv("PRISM_BANNER", raising=False)
    app = PrismApp(); app.run(headless=True)   # 无 tty → get_terminal_size 兜底 24 行 → line
    out = app.render_to_string(24, 80)
    assert "◆ Prism" in out and "█" not in out


def test_b5_border_pink_default_and_accent_optout(monkeypatch):
    try:
        monkeypatch.delenv("PRISM_INPUT_BORDER", raising=False)
        app = PrismApp(); app.run(headless=True)
        buf = _frame(app)
        assert (255, 20, 147) in _fgs(buf), "默认边框应 DeepPink"
        monkeypatch.setenv("PRISM_INPUT_BORDER", "accent")
        app2 = PrismApp(); app2.run(headless=True)
        buf2 = _frame(app2)
        assert (255, 20, 147) not in _fgs(buf2), "accent 模式不应有粉"
        assert (138, 190, 183) in _fgs(buf2), "accent 模式应为主题 accent"
    finally:
        markup.set_color_theme("dark")
