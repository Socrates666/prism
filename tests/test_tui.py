"""黑盒 TUI: PrismApp Pilot 验证结构/焦点/路由/不崩(不调 LLM)。

RichLog 内容不可读回, 故断言 widget 状态/焦点/agent 状态, 不断言渲染文本。
dock 现在是多行 DockInput(TextArea); 提交走 app.submit_dock()
(Shift+Enter 依赖终端协议, 测试里直接调 submit_dock 更稳)。
"""
import asyncio
from prism.shell import PrismApp, DockInput


def test_tui_mounts_main_agent_and_widgets():
    async def run():
        async with PrismApp().run_test() as pilot:
            app = pilot.app
            assert app.agent is not None
            assert app.agent.kind == "main"
            assert app.query_one("#transcript") is not None
            assert app.query_one("#dock") is not None
    asyncio.run(run())


def test_tui_dock_is_multiline_textarea():
    """Input → DockInput(TextArea) 回归: 多行输入。"""
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", DockInput)
            assert isinstance(dock, DockInput)
    asyncio.run(run())


def test_tui_focus_survives_transcript_click():
    """点击 transcript 不抢 dock 焦点。"""
    async def run():
        async with PrismApp().run_test() as pilot:
            dock = pilot.app.query_one("#dock", DockInput)
            assert dock.has_focus
            await pilot.click("#transcript")
            await pilot.pause()
            assert dock.has_focus                         # 焦点没被抢
            await pilot.press("a", "b", "c")
            await pilot.pause()
            assert dock.text == "abc"                     # 键盘仍进 dock
    asyncio.run(run())


def test_tui_at_route_unknown_agent_no_crash():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.submit_dock("@ghost hello")
            await pilot.pause()
            assert pilot.app.is_running                    # 没崩
            assert pilot.app.query_one("#dock", DockInput).text == ""  # 提交后清空
    asyncio.run(run())


def test_tui_empty_at_message_no_crash():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.submit_dock("@Prism")                # 空消息
            await pilot.pause()
            assert pilot.app.is_running
    asyncio.run(run())


class FakeModel:
    def __init__(self, script): self.script = list(script); self.i = 0
    def chat_stream(self, m, tools=None):
        text, tcs = self.script[self.i]; self.i += 1
        if text: yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def test_tui_slash_model_switches():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.submit_dock("/model glm-4.7")
            await pilot.pause()
            assert pilot.app.agent.model.model == "glm-4.7"
    asyncio.run(run())


def test_tui_slash_thinking_off():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.submit_dock("/thinking off")
            await pilot.pause()
            assert pilot.app.agent.thinking_level == "off"
    asyncio.run(run())


def test_tui_python_exec_sets_namespace():
    async def run():
        async with PrismApp().run_test() as pilot:
            pilot.app.submit_dock("x = 42")
            await pilot.pause()
            assert pilot.app.agent.namespace.get("x") == 42
    asyncio.run(run())


def test_tui_at_prism_runs_with_fake_model():
    async def run():
        async with PrismApp().run_test() as pilot:
            app = pilot.app
            app.agent.model = FakeModel([("prism-reply", [])])
            app.submit_dock("@Prism hi")
            for _ in range(50):
                await pilot.pause(0.05)
                if app.agent.last_result: break
            assert app.agent.last_result == "prism-reply"
    asyncio.run(run())


def test_tui_reasoning_event_reaches_emit():
    """★ reasoning 链路保护: 事件到达 agent.emit 广播 + agent 记录 streaming_reasoning。

    #current 的 call_from_thread 从主线程调会抛 RuntimeError(textual 限制),
    故本测只验链路; 显示机制在 actor 线程(运行时)走 call_from_thread 不抛。
    """
    async def run():
        async with PrismApp().run_test() as pilot:
            app = pilot.app
            seen = []
            unsub = app.agent.subscribe(lambda e: seen.append(e["type"]))
            app.agent.emit({"type": "reasoning", "text": "我在思考解法"})
            await pilot.pause()
            assert "reasoning" in seen, "reasoning 事件没到达 agent.emit 广播"
            assert "我在思考解法" in (app.agent.streaming_reasoning or ""), \
                "agent 没把思考记进 streaming_reasoning"
            unsub()
    asyncio.run(run())
