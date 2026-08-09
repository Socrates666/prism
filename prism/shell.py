"""prism TUI 套壳 — textual 全屏, 抄 pi 的 transcript + dock 布局。

布局(抄 pi packages/tui/fullscreen.ts):
  上方 transcript(RichLog 滚动对话区) + 底部 dock(Input 固定输入)

@ 路由(原则8)在 Input 处理; agent emit 跨线程到 RichLog(call_from_thread)。
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Header, Input, RichLog


class Transcript(RichLog):
    """transcript 显示区。can_focus=False: 点击它不抢 Input 焦点。

    RichLog 默认 can_focus=True —— 鼠标点击 transcript 会把焦点从输入框
    抢走, 导致键盘输入丢失、:focus 边框消失(用户报"点击后失效")。
    transcript 是只读显示区, 不需要焦点, 关掉即可。
    """
    can_focus = False


class ThemeCtl:
    """theme 控制器(阶段12): 暴露给 agent namespace, 跨线程切主题。

    治 theme namespace gap(开放问题 #16): agent 能 `theme.set("nord")`。
    """
    def __init__(self, app: "PrismApp"):
        self._app = app

    def set(self, name: str) -> None:
        self._app.call_from_thread(self._apply, name)

    def _apply(self, name: str) -> None:
        self._app.theme = name  # pragma: no cover  (跨线程, call_from_thread 调)

    def list(self) -> list:
        return sorted(getattr(self._app, "available_themes", {}).keys())


CSS = """
Screen { layout: vertical; }
#transcript { height: 1fr; border: solid $accent; padding: 0 1; }
#dock { height: 3; border: solid $primary; }
#dock:focus { border: solid $accent; }
"""


class PrismApp(App):
    """prism 全屏 TUI(transcript + dock)。"""

    CSS = CSS

    def __init__(self) -> None:
        super().__init__()
        self.agent = None  # 主 agent(on_mount 时建)
        self.commands = {}  # slash 指令(on_mount 时从 ext/commands/ 加载)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Transcript(id="transcript", wrap=True, markup=True)
        yield Input(id="dock", placeholder="@agent 消息   或   Python 代码")

    def on_mount(self) -> None:
        from .agent import Agent
        from .model import OpenAIModel
        from .registry import default_registry, load_ext
        from .memory import FileMemory

        log = self.query_one("#transcript", RichLog)
        app = self

        # emit 桥接: actor 线程 emit → call_from_thread 写 RichLog(跨线程安全)
        # 流式分行: 按 LLM 的 \n 分行(RichLog.write 每次=一行), 不每 token 一行
        line_buf: list[str] = []
        reasoning_buf: list[str] = []

        def flush_line() -> None:
            if line_buf:
                app.call_from_thread(log.write, "".join(line_buf))
                line_buf.clear()

        def flush_reasoning() -> None:
            if reasoning_buf:
                text = "".join(reasoning_buf).replace("[", "\\[")
                app.call_from_thread(log.write, f"[dim italic]{text}[/dim italic]")
                reasoning_buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "message_update":
                flush_reasoning()                       # 思考结束, 转正式回复
                # 按 \n 分段: 前面的完整行 flush, 最后一段留 buffer 继续累加下一个 delta
                parts = event.get("delta", "").split("\n")
                for i, part in enumerate(parts):
                    line_buf.append(part)
                    if i < len(parts) - 1:
                        flush_line()
            elif t == "message_end":
                flush_line()                       # message 结束, flush 剩余行
            elif t == "reasoning":
                parts = event.get("text", "").split("\n")
                for i, part in enumerate(parts):
                    reasoning_buf.append(part)
                    if i < len(parts) - 1:
                        flush_reasoning()
            elif t == "tool_execution_start":
                flush_line()                       # 工具前先把文本 flush
                app.call_from_thread(log.write, f"[dim]→ {event['tool_name']}({event['args']})[/dim]")
            elif t == "tool_execution_end":
                mark = "✗" if event.get("is_error") else "✓"
                app.call_from_thread(log.write, f"[dim]  {mark} {str(event.get('result', ''))[:200]}[/dim]")
            elif t == "error":
                flush_line()
                app.call_from_thread(log.write, f"[red]error: {event.get('error')}[/red]")
            elif t == "patch_error":
                flush_line()
                app.call_from_thread(log.write, f"[yellow]⚠ patch {event.get('phase')}/{event.get('point')}: {event.get('error')} (已降级)[/yellow]")

        # 加载 ext/(tools/prompts/patches/skills 进 default_registry, 容错) + slash 指令
        from .commands import load_commands
        load_ext("ext", default_registry, emit=emit)
        self.commands = load_commands("ext", emit=emit)
        # 建 main agent(接 registry → ext/ 的 tool 可用, 如 web_search)
        memory = FileMemory(".prism/memory")
        self.agent = Agent("main", model=OpenAIModel(), kind="main", registry=default_registry, memory=memory)
        self.agent.hooks["emit"] = emit
        self.agent.namespace["theme"] = ThemeCtl(self)   # theme 自举口子(阶段12, 治 #16)
        log.write("[bold]prism[/bold] — 全屏 TUI(抄 pi transcript+dock)\n")
        if default_registry.tools():
            log.write("工具: " + "  ".join(f"[cyan]{t.name}[/]" for t in default_registry.tools()) + "\n")
        if self.commands:
            log.write("指令: " + "  ".join(f"[cyan]/{n}[/]" for n in sorted(self.commands)) + "\n")
        log.write("输入 [cyan]@agent 消息[/] 对话, 或直接 Python 代码。Ctrl+C 退出。\n\n")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        if not text.strip():
            return
        log = self.query_one("#transcript", RichLog)
        log.write(f"[bold green]>>>[/] {text}\n")
        event.input.value = ""

        ns = self.agent.namespace
        stripped = text.strip()

        # / 指令(ext/commands/, 扩展点)
        if stripped.startswith("/") and "\n" not in stripped:
            parts = stripped[1:].split(None, 1)
            name = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            cmd = self.commands.get(name)
            if cmd is None:
                log.write(f"[red]/{name}: 未知指令。可用: {' '.join('/'+c for c in sorted(self.commands))}[/]\n")
            else:
                try:
                    ctx = {"agent": self.agent, "app": self, "write": lambda m: log.write(m),
                           "commands": self.commands}
                    result = cmd.run(args, ctx)
                    if result:
                        log.write(f"{result}\n")
                except Exception as e:  # pragma: no cover  (pilot 漏)
                    log.write(f"[red]/{name} 失败: {type(e).__name__}: {e}[/]\n")
            return

        # @ 路由(原则8): 单行 @name 消息 → 目标 agent.inject; 否则 Python exec
        if stripped.startswith("@") and "\n" not in stripped:
            parts = stripped[1:].split(None, 1)
            if len(parts) < 2:
                log.write("[red]空消息。@ 了就得说事[/]\n")
                return
            name, msg = parts
            target = ns.get(name)
            if target is not None and hasattr(target, "inject"):
                target.inject({"type": "run", "input": msg})   # actor 线程跑, 不冻 TUI
            else:
                log.write(f"[red]@{name}: 命名空间没有这个 agent[/]\n")
        else:
            # 主 agent 享完整 IPython(原则13): exec in namespace
            # textual 全屏接管终端, exec 的 print 走 sys.stdout 会丢 → 重定向捕获写到 transcript
            import contextlib, io
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    exec(compile(text, "<prism>", "exec"), ns)  # pragma: no cover  (pilot exec 漏)
            except Exception as e:
                log.write(f"[red]{type(e).__name__}: {e}[/]")
            for line in buf.getvalue().splitlines():
                log.write(line)  # pragma: no cover  (pilot exec print 漏)

    def make_subagent_emit(self, name: str):
        """给子 agent 的 emit(阶段12): 事件汇入主 transcript, 带 [name] 前缀。"""
        log = self.query_one("#transcript", RichLog)
        app = self
        buf: list[str] = []

        def flush() -> None:
            if buf:
                app.call_from_thread(log.write, f"[dim][{name}][/dim] " + "".join(buf))
                buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "message_update":
                buf.append(event.get("delta", ""))
            elif t == "message_end":
                flush()
            elif t == "tool_execution_start":
                flush()
                app.call_from_thread(log.write, f"[dim][{name}] → {event.get('tool_name')}[/]")
            elif t == "tool_execution_end":
                mark = "✗" if event.get("is_error") else "✓"
                app.call_from_thread(log.write, f"[dim][{name}]   {mark} {str(event.get('result', ''))[:150]}[/]")
            elif t == "error":
                flush()
                app.call_from_thread(log.write, f"[red][{name}] error: {event.get('error')}[/]")
        return emit


def main() -> None:
    PrismApp().run()  # pragma: no cover  (入口)
