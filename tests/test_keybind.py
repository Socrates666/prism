"""REQ-G3 键盘分发层回归: 补全导航 / Enter 接受 / Esc 关浮层 / home-end / 输入历史 / Ctrl+C / Ctrl+J。

黑盒驱动 headless PrismApp(喂键 → _drain → 断言), 不连网。
提交路径用 on_input_submitted 覆写记录提交值, 不依赖 shell 的命令执行。
"""
import time

from prism.shell import PrismApp
from prism.tui.terminal import Key


def mount() -> PrismApp:
    app = PrismApp()
    app.run(headless=True)
    return app


def type_(app: PrismApp, text: str) -> None:
    for ch in text:
        app._dispatch_key(Key(key=ch, char=ch)); app._drain()


def press(app: PrismApp, k: str, ctrl: bool = False) -> None:
    app._dispatch_key(Key(key=k, char="", ctrl=ctrl)); app._drain()


def screen(app: PrismApp, rows: int = 30, cols: int = 80) -> str:
    buf = app._render_frame(rows, cols)
    return "\n".join("".join(c.ch for c in row) for row in buf.grid)


# ── 补全浮层: 方向键导航 + Enter 接受 ─────────────────────────────────────
def test_arrows_navigate_completion_not_history():
    """浮层激活时 up/down 归补全导航: 不翻历史、不提交、值不动。"""
    app = mount()
    app.on_input_submitted = lambda e: (_ for _ in ()).throw(AssertionError("不应提交"))
    app._drain()
    type_(app, "/")
    assert app._completion_active()
    sl = app._cmd_selectlist()
    assert len(sl._filtered) > 1
    sel0 = sl.selected
    press(app, "down")
    assert sl.selected == (sel0 + 1) % len(sl._filtered)
    press(app, "up")
    assert sl.selected == sel0
    assert app.query_one("#dock").value == "/"   # 未被历史回填


def test_enter_accepts_completion_selected():
    """Enter 先取选中项回填再提交(残缺前缀 /be 不当命令); 提交后浮层关闭。"""
    app = mount()
    got = []
    app.on_input_submitted = lambda e: got.append(e.value)
    app._drain()
    type_(app, "/ba")                            # backups 唯一匹配
    assert app._completion_active()
    press(app, "down")
    press(app, "enter")
    assert got == ["/backups "], got
    assert not app._completion_active()          # 修浮层残留
    assert app.query_one("#dock").value == ""    # 提交后清空


# ── Escape: 关浮层优先, busy 时仍中断 ─────────────────────────────────────
def test_escape_closes_overlay_then_busy_interrupts():
    app = mount()
    stopped = []
    class A:
        def stop(self): stopped.append(1)
    app.agent = A()
    app._drain()
    type_(app, "/")
    assert app._completion_active()
    press(app, "escape")
    assert not app._completion_active()
    app._agent_busy = True
    press(app, "escape")
    assert stopped == [1]                        # 浮层关后, busy Esc 仍中断


def test_escape_overlay_wins_over_busy_interrupt():
    """浮层激活 + busy 同时成立: 浮层优先关闭, 不中断。"""
    app = mount()
    stopped = []
    class A:
        def stop(self): stopped.append(1)
    app.agent = A()
    app._agent_busy = True
    app._drain()
    type_(app, "/")
    assert app._completion_active()
    press(app, "escape")
    assert not app._completion_active()
    assert stopped == []


# ── Home/End: 多行归输入框, 单行回退 transcript ───────────────────────────
def test_multiline_home_end_go_to_input():
    app = mount()
    dock = app.query_one("#dock")
    dock.value = "line1\nline2"; dock.pos = 11
    press(app, "home")
    assert dock.pos == 6
    press(app, "end")
    assert dock.pos == 11


def test_single_line_home_end_fall_back_to_transcript():
    app = mount()
    log = app.query_one("#transcript")
    dock = app.query_one("#dock")
    dock.value = "abc"; dock.pos = 3
    log._follow = False; log._top = 5
    press(app, "home")
    assert log._top == 0 and dock.pos == 3       # 单行 home → 滚顶, 输入框不动
    log._follow = False; log._top = 0
    press(app, "end")
    assert log._follow is True                   # 单行 end → 贴底


# ── 输入历史: 单行 up/down 回溯 ───────────────────────────────────────────
def test_single_line_history_nav():
    app = mount()
    app.on_input_submitted = lambda e: None      # 记录提交但不 exec
    app._drain()
    dock = app.query_one("#dock")
    for v in ("first_cmd", "second_cmd"):
        dock.value = v; dock.pos = len(v)
        dock.on_key(Key(key="enter", char="")); app._drain()
    press(app, "up")
    assert dock.value == "second_cmd"
    press(app, "up")
    assert dock.value == "first_cmd"
    press(app, "up")                             # 翻到顶: 不动
    assert dock.value == "first_cmd"
    press(app, "down")
    assert dock.value == "second_cmd"
    press(app, "down")                           # 回实时位: 恢复草稿(提交后已清空)
    assert dock.value == ""


def test_multiline_up_down_still_move_lines():
    app = mount()
    dock = app.query_one("#dock")
    dock.value = "aa\nbb"; dock.pos = 5
    press(app, "up")                             # 多行: 行移动(列保留), 不翻历史
    assert dock.pos == 2                         # 行 1 列 2 → 行 0 列 2
    press(app, "up")                             # 已在首行: 不动
    assert dock.pos == 2


# ── Ctrl+C 三分支 ──────────────────────────────────────────────────────────
def test_ctrl_c_busy_interrupts_without_clearing():
    app = mount()
    stopped = []
    class A:
        def stop(self): stopped.append(1)
    app.agent = A()
    dock = app.query_one("#dock")
    app._agent_busy = True
    dock.value = "keep me"
    app._dispatch_key(Key(key="ctrl+c", char="", ctrl=True)); app._drain()
    assert stopped == [1]
    assert dock.value == "keep me"               # 中断不清输入
    app._agent_busy = False
    app._dispatch_key(Key(key="ctrl+c", char="", ctrl=True)); app._drain()
    assert dock.value == ""                      # idle 有文 → 清空
    assert "已清空" in screen(app) or "已中断" in screen(app)   # 有反馈行


def test_ctrl_c_double_press_quits_with_chinese_hint():
    app = mount()
    press(app, "ctrl+c", ctrl=True)
    assert not app._quit.is_set()
    assert "再按一次 Ctrl+C 退出" in screen(app)
    press(app, "ctrl+c", ctrl=True)              # 1 秒内第二按
    assert app._quit.is_set()


# ── Ctrl+J 换行 ────────────────────────────────────────────────────────────
def test_ctrl_j_inserts_newline():
    app = mount()
    dock = app.query_one("#dock")
    dock.value = "a"; dock.pos = 1
    dock.on_key(Key(key="ctrl+j", char="")); app._drain()
    assert "\n" in dock.value
