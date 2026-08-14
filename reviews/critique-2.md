# 批判轮2：键盘交互与操作流（评审人：终端 UI 键盘交互/反馈/错误恢复评审专家）

评审视角：按键绑定设计与惯例（emacs/readline/vim 惯例、Ctrl+C/Esc/Tab/方向键语义）、多行输入与光标移动手感、补全/历史翻阅交互、命令执行反馈（loading/中断/错误恢复）、流式中能否操作（打断/滚动）、按键冲突或不可达功能、粘贴处理、中文/IME 输入路径、终端原始模式下的按键解码健壮性。

方法：通读 `prism/tui/app.py`（按键分发 `_dispatch_key`）、`terminal.py`（`_win_translate` / `_parse_vt`）、`widgets.py`（`Input.on_key` / `SelectList`）、`shell.py`（`on_key` / `on_tab` / `_on_input_changed`）。写无头取证脚本（附录），实例化 `PrismApp` 经 `_build()`（不调 `on_mount`，不连网/不建 agent），手工喂入 `Key` 对象与 `_parse_vt` 解码的 escape 序列字节，断言状态变化。所有「按了什么 → 实际发生什么 → 应该发生什么」均有真实取证输出。

共 **12 条**问题。分布：**P0 ×1，P1 ×7，P2 ×4**。

> 不重复轮1（布局与信息架构）已提的问题。轮1 的「流式区撑爆屏幕」「输出区用思考样式」「border 死代码」等不在本视角范围内；本报告仅从键盘交互角度切入，凡与布局相关者一律不重复。

---

## 发现的问题

### [P0] 粘贴多行文本时，每个换行符都触发一次提交——没有 bracketed-paste 处理，代码块会逐行炸裂

- 证据：
  - `prism/tui/terminal.py:284-316` `_parse_vt` 把字节流逐字符解码，`\r` / `\n` 一律变成 `Key(key="enter")`（line 304-306）。没有任何 bracketed-paste 序列（`\x1b[200~` / `\x1b[201~`）的识别。
  - `prism/tui/app.py:166-173` 主循环把 `_parse_vt` 产出的每个 Key 逐一喂给 `_dispatch_key`，粘贴的字节流被拆成独立按键序列。
  - `prism/tui/widgets.py:358-364` `Input.on_key` 收到 `enter`（且 `key.shift` 为 False）就调用 `_input_submitted` 然后 `self.clear()`。
  - **取证（TEST 7）**：把 `"import os\rimport sys\rimport re"` 当作粘贴字节喂入 `_parse_vt`，产出的 Key 序列含 **2 个 enter**。再逐个 dispatch，结果产生了 **2 次独立提交**：
    ```
    keys from paste: ['i','m','p','o','r','t',' ','o','s','enter','i','m','p','o','r','t',' ','s','y','s','enter',...]; enter count=2
    submitted=['import os', 'import sys'], dock still has='import re'
    ```
    每一行换行都触发 `on_input_submitted` → `clear()`，最后一行残留在输入框。
- 为什么伤害核心体验：这是一个 coding agent，粘贴多行代码（函数定义、配置、日志）是**最高频**的操作之一。粘贴一个 Python 函数 `def foo():\n    return 42` 时，第一行 `def foo():` 被提交 → `exec("def foo():")` → **SyntaxError**；第二行 `    return 42` 再提交 → 又一个 **SyntaxError**。用户看到两行红色报错，完全不知道发生了什么。Windows 路径同理：`ReadConsoleInputW`（terminal.py:209-227）会把粘贴的每个 `\r` 拆成独立的 KEY_EVENT(VK_RETURN)。这是跨平台彻底不可用的多行输入路径。
- 具体改进建议：
  1. 在 `Terminal.__enter__`（terminal.py:135）进入 alt screen 时同时发送 `\x1b[?2004h` 开启 bracketed paste；`__exit__`（terminal.py:153）发送 `\x1b[?2004l` 关闭。
  2. 在 `_parse_vt`（terminal.py:284）识别 `\x1b[200~` ... `\x1b[201~`：把这段内容产出一个 `Key(key="__paste__", char=text)`，而不是逐字符解码。
  3. 在 `_dispatch_key`（app.py:214）或 `Input.on_key`（widgets.py:351）里处理 `__paste__`：把整段文本原样 `_insert`（保留换行），不触发提交。Windows 路径：在 `_read_loop_win` 检测连续的 VK_RETURN key-down + 快速间隔，合并为 paste 事件；或改用 `ReadConsoleInputW` 的 paste 标志。
  4. 兜底：至少在 `Input.on_key` 的 `enter` 分支前检查「当前帧内是否已 submit 过一次」，对极短间隔的连续 enter 做合并保护。

---

### [P1] 命令补全浮层的上下方向键完全失效——被 transcript 滚动拦截，用户无法选择列表项

- 证据：
  - `prism/tui/app.py:252-260` `_dispatch_key` 里，`up`/`down` 在单行输入时**无条件**走 transcript 滚动并 `return`，**早于**焦点 widget 的 `on_key`：
    ```python
    if k in ("up", "down"):
        try:
            dock = self.query_one("#dock")
            if "\n" not in (dock.value or ""):
                (log.scroll_up if k == "up" else log.scroll_down)(3)
                self.request_render(); return    # ← return，永不抵达 Input
    ```
  - `prism/tui/widgets.py:382-389` `Input.on_key` 里**明明写了**补全导航逻辑：
    ```python
    if k == "up":
        if hasattr(self.app, "_completion_active") and self.app._completion_active():
            self.app._completion_move(-1); return True
        self._move_line(-1); return True
    ```
    但这段代码**在正常流程中永远不可达**，因为用户输入 `/mod`（单行、无 `\n`）时 up/down 在 `_dispatch_key` 就被拦截了。
  - **取证（TEST 1）**：`app.commands` 设 6 条命令，输入 `/` 触发浮层（6 个候选项），按 `down`：
    ```
    selected_before=0, selected_after_down=0, n_items=6
    → 选中索引纹丝不动（0→0），因为 DOWN 被 transcript scroll 吃掉了
    log._follow=False → DOWN 确实走了 scroll_down 路径
    ```
    而绕过 `_dispatch_key` 直接调 `dock.on_key(Key("down"))` 时，选中索引正确变为 1（`selected after direct dock.on_key('down')=1`），证明 Input 代码本身是对的，只是**分发层拦截**导致不可达。
- 为什么伤害体验：浮层画了 `▸` 高亮标记、画了 `(1/6)` 分页指示，暗示「这是可选列表」。用户本能地按 ↓ 想翻到 `/thinking`，结果什么都没发生——光标不动、选中不变，只有背后的 transcript 滚了一下。用户只能靠**继续打字过滤**或盲选第一项（Tab）。这是一个「看起来能用、实际不能用」的交互陷阱。
- 具体改进建议：
  - 在 `_dispatch_key`（app.py:240）的 scroll 拦截**之前**加补全优先判断：
    ```python
    if k in ("up", "down") and getattr(self, "_completion_active", lambda: False)():
        self._completion_move(-1 if k == "up" else 1)
        self.request_render(); return
    ```
    这样浮层打开时 up/down 归补全，关闭后才归滚动/光标。

---

### [P1] Ctrl+C 在 agent 运行时清空输入框而非中断——唯一的「中断」键是 Escape，且没有任何地方提示

- 证据：
  - `prism/tui/app.py:217-233` `_dispatch_key` 的 ctrl+c 分支：
    ```python
    if k == "ctrl+c":
        inp = self._focusable[self._focus_idx] ...
        if inp is not None and getattr(inp, "value", ""):
            inp.clear(); self.request_render(); return   # ← 有文本就清空，直接返回
        # 下面才是「双击退出」逻辑
    ```
    只要输入框有文本，Ctrl+C **永远**走清空路径，**永不检查** `_agent_busy`，**永不调用** `agent.stop()`。
  - `prism/shell.py:41-47` 中断逻辑只挂在 `on_key` 的 `escape` 上：
    ```python
    def on_key(self, event) -> None:
        if event.key == "escape" and self._agent_busy:
            if self.agent: self.agent.stop() ...
    ```
  - Header 提示（`widgets.py:16`）是 `"/ commands · @ agents · python"`，Footer 显示 `model · thinking · busy`——**没有任何位置**告知用户「Esc 中断 / Ctrl+C 清空」。
  - **取证（TEST 3）**：`_agent_busy=True`，输入 `"follow up question"`，按 Ctrl+C：
    ```
    dock.value='follow up question' → dock.value=''  (文本被清空)
    agent.stop called: False  → agent 未被中断
    ```
  - **取证（TEST 12）**：输入框为空时连按两次 Ctrl+C，**直接退出整个 app**，即便 agent 正在运行：
    ```
    1st Ctrl+C (empty): quit=False
    2nd Ctrl+C (empty): quit=True, agent.stop called=False
    → 用户误触双击就丢失整个会话，agent 也没被优雅中断
    ```
- 为什么伤害体验：Ctrl+C 是全行业通用的「中断当前操作」心智（Ctrl+C in shell = SIGINT，in REPL = KeyboardInterrupt）。这里它却「清空输入框」。用户在 agent 跑了一半时想中断（最常见的需求），按 Ctrl+C，结果**自己刚打的 follow-up 被删了，agent 继续跑**。用户只能干瞪眼，或者乱按到 Escape 才发现能中断——但 Escape 的语义（取消/关闭浮层）和「中断后台进程」相去甚远，全靠猜。
- 具体改进建议：
  - 在 `_dispatch_key`（app.py:217）的 ctrl+c 分支里**优先判断 busy**：
    ```python
    if k == "ctrl+c":
        if self._agent_busy and self.agent:
            self.agent.stop()
            ...log.write("[yellow]⏹ 已中断[/yellow]")
            return
        # 非忙时才走「清空 / 双击退出」逻辑
    ```
  - 在 Header（widgets.py:16）或 Footer 加一行 hint：`esc interrupt · ctrl+c clear`，让中断路径可见。

---

### [P1] 没有任何输入历史——Up 键不回溯上一条命令，而是滚动 transcript

- 证据：
  - `prism/tui/widgets.py:299-404` `Input` 类**没有** `history` / `_history` / `_hist_idx` 任何属性（取证 `hasattr(dock, "history")=False`）。整个 `on_key` 没有任何 `history` 引用。
  - `prism/tui/app.py:252-260` Up/Down 在单行时被截走做 transcript 滚动。
  - **取证（TEST 2）**：先提交 `"print(1)"`，再在输入框打 `"x"`，按 Up：
    ```
    before_up='x', after_up='x'  → 输入框内容纹丝不动，Up 没有回溯到上一条命令
    ```
- 为什么伤害体验：每一个 shell、REPL、coding agent TUI（bash / zsh / ipython / claude-code / pi）都用 Up/Down 翻阅命令历史。这是肌肉记忆级的功能。这里 Up 不仅不回溯，还偷偷滚动了背后的 transcript（用户可能根本没注意到 transcript 动了，只觉得「按了没反应」）。用户想重复上一条命令只能重新打一遍。
- 具体改进建议：
  - 在 `Input.__init__`（widgets.py:309）加 `self.history: list[str] = []` 和 `self._hist_idx = -1`。
  - 在 `on_input_submitted`（app.py:149-150）成功提交后 `dock.history.append(value)`。
  - 在 `_dispatch_key`（app.py:252）的 up/down 拦截之前，判断焦点在 Input 且单行时：Up → `hist_idx -= 1` 回填 `dock.value`；Down → `hist_idx += 1`。回填时把 `dock.pos` 置末尾。
  - transcript 滚动改用 PageUp/PageDown（已有），不要抢占 Up/Down。

---

### [P1] Escape 不能关闭命令补全浮层——通用「取消」键在浮层打开时是死的

- 证据：
  - `prism/tui/app.py:214-267` `_dispatch_key` 对 `escape` 没有任何特殊处理，直接走到 line 262 `self._focusable[...].on_key(key)`。
  - `prism/tui/widgets.py:351-404` `Input.on_key` **不处理** `escape`（不在任何 if 分支里），返回 `False`。
  - `prism/shell.py:41-47` `on_key` 只在 `_agent_busy=True` 时响应 escape。闲时 escape 整条链路无人处理。
  - **取证（TEST 4）**：输入 `/` 打开浮层，按 Escape：
    ```
    overlays before Escape: 1
    overlays after Escape: 1  → 浮层纹丝不动，Escape 完全无效
    ```
    用户只能退格删掉 `/` 才能让浮层消失（`_on_input_changed` 的非 `/` 分支调 `_hide_cmd_overlay`）。
- 为什么伤害体验：Escape 是终端/桌面应用的通用「关闭弹层/取消」键。浮层弹出来挡在内容上方（轮1 已证浮层宽度铺满整屏），用户想关掉它，按 Escape——没反应。这是违反直觉的。用户只能猜测「是不是要退格」，但退格会把 `/` 删掉导致已输入的前缀丢失。
- 具体改进建议：
  - 在 `_dispatch_key`（app.py:214）开头加 escape 优先处理：
    ```python
    if k == "escape":
        if getattr(self, "_completion_active", lambda: False)():
            self._hide_cmd_overlay(); self.request_render(); return
    ```
  - 或在 `Input.on_key`（widgets.py:351）加 `if k == "escape": ...hide overlay...; return True`。

---

### [P1] Home/End/PageUp/PageDown 被永久绑死给 transcript 滚动——Input 里的 home/end 处理是死代码，多行编辑无法用 Home/End 跳行首行尾

- 证据：
  - `prism/tui/app.py:244-251` `_dispatch_key` 对 `pageup`/`pagedown`/`home`/`end` **无条件**走 transcript 滚动并 `return`，**不看输入框是否多行、不看浮层是否打开**：
    ```python
    if k == "home":  log.scroll_home(); ...; return
    if k == "end":   log.scroll_end(); ...; return
    ```
  - `prism/tui/widgets.py:376-381` `Input.on_key` 里**写了** home/end 行首行尾跳转：
    ```python
    if k == "home":
        self.pos = self._line_starts()[self._cursor_rc()[0]]; return True
    if k == "end":
        ...
    ```
    但取证证明这段代码**永远不可达**。
  - **取证（TEST 5）**：多行输入 `"line1\nline2"`，光标置于 line2 中间，通过 `_dispatch_key` 发 `home`：
    ```
    pos_before=10, pos_after=10  → 光标没动（Home 被 scroll 吃了）
    ```
    绕过分发层直接调 `dock.on_key(Key("home"))` 时，光标正确移到行首：
    ```
    pos_before=10, pos_after=6  → 证明 Input 的 home 代码是对的，只是分发层拦截导致死代码
    ```
  - **取证（TEST 6）**：`pageup`/`pagedown`/`home`/`end` 四个键全部被拦截，Input 对 `pageup` 返回 `False`（完全不认识）。
- 为什么伤害体验：多行编辑时 Home/End 跳行首行尾是基本编辑能力。这里 Ctrl+A 能到行首（TEST 15 证实），但 Home 不行——同一个功能两个键一个能用一个不能用，极其混乱。而 PageUp/PageDown 永远只能滚 transcript，即便用户正卡在一个 6 行的多行输入框里想翻看自己写的内容。
- 具体改进建议：
  - 在 `_dispatch_key`（app.py:244）的滚动拦截前，把 `home`/`end` 先交给焦点 widget：`if self._focusable[...].on_key(key): return`。只有 widget 不吃（返回 False）时才回退到 transcript 滚动。
  - PageUp/PageDown 保留给 transcript（它们在单行编辑器里本就少见），但 Home/End 必须归 Input。

---

### [P1] Shift+Enter 多行换行只在 Windows 有效——POSIX（Mac/Linux）下 Shift+Enter 等同于普通 Enter（提交），多行输入彻底无法用键盘完成

- 证据：
  - `prism/tui/widgets.py:358-364` 换行依赖 `key.shift`：
    ```python
    if k == "enter":
        if key.shift:
            self._insert("\n")
        else:
            self.app._input_submitted(...)   # 提交
    ```
  - `prism/tui/terminal.py:284-316` `_parse_vt`（POSIX 路径）把 `\r` 解码为 `Key(key="enter", char="")`，**shift 字段永远是默认值 False**（line 304-306，构造 Key 时没传 shift）。
  - **取证（TEST 9）**：
    ```
    POSIX Enter: key='enter', shift=False  → 走提交分支
    Windows Shift+Enter (Key(key="enter", shift=True)): dock.value='\n'  → 换行成功
    POSIX Enter after typing 'hello': submitted=['hello']  → 提交了，没换行
    ```
    部分终端的 Shift+Enter 发 `\x1b\r`（ESC + CR），`_parse_vt` 把它拆成两个 Key：`['escape', 'enter']`——先触发 agent 中断（Escape），再触发提交（Enter）。
- 为什么伤害体验：`Input.max_lines = 6`（widgets.py:302）、注释写着「Shift+Enter 换行(pi 同款)」（widgets.py:300），代码明确设计了多行能力。但这能力在 Mac/Linux 上**根本无法触发**——用户按 Shift+Enter，输入被提交了。多行输入框形同虚设。考虑到大量开发者在 Mac/Linux 终端工作，这是跨平台可用性硬伤。
- 具体改进建议：
  - 在 `_parse_vt`（terminal.py:284）增加 kitty keyboard protocol（`CSI > 1u` 查询 + `CSI ... u` 解码）或至少处理 `\x1b\r` → `Key(key="enter", shift=True)`。
  - 或提供替代换行键（如 `Ctrl+J` / `Alt+Enter`），在 `Input.on_key`（widgets.py:358）加 `if k == "ctrl+j": self._insert("\n"); return True`，这在所有平台都能稳定解码（`\n` = Ctrl+J）。
  - Header 加提示告知多行换行键。

---

### [P1] POSIX `_parse_vt` 丢失 CSI 序列的全部修饰键信息——Shift/Ctrl/Alt + 方向键全部退化为裸方向键，Alt+字母注入多余 Escape

- 证据：
  - `prism/tui/terminal.py:290-299` `_parse_vt` 解析 CSI 时，只取末字母映射方向，**完全忽略**中间的修饰参数（`;2` = Shift, `;5` = Ctrl, `;3` = Alt），构造 Key 时 shift/ctrl/alt 全留默认 False：
    ```python
    name = _VT_CSI.get(seq.rstrip("0123456789;") and seq or seq, "")
    if not name and seq and seq[-1] in _VT_CSI:
        name = _VT_CSI[seq[-1]]
    out.append(Key(key=name or f"csi_{seq}", char=""))   # ← 无 ctrl/alt/shift
    ```
  - `prism/tui/terminal.py:301-303` Alt 前缀（`\x1b` + 字符）被拆成独立 Escape：
    ```python
    elif ch == "\x1b":
        out.append(Key(key="escape", char="")); i += 1   # ← Alt+X → Escape + X
    ```
  - **取证（TEST 8）**：
    ```
    Shift+Up (ESC[1;2A): key='up', shift=False  → 修饰键丢失
    Ctrl+Right (ESC[1;5C): key='right', ctrl=False  → 无法绑定 Ctrl+方向键跳词
    Alt+X (ESC x): keys=[('escape',''), ('x','x')]  → 注入了多余 Escape，可能误触发 agent 中断
    ```
- 为什么伤害体验：Windows 路径（`_win_translate`，terminal.py:98-115）**正确地**设置了 ctrl/alt/shift，所以 Windows 用户有修饰键；但 POSIX 用户的所有 Ctrl+Arrow（跳词）、Alt+Backspace（删词）、Shift+Arrow（选区）全部失效。更危险的是 Alt+任何字母会先注入一个 Escape——如果 agent 正忙，这个 Escape 会触发 `on_key` 的中断逻辑（shell.py:42），用户按 Alt+F 想做什么，结果 agent 被中断了。这是一个隐蔽的副作用 bug。
- 具体改进建议：
  - 在 `_parse_vt`（terminal.py:292-299）解析 CSI 的数字参数时提取修饰符：`params = seq.split(";")`，若 `len(params) >= 2`，`mod = int(params[1]) - 1`，按位解析 `shift = mod & 1`、`alt = mod & 2`、`ctrl = mod & 4`，传入 `Key(..., ctrl=ctrl, alt=alt, shift=shift)`。
  - 对 `\x1b` + 单字符（非 `[`）的序列，应合并为 `Key(key=char, char=char, alt=True)` 而非拆成 Escape + 字符。需要一个「向前看一格」的缓冲：如果 `\x1b` 后面紧跟一个普通可打印字符且不是 `[`，就产出 `alt+char`。

---

### [P2] transcript 向上滚动后，新的流式输出被静默隐藏——没有「有新内容」指示，也没有「不在底部」提示

- 证据：
  - `prism/tui/widgets.py:171-181` `scroll_up` 把 `_follow` 设为 False。之后 `draw`（widgets.py:193-207）只在 `_follow=True` 时才贴底。新内容 `write()` 只 append 到 entries，不改 `_follow`、不设任何标记。
  - **取证（TEST 14）**：先写 30 行历史，`scroll_up(10)` 让 `_follow=False`，再 `write("NEW IMPORTANT OUTPUT")`：
    ```
    after scroll-up: _follow=False
    after new output: _follow=False  → 新内容不显示
    RichLog has NO new-content/unread indicator: True  → 没有任何「有新内容」属性
    ```
- 为什么伤害体验：用户向上滚动读历史时，模型可能正好流式输出了关键回答。用户盯着旧内容看了半天，完全不知道下面已经有新内容了。等用户按 End 回到底部才发现——但这段时间用户的注意力完全被误导。同类产品（pi / claude-code）在滚动离开底部时都会显示「↓ N new lines」提示。
- 具体改进建议：
  - 在 `RichLog`（widgets.py:61）加 `self._unread = 0`，在 `_follow=False` 时每次 `write()` 递增。
  - 在 `draw`（widgets.py:193）末尾，若 `_follow=False` 且 `_unread > 0`，在 transcript 底部画一行 `[dim]↓ {_unread} new lines · press End[/dim]`。
  - `scroll_end` / `scroll_down` 回到底部时 `_unread = 0`。

---

### [P2] 缺少标准 readline 绑定：Ctrl+D（删字符/退出）、Ctrl+F/B（前后移字符）、Ctrl+L（清屏）、Ctrl+P/N（历史前后）全部不存在

- 证据：
  - `prism/tui/widgets.py:390-404` `Input.on_key` 只实现了 `ctrl+a`/`ctrl+e`/`ctrl+u`/`ctrl+k`/`ctrl+w`，**没有** `ctrl+d`/`ctrl+f`/`ctrl+b`/`ctrl+l`/`ctrl+p`/`ctrl+n`。
  - **取证（TEST 13）**：对每个绑定调 `dock.on_key(Key("ctrl+x", ctrl=True))`，全部返回 `False`（未处理），value 和 pos 不变：
    ```
    ctrl+d: handled=False, value='hello'(was 'hello'), pos=3(was 3)
    ctrl+f: handled=False ...
    ctrl+b: handled=False ...
    ctrl+l: handled=False ...
    ctrl+n: handled=False ...
    ctrl+p: handled=False ...
    ```
- 为什么伤害体验：readline/emacs 按键是终端用户的肌肉记忆。Ctrl+A/E 能用但 Ctrl+F/B 不能用（前者靠 Input、后者不存在），Ctrl+W 能删词但 Ctrl+D 不能删光标处字符——这种「一半有一半没有」比完全没有更让人困惑，因为用户会假定「既然 Ctrl+A 行，Ctrl+F 也该行」。
- 具体改进建议（在 `Input.on_key`，widgets.py:390 附近补）：
  - `ctrl+d`: 若 `self.pos < len(self.value)`: `self._delete_fwd()`；否则（空输入）可触发 `app.exit()`（EOF 语义）。
  - `ctrl+f`: `self.pos = min(len(self.value), self.pos + 1)`。
  - `ctrl+b`: `self.pos = max(0, self.pos - 1)`。
  - `ctrl+l`: `app.request_render()` + 清 transcript 视口（或滚到底）。
  - `ctrl+p`/`ctrl+n`: 接入历史（与上面历史问题联动）。

---

### [P2] Ctrl+A 能到行首但 Home 不能——同一功能两个键一个灵一个死，readline 与功能键体验割裂

- 证据：
  - `prism/tui/widgets.py:390-391` `ctrl+a` 走 Input.on_key（不被 `_dispatch_key` 拦截），**有效**。
  - `prism/tui/widgets.py:376-377` `home` 也在 Input.on_key 里写了，但被 `_dispatch_key`（app.py:248）拦截，**无效**。
  - **取证（TEST 15）**：
    ```
    Ctrl+A via dispatch: pos=0  → 成功移到行首
    Home via dispatch: pos=5    → 没动（被 scroll 拦截）
    ```
- 为什么伤害体验：功能键（Home/End）和 Ctrl 组合键（Ctrl+A/E）在用户心智里是等价的行首行尾跳转。这里 Ctrl+A 灵敏、Home 失灵，用户会反复试 Home、以为键盘坏了。这在「Home/End 被拦截」问题里已提到根因，此处单独列出是因为它最直观地体现了「按键绑定不一致」的体感伤害。
- 具体改进建议：同 Home/End 问题——把 home/end 优先交给 Input。修好后 Ctrl+A 和 Home 行为统一。

---

### [P2] Ctrl+C 清空输入框时零反馈、零撤销——长文本一键蒸发，用户无从恢复

- 证据：
  - `prism/tui/app.py:218-222` 有文本时 Ctrl+C 直接 `inp.clear()` + `request_render()` + `return`，不写任何 transcript 消息。
  - **取证（TEST 11）**：
    ```
    dock.value='a very long and carefully typed command'
    → after Ctrl+C: dock.value=''
    lines_before=0, lines_after=0  → transcript 没有任何提示，文本无声消失
    ```
- 为什么伤害体验：用户打了半天的命令，手滑碰到 Ctrl+C，文本瞬间消失，屏幕上没有任何「已清空」的提示，也没有撤销。对比 pi 的实现：pi 在 Ctrl+C 清空后会写一行 `(input cleared)` 让用户知道发生了什么。这里连这都没有，用户可能以为「是不是没按到」，再按一次——直接触发「双击退出」，整个 app 关了。
- 具体改进建议：
  - 在 `app.py:220` 的 `inp.clear()` 后加 `log.write("[dim](input cleared)[/dim]")`。
  - 或保留被清空的文本到 `inp._last_cleared`，支持 Ctrl+Y / Undo 恢复（yank）。

---

## 本轮取证脚本（附录）

取证脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_key_forensics.py`。完整输出：`C:/Users/cty18/AppData/Local/Temp/prism_key_evidence.txt`。

要点：
- `make_app()` 实例化 `PrismApp`，调 `_build()`（compose + CSS + mount），**不调 `on_mount`**（避免连网/建 agent/写 banner），手工填 `app.commands` / `app.agent`（FakeAgent stub）。
- `key(k, char="", ctrl=False, ...)` 构造 `terminal.Key` 对象，模拟真实按键。
- `dispatch_str(app, s)` 把可打印字符逐个经 `app._dispatch_key` 喂入（走真实分发路径，含 scroll 拦截）。
- `type_str(dock, s)` 直接调 `dock.on_key`（绕过分发层，用于对照证明 Input 代码本身是否正确）。
- `_parse_vt(bytes)` 直接调用 POSIX escape 序列解码器，验证修饰键丢失 / 粘贴拆分 / Shift+Enter。
- 16 组测试覆盖：补全导航、历史缺失、Ctrl+C 中断语义、Escape 关浮层、Home/End 死代码、多行粘贴、修饰键丢失、Shift+Enter 跨平台、Ctrl+U/K/W 编辑、Ctrl+C 静默清空、双击退出、readline 绑定缺失、滚动无指示、Ctrl+A vs Home 一致性、提交边界。

核心取证模式（「按了什么 → 实际发生 → 应发生」三段式）：
```python
# 证明 _dispatch_key 拦截 vs Input 代码本身正确
app._dispatch_key(key("down"))      # 实际路径：selected 不变（0→0），被 scroll 吃了
dock.on_key(key("down"))            # 对照路径：selected 变了（0→1），证明 Input 代码对
# 结论：分发层拦截导致功能不可达
```

```python
# 证明 POSIX 修饰键丢失
_parse_vt(b"\x1b[1;2A")[0]  # Shift+Up → Key(key='up', shift=False)  应为 shift=True
_parse_vt(b"\x1b[1;5C")[0]  # Ctrl+Right → Key(key='right', ctrl=False)  应为 ctrl=True
```
