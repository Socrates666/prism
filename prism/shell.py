"""prism TUI 套壳 —— 自研 textual 接口相近 TUI(零 textual/rich 依赖)。

布局对齐 piagent(顶到底): Header / Messages(transcript 滚动) / Current(流式)
/ Editor(accent 边框, Shift+Enter 多行) / Footer(cwd · model · busy)。

@ 路由(原则8)在 on_input_submitted 处理; agent emit 跨线程经 call_from_thread 回主循环。
"""
from __future__ import annotations

from .tui import App, Header, Input, RichLog, Static, Footer


class PrismApp(App):
    """prism 全屏 TUI(自研引擎)。"""

    CSS = """
Screen { layout: vertical; }
#transcript { height: 1fr; border: round $accent; padding: 0 1; }
#current { height: auto; min-height: 1; padding: 0 1; }
#dock { height: auto; min-height: 3; border: round $accent; padding: 0 1; }
"""
    TITLE = "Prism"

    def __init__(self) -> None:
        super().__init__()
        self.agent = None
        self.commands: dict = {}

    # ── 布局 ─────────────────────────────────────────────────────────────
    def compose(self):
        yield Header(id="header")
        yield RichLog(id="transcript", wrap=True)
        yield Static(id="current")
        yield Input(id="dock", placeholder="@agent 消息  |  /command  |  Python 代码")
        yield Footer(id="footer")

    # ── 按键(Esc 中断当前 agent run, 不退出 prism) ────────────────────────
    def on_key(self, event) -> None:
        if event.key == "escape" and self._agent_busy:
            if self.agent:
                self.agent.stop()
                log = self.query_one("#transcript")
                if isinstance(log, RichLog):
                    log.write("[yellow]⏹ 已中断[/yellow]")

    # ── 装配 agent + emit(跨线程) ─────────────────────────────────────────
    def on_mount(self) -> None:
        from .agent import Agent
        from .model import OpenAIModel
        from .registry import default_registry, load_ext
        from .memory import FileMemory

        log = self.query_one("#transcript")
        current = self.query_one("#current")
        app = self

        reasoning_buf: list[str] = []
        current_buf: list[str] = []

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
                text = "".join(reasoning_buf).replace("[", "\\[")
                app.call_from_thread(
                    log.write, f"[dim italic]  {text}[/dim italic]")
                reasoning_buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "agent_start":
                app._agent_busy = True
            elif t in ("agent_end", "steer_interrupt"):
                app._agent_busy = False
            if t == "message_update":
                flush_reasoning()
                current_buf.append(event.get("delta", ""))
                update_current()
            elif t == "message_end":
                text = "".join(current_buf)
                if text:
                    app.call_from_thread(log.write, text)
                current_buf.clear()
                app.call_from_thread(current.update, "")
            elif t == "reasoning":
                parts = event.get("text", "").split("\n")
                for i, part in enumerate(parts):
                    reasoning_buf.append(part)
                    if i < len(parts) - 1:
                        flush_reasoning()
            elif t == "tool_execution_start":
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
                    app.call_from_thread(log.write, f"{obs} {mark} [dim]{result}[/dim]")
                else:
                    app.call_from_thread(log.write, f"{obs} {mark}")
            elif t == "cognitive":
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
        from .agent_registry import restore_agents
        main_agent, subs = restore_agents(self, emit)
        if main_agent:
            self.agent = main_agent
        else:
            self.agent = Agent("Prism", model=OpenAIModel(), kind="main",
                               registry=default_registry, memory=FileMemory(".prism/memory"))
            sections = default_registry.get_prompt("prism")
            if sections:
                self.agent.apply_prompt(sections, "Prism", "main")
            self.agent.hooks["emit"] = emit
        self.agent.namespace["theme"] = ThemeCtl(self)
        for sub in subs:
            self.agent.namespace[sub.name] = sub
        self.model_name = getattr(self.agent.model, "model", "") or ""

        # 欢迎信息(pi 风格: 启动头)
        log.write("[bold cyan]◆ Prism[/bold cyan] [dim]— Agentic TUI  v0.1[/dim]")
        log.write("")
        if default_registry.tools():
            log.write("[dim]tools:[/dim] " + "  ".join(f"[cyan]{t.name}[/]" for t in default_registry.tools()))
        if self.commands:
            log.write("[dim]cmds:[/dim]   " + "  ".join(f"[cyan]/{n}[/]" for n in sorted(self.commands)))
        log.write("[dim]─[/dim]" * 40)
        log.write("")

    # ── 输入路由(/ · @ · Python) ──────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        if not text.strip():
            return
        log = self.query_one("#transcript")
        log.write(f"[bold green]❯[/] {text}")
        ns = self.agent.namespace
        stripped = text.strip()

        # / 指令
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

        # @ 路由
        if stripped.startswith("@") and "\n" not in stripped:
            parts = stripped[1:].split(None, 1)
            if len(parts) < 2:
                log.write("[red]@ 了就得说事[/]")
                return
            name, msg = parts
            target = ns.get(name)
            if target is not None and hasattr(target, "inject"):
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
        """给子 agent 的 emit: 事件汇入主 transcript, 带 [name] 标签。"""
        log = self.query_one("#transcript")
        app = self
        buf: list[str] = []

        def flush() -> None:
            if buf:
                app.call_from_thread(log.write, f"[dim blue]┌[{name}][/dim blue]")
                app.call_from_thread(log.write, "".join(buf))
                app.call_from_thread(log.write, f"[dim blue]└[/dim blue]")
                buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "agent_start":
                app._agent_busy = True
            elif t in ("agent_end", "steer_interrupt"):
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


class ThemeCtl:
    """theme 控制器: 暴露给 agent namespace, 跨线程切主题。"""
    def __init__(self, app: "PrismApp"):
        self._app = app

    def set(self, name: str) -> None:
        self._app.call_from_thread(self._apply, name)

    def _apply(self, name: str) -> None:
        if name in self._app.available_themes:
            self._app.theme = name
            self._app.request_render()

    def list(self) -> list:
        return sorted(getattr(self._app, "available_themes", {}).keys())


def _fmt_args(args: dict, max_len: int = 60) -> str:
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


def main() -> None:
    PrismApp().run()  # pragma: no cover  (入口)
