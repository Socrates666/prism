"""黑盒 TUI: PrismApp Pilot 验证结构/焦点/不崩(不调 LLM)。

RichLog 内容不可读回, 故断言 widget 状态/焦点/app 存活, 不断言渲染文本。
"""
import asyncio
from textual.widgets import Input
from prism.shell import PrismApp


def test_tui_mounts_main_agent_and_widgets():
    async def run():
        async with PrismApp().run_test() as pilot:
            app = pilot.app
            assert app.agent is not None
            assert app.agent.kind == "main"
            assert app.query_one("#transcript") is not None
            assert app.query_one("#dock") is not None
    asyncio.run(run())


def test_tui_focus_survives_transcript_click():
    """阶段 E 修复回归: 点击 transcript 不抢 Input 焦点。"""
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            assert dock.has_focus
            await pilot.click("#transcript")
            await pilot.pause()
            assert dock.has_focus                         # 焦点没被抢
            await pilot.press("a", "b", "c")
            await pilot.pause()
            assert dock.value == "abc"                    # 键盘仍进 Input
    asyncio.run(run())


def test_tui_at_route_unknown_agent_no_crash():
    """@未知 agent → 报错写 transcript, 但 app 不崩。"""
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            dock.value = "@ghost hello"
            await pilot.press("enter")
            await pilot.pause()
            assert pilot.app.is_running                    # 没崩
            assert dock.value == ""                        # 提交后清空
    asyncio.run(run())


def test_tui_empty_at_message_no_crash():
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            dock.value = "@main"                           # 空消息
            await pilot.press("enter")
            await pilot.pause()
            assert pilot.app.is_running
    asyncio.run(run())
