"""REQ-G5 验收: 命令表单一事实源 + /help 四段式 + ext 根不赌 cwd + 重试/错误可见。

黑盒回归, 直接驱动 headless PrismApp: 喂键 → _drain → _render_frame → 断言整屏像素。
"""
from prism.shell import PrismApp
from prism.tui.terminal import Key


def _screen(app, rows=60, cols=120):
    buf = app._render_frame(rows, cols)
    return "\n".join("".join(c.ch for c in row) for row in buf.grid)


def _submit(app, text):
    dock = app.query_one("#dock")
    dock.value = text
    dock.pos = len(text)
    dock.on_key(Key(key="enter", char=""))
    app._drain()


def _app():
    app = PrismApp(); app.run(headless=True)
    return app


def _text(app):
    log = app.query_one("#transcript")
    return "\n".join(m for k, m in log.entries if k == "line")


def test_g5_all_commands_single_source():
    """内置 revert/backups + ext 指令合入同一张表; 未知指令报错也读它。"""
    app = _app()
    allc = app.all_commands()
    for n in ("revert", "backups", "help", "model"):
        assert n in allc, n
    assert allc["revert"], "builtin DESC missing"
    _submit(app, "/nosuchcmd")
    joined = _text(app)
    assert "/revert" in joined and "/backups" in joined and "/help" in joined


def test_g5_help_four_sections():
    """/help 四段式: 全量指令(含内置) + 按键 + 输入路由 + 概念。"""
    app = _app()
    _submit(app, "/help")
    screen = _screen(app)
    for tok in ("/revert", "/backups", "/help", "/model"):
        assert tok in screen, tok + " missing in /help"
    assert "按键" in screen, "keybindings section missing"
    low = screen.lower()
    assert "esc" in low and "tab" in low, "esc/tab not documented"
    assert "ctrl" in low, "ctrl bindings not documented"
    assert "直觉" in screen, "concept section missing"
    assert "@Prism" in screen or "路由" in screen, "routing section missing"


def test_g5_ext_root_survives_cwd_change(tmp_path, monkeypatch):
    """cwd 离开项目根: 包根优先解析, 指令照常加载且无假警告。"""
    monkeypatch.delenv("PRISM_EXT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    from prism.commands import ext_root
    assert (ext_root() / "commands").is_dir()
    app = PrismApp(); app.run(headless=True)
    app._drain()
    assert len(app.commands) >= 5, len(app.commands)
    assert not any("未找到" in l for l in app.query_one("#transcript").lines)


def test_g5_ext_missing_warns(tmp_path, monkeypatch):
    """PRISM_EXT_DIR 指向不存在目录 → transcript 写「未找到」警告。"""
    monkeypatch.setenv("PRISM_EXT_DIR", str(tmp_path / "nonexistent-ext"))
    app = PrismApp(); app.run(headless=True)
    app._drain()
    lines = app.query_one("#transcript").lines
    assert any("未找到" in l for l in lines), lines[:6]


def test_g5_retry_visible_and_error_guidance():
    """auto_retry_start/end 落 transcript; error 按内容分类给指引并归位 busy。"""
    app = _app()
    emit = app.agent.hooks["emit"]
    emit({"type": "agent_start"}); app._drain()
    emit({"type": "auto_retry_start", "attempt": 2, "error": "timeout after 30s"})
    app._drain()
    assert "重试" in _text(app), _text(app)[-200:]
    emit({"type": "auto_retry_end", "attempts": 3, "gave_up": True, "error": "boom"})
    app._drain()
    assert "放弃" in _text(app), _text(app)[-200:]
    emit({"type": "error", "error": "401 invalid api key"}); app._drain()
    assert "OPENAI_API_KEY" in _text(app), _text(app)[-200:]
    assert app._agent_busy is False
    emit({"type": "error", "error": "read timeout"}); app._drain()
    assert "超时" in _text(app) or "/model" in _text(app), _text(app)[-200:]
