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
            dock.value = "@Prism"                           # 空消息
            await pilot.press("enter")
            await pilot.pause()
            assert pilot.app.is_running
    asyncio.run(run())


class FakeModel:
    def __init__(self, script): self.script = list(script); self.i = 0
    def chat_stream(self, m, tools=None):
        text, tcs = self.script[self.i]; self.i += 1
        if text: yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def test_tui_slash_model_switches():                          # /model 触发 + 状态变
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            dock.value = "/model glm-4.7"
            await pilot.press("enter"); await pilot.pause()
            assert pilot.app.agent.model.model == "glm-4.7"
    asyncio.run(run())


def test_tui_slash_thinking_off():                            # /thinking off 触发
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            dock.value = "/thinking off"
            await pilot.press("enter"); await pilot.pause()
            assert pilot.app.agent.thinking_level == "off"
    asyncio.run(run())


def test_tui_python_exec_sets_namespace():                    # Python 输入→exec→namespace
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", Input)
            dock.value = "x = 42"
            await pilot.press("enter"); await pilot.pause()
            assert pilot.app.agent.namespace.get("x") == 42
    asyncio.run(run())


def test_tui_at_prism_runs_with_fake_model():                # @Prism→inject→actor 跑(fake model)
    async def run():
        async with PrismApp().run_test() as pilot:
            app = pilot.app
            app.agent.model = FakeModel([("prism-reply", [])])   # 避免真 LLM
            dock = app.query_one("#dock", Input)
            dock.value = "@Prism hi"
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause(0.05)
                if app.agent.last_result: break
            assert app.agent.last_result == "prism-reply"
    asyncio.run(run())
