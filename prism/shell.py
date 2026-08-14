"""prism TUI 套壳 —— 自研 textual 接口相近 TUI(零 textual/rich 依赖)。

布局(pi 极简, 无顶栏/底栏): Messages(transcript 滚动) / Current(流式)
/ Editor(聚焦 DeepPink 边框, Shift+Enter 多行)。

@ 路由(原则8)在 on_input_submitted 处理; agent emit 跨线程经 call_from_thread 回主循环。
"""
from __future__ import annotations

from pathlib import Path

from .tui import App, Input, RichLog, Static

# 内置指令(无 ext 文件的硬编码实现, 见 _builtin_command): 名 → DESC。
# 与 self.commands 一起构成 all_commands() 单一事实源。
BUILTIN_COMMANDS = {
    "revert": "回退上次文件改动: /revert  (重启生效)",
    "backups": "查看改动备份栈: /backups  (最近在上)",
}


class PrismApp(App):
    """prism 全屏 TUI(自研引擎)。"""

    CSS = """
Screen { layout: vertical; }
#transcript { height: 1fr; padding: 0 1; }
#current { height: auto; min-height: 0; max-height: 6; padding: 0 1; color: $text; }
#status { height: auto; min-height: 0; padding: 0 1; color: $accent; }
#completion { height: auto; min-height: 0; padding: 0 1; }
#dock { height: auto; min-height: 1; padding: 0 1; }
"""
    TITLE = "Prism"

    def __init__(self) -> None:
        super().__init__()
        self.agent = None
        self.commands: dict = {}
        # busy 引用计数: 主/子 agent 各自 agent_start +1 / agent_end -1,
        # 子 agent_end 不再把仍在跑的主 agent 抹成 idle(PROBLEM-2)。
        # _agent_busy 作为同步维护的 bool 供 Esc 判断(shell:42)/刷帧(app:182)读。
        self._busy_depth = 0

    def _busy_inc(self) -> None:
        self._busy_depth += 1
        self._agent_busy = True

    def _busy_dec(self) -> None:
        # 夹 0 防 drift(重复 agent_end / error 兜底不会跌负)
        self._busy_depth = max(0, self._busy_depth - 1)
        self._agent_busy = self._busy_depth > 0

    def all_commands(self) -> dict:
        """全部指令单一事实源: ext 指令 + 内置 revert/backups → {名: DESC}。

        补全浮层 / 未知指令报错 / /help 三处共用, 防三份清单各自漂移(PROBLEM-1)。
        """
        cmds = {n: getattr(m, "DESC", "") for n, m in self.commands.items()}
        cmds.update(BUILTIN_COMMANDS)
        return cmds

    # ── 布局 ─────────────────────────────────────────────────────────────
    def compose(self):
        # 无顶栏/底栏(用户裁决 2026-08-14): Header(◆标题+快捷键提示)与
        # Footer(cwd·model·thinking 状态)全部移除, 纯 transcript+输入区(pi 极简)
        yield RichLog(id="transcript", wrap=True)
        yield Static(id="current")
        yield Static(id="status")
        yield Input(id="dock")   # 无占位提示(用户裁决 2026-08-14: 输入区只留 ❯)

    # ── 按键(Esc 中断当前 agent run, 不退出 prism) ────────────────────────
    def on_key(self, event) -> None:
        if event.key == "escape" and self._agent_busy:
            if self.agent:
                self.agent.stop()
                log = self.query_one("#transcript")
                if isinstance(log, RichLog):
                    log.write("[yellow]⏹ 已中断[/yellow]")

    def on_tab(self, inp) -> bool:
        """Tab: / 模式+completion 可见 → 补全选中命令; 否则 @agent 智能填充。
        """
        v = (inp.value or "").lstrip() if inp is not None else ""
        if v.startswith("/") and self._completion_active():
            sl = self._cmd_selectlist()
            if sl:
                val = sl.selected_value()
                if val:
                    inp.value = f"/{val} "
                    inp.pos = len(inp.value)
                    self._hide_cmd_overlay()
                    self.request_render()
                return True
        if inp is None or getattr(inp, "id", "") != "dock" or self.agent is None:
            return False
        agents = [n for n, v in self.agent.namespace.items() if hasattr(v, "inject")]
        if not agents:
            return False
        import re
        cur = inp.value or ""
        pos = getattr(inp, "pos", len(cur))
        left, right = cur[:pos], cur[pos:]
        m = re.search(r"@(\w+)$", left)            # 光标左侧紧贴的 @agent
        if m and m.group(1) in agents:              # → 替换切下一个
            nxt = agents[(agents.index(m.group(1)) + 1) % len(agents)]
            new_left = left[:m.start()] + f"@{nxt}"
        else:                                        # → 光标处新增
            existing = [a for a in re.findall(r"@(\w+)", cur) if a in agents]
            nxt = agents[(agents.index(existing[-1]) + 1) % len(agents)] if existing else agents[0]
            new_left = left + f"@{nxt} "
        inp.value = new_left + right
        inp.pos = len(new_left)
        self.request_render()
        return True

    def _on_input_changed(self, value: str) -> None:
        """输入变化: / 开头 → 浮层 SelectList(pi 风格, 可选+高亮+箭头+Tab补全)。"""
        v = value.lstrip()
        if not v.startswith("/"):
            self._hide_cmd_overlay()
            return
        rest = v[1:]
        parts = rest.split()
        prefix = parts[0] if parts else ""
        cmds = sorted(self.all_commands())          # 单一事实源, 字典序(含内置 revert/backups)
        from prism.tui.widgets import SelectList
        sl = self._cmd_selectlist()
        if sl is None:                                   # 首次: 建浮层(全量, filter 内部过滤)
            h = min(len(cmds), 8)
            y = max(0, self._rows - 6 - h)
            sl = SelectList([{"value": c} for c in cmds])
            self._cmd_overlay = self.show_overlay(sl, 1, y, max(1, self._cols - 2), h)
        sl.set_filter(prefix)                            # 过滤(复用 overlay, 不重建)
        self.request_render()

    def _cmd_selectlist(self):
        """当前命令浮层的 SelectList(无则 None)。"""
        oid = getattr(self, "_cmd_overlay", None)
        if oid is None:
            return None
        for ov in self._overlays:
            if ov["id"] == oid:
                return ov["widget"]
        return None

    def _completion_active(self) -> bool:
        return getattr(self, "_cmd_overlay", None) is not None

    def _completion_move(self, d: int) -> None:
        sl = self._cmd_selectlist()
        if sl is not None:
            sl.move(d)
            self.request_render()

    def _hide_cmd_overlay(self) -> None:
        oid = getattr(self, "_cmd_overlay", None)
        if oid is not None:
            self.hide_overlay(oid)
            self._cmd_overlay = None

    # ── 装配 agent + emit(跨线程) ─────────────────────────────────────────
    def on_mount(self) -> None:
        from .agent import Agent
        from .model import OpenAIModel
        from .registry import default_registry, load_ext
        from .memory import FileMemory

        log = self.query_one("#transcript")
        current = self.query_one("#current")
        status = self.query_one("#status")
        app = self

        reasoning_buf: list[str] = []
        current_buf: list[str] = []
        pending_tool: list = [None]     # 跨 start/end 的工具块引用(cell)
        started: list = [False]         # 本 agent 是否处 started 未 end 状态(去重 agent_end/error 归位)

        # 折射中... 动画(agent 工作时, 输入框正上方)
        import threading as _th
        _status_anim = {"stop": None, "thread": None}

        def _status_loop() -> None:
            n = 0
            while _status_anim["stop"] and not _status_anim["stop"].is_set():
                dots = "." * (n % 4)
                # 无 markup 标签: 颜色由 #status 的 CSS color($accent) 提供,
                # 与 footer spinner 同色系且随主题(light 下 markup accent 是暗色基值, 会失配)
                try:
                    app.call_from_thread(status.update, f"◇ 折射中{dots}")
                except Exception:
                    pass
                n += 1
                _status_anim["stop"].wait(0.4)

        def _start_status() -> None:
            if _status_anim["thread"] and _status_anim["thread"].is_alive():
                return
            _status_anim["stop"] = _th.Event()
            _t0 = _th.Thread(target=_status_loop, daemon=True)
            _status_anim["thread"] = _t0
            _t0.start()

        def _stop_status() -> None:
            if _status_anim["stop"]:
                _status_anim["stop"].set()
            try:
                app.call_from_thread(status.update, "")
            except Exception:
                pass

        def update_current() -> None:
            app.call_from_thread(current.update, "".join(current_buf))

        def flush_current() -> None:
            text = "".join(current_buf)
            if text:
                # 模型输出是数据不是 markup: 转义 [ 防 arr[0] 被当数字色标签吞掉(围栏由 RichLog 识别)
                app.call_from_thread(log.write, text.replace("[", "\\["))
            current_buf.clear()
            app.call_from_thread(current.update, "")

        def flush_reasoning() -> None:
            if reasoning_buf:
                text = "".join(reasoning_buf).replace("[", "\\[")
                app.call_from_thread(log.thinking, text)
                reasoning_buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "agent_start":
                started[0] = True
                app._busy_inc()
                _start_status()
            elif t in ("agent_end", "steer_interrupt"):
                # 仅当本 agent 仍 started 时归位: steer_interrupt 后 run_agent_loop 的
                # finally 会再发一次 agent_end, 去重避免双扣计数。
                if started[0]:
                    started[0] = False
                    app._busy_dec()
                    if not app._agent_busy:
                        _stop_status()
                    app.call_from_thread(log.write, "")   # 回合结束 → 空行分隔下一回合(回合内紧凑)
            if t == "message_update":
                flush_reasoning()
                current_buf.append(event.get("delta", ""))
                update_current()
            elif t == "message_end":
                text = "".join(current_buf)
                if text:
                    # 同 flush_current: 模型输出按字面渲染(转义 [), ``` 围栏由 RichLog 拆段
                    app.call_from_thread(log.write, text.replace("[", "\\["))
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
                def _ts(n=name, a=args_str):
                    pending_tool[0] = log.tool_start(n, a)
                app.call_from_thread(_ts)
            elif t == "tool_execution_end":
                result = _fmt_result(str(event.get("result", "")))
                is_err = event.get("is_error")
                def _te(r=result, e=is_err):
                    if pending_tool[0]:
                        log.tool_end(pending_tool[0], r, e)
                        pending_tool[0] = None
                app.call_from_thread(_te)
            elif t == "cognitive":
                stage = event.get("stage")
                content = _fmt_result(str(event.get("content", ""))).replace("[", "\\[")
                app.call_from_thread(log.cognitive, stage, content, event.get("based_on"))
            elif t == "auto_retry_start":
                # 重试可见(PROBLEM-4): 动画只说「折射中」, 写一行让用户知道在第几次重试。
                err = str(event.get("error", ""))
                if len(err) > 60:
                    err = err[:59] + "…"
                app.call_from_thread(log.write,
                    f"[yellow]↻ 重试 {event.get('attempt', '?')}：{err}[/yellow]")
            elif t == "auto_retry_end":
                tail = "放弃" if event.get("gave_up") else "成功"
                app.call_from_thread(log.write,
                    f"[yellow]↻ 重试{tail}（共 {event.get('attempts', '?')} 次）[/yellow]")
            elif t == "error":
                # 兜底归位 busy: 正常路径 run_agent_loop 的 finally 已发 agent_end
                # (此时 started=False 跳过, 不抹仍在跑的别 agent); 直发 error 时
                # started 仍 True → 归位计数 + 停动画(防御层)。
                if started[0]:
                    started[0] = False
                    app._busy_dec()
                    if not app._agent_busy:
                        _stop_status()
                flush_current()
                # 裸异常文本 → 按内容分类给下一步指引(401/超时占大头, PROBLEM-4)
                err = str(event.get("error", ""))
                low = err.lower()
                if "401" in err or "403" in err or "api key" in low or "apikey" in low:
                    hint = "\n[dim]→ 检查 OPENAI_API_KEY / OPENAI_BASE_URL[/dim]"
                elif "timeout" in low or "超时" in err:
                    hint = "\n[dim]→ 网络超时，可重试或 /model 换模型[/dim]"
                else:
                    hint = ""
                app.call_from_thread(
                    log.write, f"[red bold]✗ 错误：[/red bold] [red]{err}[/red]{hint}")
            elif t == "patch_error":
                flush_current()
                app.call_from_thread(
                    log.write,
                    f"[yellow]⚠ {event.get('phase')}/{event.get('point')}: {event.get('error')} （已降级）[/yellow]")

        # 加载 ext/ + slash 指令(根解析不赌 cwd: 包根优先 + PRISM_EXT_DIR 覆盖, PROBLEM-3)
        from .commands import ext_root, load_commands
        ext_dir = ext_root()
        if not (ext_dir / "commands").is_dir():
            log.write(f"[yellow]⚠ 未找到 ext/ 插件目录（cwd={Path.cwd()}）："
                      f"指令/agent 配置未加载，请在项目根启动或设 PRISM_EXT_DIR[/yellow]")
        load_ext(ext_dir, default_registry, emit=emit)
        self.commands = load_commands(ext_dir, emit=emit)
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
        # 认知层(RLM): forest + 直觉(开关 PRISM_INTUITION=off/heuristic/small, 默认 small)
        import os as _os
        from .forest import SQLiteForest
        from .cog_patches import enable_cognitive_cycle
        self.agent.forest = SQLiteForest(".prism/forest.db", session_id=self.agent.name)
        _intui = _os.environ.get("PRISM_INTUITION", "small").lower()
        if _intui == "off":
            enable_cognitive_cycle(self.agent)
            from .cognitive import NullIntuition
            self.agent.intuition = NullIntuition()        # 关直觉
        elif _intui == "heuristic":
            enable_cognitive_cycle(self.agent)            # 启发式(intuition_model=None)
        else:                                              # small: glm-4.5-air
            from .model import OpenAIModel as _OM
            enable_cognitive_cycle(self.agent,
                intuition_model=_OM(model="glm-4.5-air", thinking_level="off"))
        self.agent.namespace["theme"] = ThemeCtl(self)
        for sub in subs:
            self.agent.namespace[sub.name] = sub
        self.model_name = getattr(self.agent.model, "model", "") or ""

        # 启动横幅三模式(PRISM_BANNER): art=5 行满饱和分光字母画(pi-faithful 观感, 默认);
        # line=单行紧凑; off=无。未指定时按屏高自动: <26 行降级 line(5 行画占 80×24 屏 37.5%, 批判轮1已证)
        _mode = _os.environ.get("PRISM_BANNER", "").lower()
        if _mode not in ("art", "line", "off"):
            try:
                _rows = _os.get_terminal_size().lines
            except OSError:
                _rows = 24
            _mode = "art" if _rows >= 26 else "line"
        if _mode == "off":
            pass
        elif _mode == "line":
            _parts = [p for p in ("Prism", self.model_name) if p]
            log.write(f"[accent]◆ {' · '.join(_parts)} · /help 查看指令[/accent]")
        else:
            _P = ["█████", "█   █", "█████", "█    ", "█    "]
            _R = ["████ ", "█   █", "████ ", "█  █ ", "█   █"]
            _I = ["█████", "  █  ", "  █  ", "  █  ", "█████"]
            _S = ["████ ", "█    ", "███  ", "   █ ", "████ "]
            _M = ["█   █", "██ ██", "█ █ █", "█   █", "█   █"]
            _letters = [_P, _R, _I, _S, _M]

            def _hue_hex(t: float) -> str:
                """t∈[0,1] → 满饱和光谱色(红→橙→黄→绿→青→蓝→紫)。"""
                import colorsys
                _r, _g, _b = colorsys.hsv_to_rgb(min(t, 1.0) * 0.84, 1.0, 1.0)
                return f"{int(_r * 255):02x}{int(_g * 255):02x}{int(_b * 255):02x}"

            # 逐字符全谱渐变(用户裁决: 颜色分布更细密): 每个方块按横向位置取色相,
            # 行间加相位差 → 棱镜分光的斜向流光(非旧的每行一色 5 条色带)
            for _r in range(5):
                _line = " ".join(_L[_r] for _L in _letters)
                _n = max(1, len(_line) - 1)
                _segs = []
                for _i, _ch in enumerate(_line):
                    if _ch == " ":
                        _segs.append(" ")
                    else:
                        _t = _i / _n * 0.80 + _r * 0.05   # 横向 0→0.80 + 行相位 0.05
                        _segs.append(f"[#{_hue_hex(_t)}]{_ch}[/]")
                log.write("".join(_segs))
            _parts = [p for p in ("Prism", self.model_name) if p]
            log.write(f"[accent]◆ {' · '.join(_parts)} · /help 查看指令[/accent]")

    # ── 输入路由(/ · @ · Python) ──────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        if not text.strip():
            return
        log = self.query_one("#transcript")
        log.user(text.replace("[", "\\["))   # 防 [ 被当 markup 标签吞掉(同 cognitive/tool 路径)
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
                avail = ['/' + c for c in sorted(self.all_commands())]   # 单一事实源
                log.write(f"[red]/{name} — 未知指令。可用：{' '.join(avail)}[/]")
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
                    log.write(f"[yellow]⚡ 转向 → {name}[/yellow]")
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
                if isinstance(e, (SyntaxError, NameError)):   # 自然语言误入 Python 直通 → 引导出路
                    log.write("[dim]（这是 Python 直通模式。要问 agent 请用 @Prism <问题>；/help 查看指令）[/dim]")
            for line in buf.getvalue().splitlines():
                log.write(line)  # pragma: no cover

    def _builtin_command(self, name: str):
        from .guard import revert_latest, list_backups
        if name == "revert":
            def _r(args):
                n = revert_latest(self.agent.emit)
                return f"[green]✓[/] 已回退 {n}（重启生效）" if n else "无改动可回退"
            return _r
        if name == "backups":
            def _b(args):
                bf = list_backups()
                if not bf:
                    return "无备份"
                return "改动备份栈（最近在上）：\n" + "\n".join(
                    f"  {i+1}. {o} → {b}" for i, (o, b) in enumerate(bf))
            return _b
        return None

    def make_subagent_emit(self, name: str):
        """给子 agent 的 emit: 事件汇入主 transcript, 带 [name] 标签 + pi 风格块。"""
        log = self.query_one("#transcript")
        app = self
        buf: list[str] = []
        pending: list = [None]
        started: list = [False]     # 本子 agent 是否处 started 未 end 状态(去重归位)
        tag = f"[{name}] "

        def flush() -> None:
            if buf:
                # 模型输出转义 [(防 markup 吞字, 同主 emit); 围栏由 RichLog 识别, tag 仍走 markup
                text = "".join(buf).replace("[", "\\[")
                app.call_from_thread(log.write, f"[dim blue]{tag}[/dim blue]{text}")
                buf.clear()

        def emit(event: dict) -> None:
            t = event.get("type")
            if t == "agent_start":
                started[0] = True
                app._busy_inc()
            elif t in ("agent_end", "steer_interrupt"):
                # 仅当本子 agent 仍 started 时扣计数, 去重(子 end 不抹主 agent busy)。
                if started[0]:
                    started[0] = False
                    app._busy_dec()
            if t == "message_update":
                buf.append(event.get("delta", ""))
            elif t == "message_end":
                flush()
            elif t == "tool_execution_start":
                flush()
                tool = event.get("tool_name", "?")
                args_str = _fmt_args(event.get("args", {}))
                def _ts(n=tag + tool, a=args_str):
                    pending[0] = log.tool_start(n, a)
                app.call_from_thread(_ts)
            elif t == "tool_execution_end":
                result = _fmt_result(str(event.get("result", "")))
                is_err = event.get("is_error")
                def _te(r=result, e=is_err):
                    if pending[0]:
                        log.tool_end(pending[0], r, e); pending[0] = None
                app.call_from_thread(_te)
            elif t == "cognitive":
                stage = event.get("stage")
                content = _fmt_result(str(event.get("content", ""))).replace("[", "\\[")
                app.call_from_thread(log.cognitive, stage, f"{tag}{content}", event.get("based_on"))
            elif t == "error":
                # 兜底归位(同主 emit: finally 已发 agent_end 则 started=False 跳过, 不抹主 agent)。
                if started[0]:
                    started[0] = False
                    app._busy_dec()
                flush()
                app.call_from_thread(
                    log.write, f"[dim blue]│[{name}][/dim blue] [red]错误：{event.get('error')}[/red]")
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


def _fmt_result(result: str, max_chars: int = 150, head_lines: int = 2, tail_lines: int = 2) -> str:
    """工具结果压缩: 头 head_lines + 尾 tail_lines(错误/断言/测试汇总都在尾部)。

    中间省略成行数提示; 提示拼在最后且不参与字符预算, 不会被 max_chars 自己吞掉。
    """
    if not result:
        return ""
    lines = result.strip().split("\n")
    hint = ""
    if len(lines) > head_lines + tail_lines:
        hint = f"…（还有 {len(lines) - head_lines - tail_lines} 行）"
        lines = lines[:head_lines] + lines[-tail_lines:]
    # 超字符预算时头尾行均摊截断(预留换行与提示的额度)
    if sum(len(l) for l in lines) + len(lines) - 1 + (len(hint) + 1 if hint else 0) > max_chars:
        per = max(16, (max_chars - len(hint) - len(lines)) // len(lines))
        lines = [l if len(l) <= per else l[:per - 1] + "…" for l in lines]
    return "\n".join(lines + ([hint] if hint else []))


def main() -> None:
    import os
    import sys
    if not os.getenv("OPENAI_API_KEY"):
        # 无 key 首启兜底: 不让 OpenAI 构造异常在 TUI 一帧未渲染前裸崩 15 行 traceback(PROBLEM-3)。
        print("未检测到 OPENAI_API_KEY，Prism 需要一个 OpenAI 兼容密钥才能启动。")
        print("请设置环境变量后再试：export OPENAI_API_KEY=\"你的密钥\"")
        print("（若走兼容网关，请另设 OPENAI_BASE_URL 指向其地址。）")
        sys.exit(2)
    if os.environ.get("PRISM_SMOKE"):
        PrismApp().run(headless=True)        # 入口端到端验证: 装配+on_mount, 不进终端
        return
    PrismApp().run()  # pragma: no cover  (入口)


if __name__ == "__main__":
    main()
