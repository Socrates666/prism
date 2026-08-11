"""prism TUI 套壳 — textual 全屏, transcript + dock 布局。

@ 路由(原则8)在 Input 处理; agent emit 跨线程到 RichLog(call_from_thread)。
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Header, RichLog, Static, TextArea


class Transcript(RichLog):
    """transcript 显示区。can_focus=False: 点击不抢 dock 焦点。"""
    can_focus = False


class DockInput(TextArea):
    """多行输入 dock。Shift+Enter 提交, Enter 换行(支持粘贴长 prompt / 多行代码)。

    终端协议注意: Shift+Enter 需终端发送带 shift 修饰的序列(kitty keyboard
    protocol / CSI u)。Windows Terminal 较新版本默认支持; 若你的终端把
    Shift+Enter 当普通 Enter, 它会退化为换行 —— 启动提示里有兜底。
    """
    BINDINGS = [
        Binding("shift+enter", "submit", "发送", show=False, priority=True),
    ]

    def action_submit(self) -> None:
        text = self.text
        if not text.strip():
            return
        self.text = ""
        app = self.app
        if hasattr(app, "submit_dock"):
            app.submit_dock(text)


class ThemeCtl:
    """theme 控制器: 暴露给 agent namespace, 跨线程切主题。"""
    def __init__(self, app: "PrismApp"):
        self._app = app

    def set(self, name: str) -> None:
        self._app.call_from_thread(self._apply, name)

    def _apply(self, name: str) -> None:
        self._app.theme = name  # pragma: no cover

    def list(self) -> list:
        return sorted(getattr(self._app, "available_themes", {}).keys())


CSS = """
Screen { layout: vertical; }
#transcript { 
    height: 1fr; 
    border: round $accent 40%;
    padding: 0 1;
}
#dock-row { 
    height: 7; 
    layout: horizontal;
}
#dock { 
    height: 100%;
    width: 1fr;
    border: round $primary 50%;
}
#send { 
    width: 6;
    height: 100%;
}
#current { 
    height: auto; 
    min-height: 1; 
    padding: 0 1; 
    color: $text;
}
#dock:focus { 
    border: round $accent;
}
"""


def _fmt_args(args: dict, max_len: int = 60) -> str:
    """精简工具参数显示。长文本截断, 只显示 key 的摘要。"""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", " ").strip()
        if len(s) > max_len:
            s = s[:max_len] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _fmt_result(result: str, max_lines: int = 3, max_chars: int = 150) -> str:
    """精简工具结果。多行只显示前几行。"""
    if not result:
        return ""
    lines = result.strip().split("\n")
    if len(lines) > max_lines:
        shown = lines[:max_lines]
        shown.append(f"  ... ({len(lines) - max_lines} more lines)")
        text = "\n".join(shown)
    else:
        text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text


class PrismApp(App):
    """prism 全屏 TUI(transcript + dock)。"""

    CSS = CSS
    TITLE = "Prism"

    def __init__(self) -> None:
        super().__init__()
        self.agent = None
        self.commands = {}
        self._agent_busy = False  # agent 正在跑时设 True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Transcript(id="transcript", wrap=True, markup=True)
        yield Static(id="current")
        with Horizontal(id="dock-row"):
            yield DockInput(id="dock")
            yield Button("发送", id="send")

    def on_key(self, event) -> None:
        """Esc 中断当前 agent run(不退出 prism)。"""
        if event.key == "escape" and self._agent_busy:
            if self.agent:
                self.agent.stop()
                log = self.query_one("#transcript", RichLog)
                log.write("[yellow]⏹ 已中断[/yellow]")

    def on_mount(self) -> None:
        from .agent import Agent
        from .model import OpenAIModel
        from .registry import default_registry, load_ext
        from .memory import FileMemory

        log = self.query_one("#transcript", RichLog)
        current = self.query_one("#current", Static)
        app = self

        import time
        reasoning_buf: list[str] = []
        current_buf: list[str] = []
        _reasoning_last: list = [0.0]
        _reasoning_flushed: list = [0]   # 已增量 flush 到 transcript 的 reasoning 字符数
        _reasoning_label_shown: list = [False]   # 本轮思考是否已显「思考」标签(首段带, 后续续接)

        def update_current() -> None:
            app.call_from_thread(current.update, "".join(current_buf))

        def flush_current() -> None:
            text = "".join(current_buf)
            if text:
                app.call_from_thread(log.write, text)
            current_buf.clear()
            app.call_from_thread(current.update, "")

        def flush_reasoning() -> None:
            if reasoning_buf:
                full = "".join(reasoning_buf)
                remaining = full[_reasoning_flushed[0]:]   # 未增量 flush 的尾段
                if remaining.strip():
                    text = remaining.replace("[", "\\[")
                    first = not _reasoning_label_shown[0]
                    prefix = "[blue]思考[/blue] [dim italic]▸ " if first else "[dim italic]    "
                    app.call_from_thread(log.write, f"{prefix}{text}[/dim italic]")
                reasoning_buf.clear()
                _reasoning_flushed[0] = 0
                _reasoning_label_shown[0] = False

        _diag = {"reasoning": 0}
        def emit(event: dict) -> None:
            t = event.get("type")
            # 临时诊断: reasoning 是否到达 emit(定位运行时'思考不显示')
            if t == "reasoning":
                _diag["reasoning"] += 1
                if _diag["reasoning"] == 1:
                    try:
                        import time as _t
                        with open(".prism/emit.log", "a", encoding="utf-8") as f:
                            f.write(f"{_t.time():.1f} FIRST reasoning reached emit\n")
                    except Exception:
                        pass
            elif t == "message_end":
                try:
                    import time as _t
                    with open(".prism/emit.log", "a", encoding="utf-8") as f:
                        f.write(f"{_t.time():.1f} message_end | reasoning_count={_diag['reasoning']}\n")
                except Exception:
                    pass
            elif t == "error":
                try:
                    import time as _t
                    with open(".prism/emit.log", "a", encoding="utf-8") as f:
                        f.write(f"{_t.time():.1f} ERROR | {str(event.get('error',''))[:200]}\n")
                except Exception:
                    pass
            if t == "agent_start":
                app._agent_busy = True
            elif t == "agent_end":
                app._agent_busy = False
            elif t == "steer_interrupt":
                app._agent_busy = False
            if t == "message_update":
                flush_reasoning()
                current_buf.append(event.get("delta", ""))
                update_current()
            elif t == "message_end":
                flush_reasoning()
                text = "".join(current_buf)
                if text:
                    app.call_from_thread(log.write, text)
                current_buf.clear()
                app.call_from_thread(current.update, "")
            elif t == "reasoning":
                reasoning_buf.append(event.get("text", ""))
                # 流式: 时间节流(300ms)增量写 transcript; 一次思考只在首段带「思考」标签, 后续续接
                now = time.time()
                if now - _reasoning_last[0] > 0.3:
                    _reasoning_last[0] = now
                    full = "".join(reasoning_buf)
                    new_part = full[_reasoning_flushed[0]:]
                    first = not _reasoning_label_shown[0]
                    _reasoning_flushed[0] = len(full)
                    if new_part.strip():
                        np = new_part.replace("\n", " ").replace("\r", "").replace("[", "\\[")
                        prefix = "[blue]思考[/blue] [dim italic]▸ " if first else "[dim italic]    "
                        _reasoning_label_shown[0] = True
                        try:
                            app.call_from_thread(log.write, f"{prefix}{np}[/dim italic]")
                        except Exception:
                            pass
            elif t == "tool_execution_start":
                flush_reasoning()
                name = event.get("tool_name", "?")
                args_str = _fmt_args(event.get("args", {}))
                app.call_from_thread(
                    log.write, f"[cyan]行动[/cyan] [dim]▸ {name}[/dim]"
                    + (f"[dim]({args_str})[/dim]" if args_str else ""))
            elif t == "tool_execution_end":
                mark = "[red]✗[/red]" if event.get("is_error") else "[green]✓[/green]"
                result = _fmt_result(str(event.get("result", "")))
                obs = "[red]观察[/red]" if event.get("is_error") else "[green]观察[/green]"
                if result:
                    app.call_from_thread(
                        log.write, f"{obs} {mark} [dim]{result}[/dim]")
                else:
                    app.call_from_thread(log.write, f"{obs} {mark}")
            elif t == "cognitive":
                # 白盒化: 认知循环阶段(直觉/反思)显式可见
                stage = event.get("stage")
                content = _fmt_result(str(event.get("content", ""))).replace("[", "\\[")
                if stage == "intuition":
                    app.call_from_thread(
                        log.write, f"[magenta]直觉[/magenta] [dim]▸ {content}[/dim]")
                elif stage == "reflect":
                    bo = event.get("based_on", [])
                    bo_str = f" [dim](based_on {bo})[/dim]" if bo else ""
                    app.call_from_thread(
                        log.write, f"[yellow]反思[/yellow] [dim italic]↺ {content}[/dim italic]{bo_str}")
            elif t == "error":
                flush_current()
                app.call_from_thread(
                    log.write, f"[red bold]✗ error:[/red bold] [red]{event.get('error')}[/red]")
            elif t == "patch_error":
                flush_current()
                app.call_from_thread(
                    log.write,
                    f"[yellow]⚠ {event.get('phase')}/{event.get('point')}: {event.get('error')} (已降级)[/yellow]")

        # 加载 ext/ + slash 指令
        from .commands import load_commands
        load_ext("ext", default_registry, emit=emit)
        self.commands = load_commands("ext", emit=emit)
        # 从 ext/agents/ 恢复 agent 配置
        from .agent_registry import restore_agents
        main_agent, subs = restore_agents(self, emit)
        if main_agent:
            self.agent = main_agent
        else:
            # fallback: 无配置文件时硬编码创建
            from .memory import FileMemory as _FM
            self.agent = Agent("Prism", model=OpenAIModel(), kind="main",
                               registry=default_registry, memory=_FM(".prism/memory"))
            sections = default_registry.get_prompt("prism")
            if sections:
                self.agent.apply_prompt(sections, "Prism", "main")
            self.agent.hooks["emit"] = emit
        self.agent.namespace["theme"] = ThemeCtl(self)
        # 认知层(RLM): 主 agent 接 SQLiteForest + 搜索循环(直觉/自指/TUI 白盒五阶段)
        from .forest import SQLiteForest
        from .cog_patches import enable_cognitive_cycle
        self.agent.forest = SQLiteForest(".prism/forest.db", session_id=self.agent.name)
        enable_cognitive_cycle(self.agent)
        # 子 agent 注册到命名空间
        for sub in subs:
            self.agent.namespace[sub.name] = sub

        # 欢迎信息
        log.write("[bold cyan]╭──────────────────────────────╮[/bold cyan]")
        log.write("[bold cyan]│[/bold cyan] [bold]Prism[/bold] — Agentic TUI  [dim]v0.1[/dim]  [bold cyan]│[/bold cyan]")
        log.write("[bold cyan]╰──────────────────────────────╯[/bold cyan]")
        if default_registry.tools():
            log.write("[dim]tools:[/dim] " + "  ".join(f"[cyan]{t.name}[/]" for t in default_registry.tools()))
        if self.commands:
            log.write("[dim]cmds:[/dim]   " + "  ".join(f"[cyan]/{n}[/]" for n in sorted(self.commands)))
        log.write("[dim]输入:[/dim]  点[bold]发送[/bold]按钮(任何终端) 或 [bold]Shift+Enter[/bold](mintty) · Enter 换行 · 可粘贴长文本")
        log.write("[dim]─[/dim]" * 40)
        log.write("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """发送按钮(Shift+Enter 在不支持 kitty 的终端里的可靠兜底)。"""
        if event.button.id == "send":
            dock = self.query_one("#dock", DockInput)
            text = dock.text
            dock.text = ""
            if text.strip():
                self.submit_dock(text)

    def submit_dock(self, text: str) -> None:
        """dock 提交入口(DockInput 的 Shift+Enter 触发)。支持多行 @ 消息 / 多行 Python。

        路由: /cmd(单行) / @agent 消息(可多行) / 否则当 Python exec(可多行)。
        """
        if not text.strip():
            return
        log = self.query_one("#transcript", RichLog)
        # 用户输入用醒目的标记; 多行时后续行缩进, 不破坏 transcript 结构
        display = text.replace("\n", "\n  ") if "\n" in text else text
        log.write(f"[bold green]❯[/] {display}")

        ns = self.agent.namespace
        stripped = text.strip()

        # / 指令(保持单行语义)
        if stripped.startswith("/") and "\n" not in stripped:
            parts = stripped[1:].split(None, 1)
            name = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            builtin = self._builtin_command(name)
            if builtin is not None:
                try:
                    result = builtin(args)
                    if result:
                        log.write(f"{result}")
                except Exception as e:  # pragma: no cover
                    log.write(f"[red]/{name}: {type(e).__name__}: {e}[/]")
                return
            cmd = self.commands.get(name)
            if cmd is None:
                avail = ['/revert', '/backups'] + ['/' + c for c in sorted(self.commands)]
                log.write(f"[red]/{name} — 未知指令。可用: {' '.join(avail)}[/]")
            else:
                try:
                    ctx = {"agent": self.agent, "app": self, "write": lambda m: log.write(m),
                           "commands": self.commands}
                    result = cmd.run(args, ctx)
                    if result:
                        log.write(f"{result}")
                except Exception as e:  # pragma: no cover
                    log.write(f"[red]/{name}: {type(e).__name__}: {e}[/]")
            return

        # @ 路由(允许换行: 粘贴长 prompt 不再被踢去 exec)
        if stripped.startswith("@"):
            parts = stripped[1:].split(None, 1)
            if len(parts) < 2:
                log.write("[red]@ 了就得说事[/]")
                return
            name, msg = parts
            target = ns.get(name)
            if target is not None and hasattr(target, "inject"):
                # 如果目标正在跑, steer 插队; 否则正常 followUp
                kind = "steer" if getattr(target, "_thread", None) and target.inbox.qsize() > 0 else "followUp"
                target.inject({"type": "run", "input": msg}, kind=kind)
                if kind == "steer":
                    log.write(f"[yellow]⚡ steer → {name}[/yellow]")
            else:
                log.write(f"[red]@{name}: 命名空间没有这个 agent[/]")
        else:
            import contextlib, io
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    exec(compile(text, "<prism>", "exec"), ns)  # pragma: no cover
            except Exception as e:
                log.write(f"[red]{type(e).__name__}: {e}[/]")
            for line in buf.getvalue().splitlines():
                log.write(line)  # pragma: no cover

    def _builtin_command(self, name: str):
        """第一公民内置指令。"""
        from .guard import revert_latest, list_backups
        if name == "revert":
            def _r(args):
                n = revert_latest(self.agent.emit)
                return f"[green]✓[/] 已回退 {n}(重启生效)" if n else "无改动可回退"
            return _r
        if name == "backups":
            def _b(args):
                bf = list_backups()
                if not bf:
                    return "无备份"
                return "改动备份栈(最近在上):\n" + "\n".join(
                    f"  {i+1}. {o} → {b}" for i, (o, b) in enumerate(bf))
            return _b
        return None

    def make_subagent_emit(self, name: str):
        """给子 agent 的 emit: 事件汇入主 transcript, 带标签前缀。"""
        log = self.query_one("#transcript", RichLog)
        app = self
        buf: list[str] = []

        def flush() -> None:
            if buf:
                app.call_from_thread(
                    log.write, f"[dim blue]┌[{name}][/dim blue]")
                app.call_from_thread(
                    log.write, "".join(buf))
                app.call_from_thread(
                    log.write, f"[dim blue]└[/dim blue]")
                buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "agent_start":
                app._agent_busy = True
            elif t == "agent_end":
                app._agent_busy = False
            elif t == "steer_interrupt":
                app._agent_busy = False
            if t == "message_update":
                buf.append(event.get("delta", ""))
            elif t == "message_end":
                flush()
            elif t == "tool_execution_start":
                flush()
                tool = event.get("tool_name", "?")
                args_str = _fmt_args(event.get("args", {}))
                app.call_from_thread(
                    log.write,
                    f"[dim blue]│[{name}][/dim blue] [cyan]行动[/cyan] [dim]▸ {tool}[/dim]"
                    + (f"[dim]({args_str})[/dim]" if args_str else ""))
            elif t == "tool_execution_end":
                mark = "[red]✗[/red]" if event.get("is_error") else "[green]✓[/green]"
                result = _fmt_result(str(event.get("result", "")))
                obs = "[red]观察[/red]" if event.get("is_error") else "[green]观察[/green]"
                app.call_from_thread(
                    log.write, f"[dim blue]│[{name}][/dim blue] {obs} {mark} [dim]{result}[/dim]")
            elif t == "cognitive":
                stage = event.get("stage")
                content = _fmt_result(str(event.get("content", ""))).replace("[", "\\[")
                if stage == "intuition":
                    app.call_from_thread(
                        log.write, f"[dim blue]│[{name}][/dim blue] [magenta]直觉[/magenta] [dim]▸ {content}[/dim]")
                elif stage == "reflect":
                    bo = event.get("based_on", [])
                    bo_str = f" [dim](based_on {bo})[/dim]" if bo else ""
                    app.call_from_thread(
                        log.write, f"[dim blue]│[{name}][/dim blue] [yellow]反思[/yellow] [dim italic]↺ {content}[/dim italic]{bo_str}")
            elif t == "error":
                flush()
                app.call_from_thread(
                    log.write, f"[dim blue]│[{name}][/dim blue] [red]error: {event.get('error')}[/red]")
        return emit


def main() -> None:
    PrismApp().run()  # pragma: no cover  (入口)
