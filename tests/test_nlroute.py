"""REQ-B 验收: 用户输入方括号被 markup 吞掉 + /help 自吞参数语法 + 自然语言报错无出路。

三个同根问题(markup 解析器把 `[...]` 当标签 / 默认路由无引导)的黑盒回归, 固化为 pytest。
直接驱动 headless PrismApp: 喂键 → _drain → _render_frame → 断言整屏像素。
"""
from prism.shell import PrismApp
from prism.tui.terminal import Key


def _screen(app, rows, cols):
    """渲染整帧 → 拍平成纯文本(逐行拼字符)。"""
    buf = app._render_frame(rows, cols)
    return "\n".join("".join(c.ch for c in row) for row in buf.grid)


def _submit(app, text):
    """填入 dock 并回车提交。"""
    dock = app.query_one("#dock")
    dock.value = text
    dock.pos = len(text)
    dock.on_key(Key(key="enter", char=""))
    app._drain()


def test_b1_user_brackets_not_swallowed():
    """用户回显里的 arr[0] / [i] / [TODO] 不能被 markup 当标签吞掉。"""
    app = PrismApp(); app.run(headless=True)
    _submit(app, "看下 arr[0] 和 arr[i] 哪里越界 [TODO] 修一下")
    screen = _screen(app, 24, 80)
    assert "arr[0]" in screen, "bracket swallowed"
    assert "[TODO]" in screen, "TODO swallowed"
    assert "[i]" in screen, "[i] swallowed"


def test_b2_help_param_syntax_visible():
    """/help 输出里命令 DESC 的 [n|none] / [name] 参数语法必须可见。"""
    app = PrismApp(); app.run(headless=True)
    _submit(app, "/help")
    screen = _screen(app, 50, 100)
    assert "[n|none]" in screen, "help param syntax swallowed"
    assert "[name]" in screen, "help [name] swallowed"


def test_b3_natural_language_gives_guidance():
    """自然语言误入 Python 直通 → NameError/SyntaxError + @Prism / /help 引导。"""
    app = PrismApp(); app.run(headless=True)
    _submit(app, "怎么重构这个函数")
    screen = _screen(app, 24, 80)
    assert "NameError" in screen or "SyntaxError" in screen, screen
    assert "@Prism" in screen, "no guidance to @Prism route"
    assert "/help" in screen, "no /help pointer"


def test_b4_placeholder_advertises_routes():
    """空输入区无占位提示(用户裁决 2026-08-14): 只留 ❯ 提示符, 路由引导由报错态(B3)承担。"""
    app = PrismApp(); app.run(headless=True)
    dock = app.query_one("#dock")
    assert dock.placeholder == "", "placeholder 应为空(用户裁决)"
    screen = _screen(app, 24, 80)
    assert "❯" in screen, "❯ 提示符缺失"
    assert "问事" not in screen and "直接输入跑 Python" not in screen, "占位提示残留"
