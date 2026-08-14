# 批判轮4：文案可读性与信息展示（评审人：终端 UI 文案/文本展示评审专家）

评审视角：界面文案质量（中英混杂规则、术语一致性、语气、错别字、大小写、标点全半角）、文本展示正确性（CJK 宽字符宽度、emoji/组合字符/ZWJ、tab 展开、超长行截断/省略号策略、硬折行是否在单词/CJK 中间断开、markup 标签在截断处泄漏）、滚动体验（滚动粒度、跳变）、历史记录的信息保真（工具调用长输出展示、代码块语法高亮/等宽、diff）、时间戳/元信息格式、空态文案。

方法：通读 `prism/tui/buffer.py`（`put`/`write`/宽字符贴边）、`markup.py`（`char_width`/`wrap_segments`/`parse_markup`）、`widgets.py`（`Static.draw`/`RichLog`/`Input`）、`shell.py`（`_fmt_result`/`_fmt_args`/transcript 组装/文案）。写无头取证脚本（附录），直接调 `char_width`/`wrap_segments`/`Buffer.write`/`_fmt_result`/`_fmt_args`，并实例化 `PrismApp()._build()` 手工喂入中文长句、CJK+emoji 混排、Makefile tab 缩进、markdown 代码块、超长工具输出，在 80×24 / 40×24 / 20×20 下 `_render_frame` + `render_plain` dump 逐行结果。所有渲染片段/宽度数值均出自真实取证，非脑补。

共 **11 条**问题。分布：**P0 ×1，P1 ×5，P2 ×5**。

> 不重复轮1（布局/IA）、轮2（键盘，含「滚动无 unread 指示」）、轮3（色彩）。轮3 批过 markup 色彩与浅色失效——本报告只在**文本展示正确性与文案**层面给新证据（如 tab 静默丢弃、单词中间断行、emoji 宽度错算、代码围栏泄漏、工具结果截断策略、文案中英混杂）。

---

## 发现的问题

### [P0] 模型输出的代码块原样泄漏 ``` 围栏，且无语法高亮 / 无等宽 / 无缩进保护——coding agent 的主输出可读性塌方

- 证据：
  - `prism/shell.py:180-185` `flush_current()` 把流式累积的**原始文本** `"".join(current_buf)` 直接 `log.write(text)`；`message_end`（shell.py:206-211）同理 `log.write(text)`。整条路径**没有任何 markdown / 代码块解析**。
  - `prism/tui/widgets.py:88-91` `RichLog.write()` 只做 `markup.split("\n")` 逐行存为 `_LineUnit`，**不识别 ``` ``` ``` 围栏，也不区分代码行与正文行**。
  - 取证（喂入 `这是代码:\n\`\`\`python\ndef foo():\n    return 42\n\`\`\`\n完毕`，回读 `transcript.lines`）：
    ```
    '这是代码:'
    '```python'      ← 围栏当作普通文本行原样出现在屏幕上
    'def foo():'
    '    return 42'
    '```'            ← 结束围栏也是噪音行
    '完毕'
    ```
  - 代码体（`def foo():`）与正文（`这是代码:`）走**完全相同的 `_LineUnit`**（widgets.py:31-32），同样的 `text` 色、同样的按显示宽度硬折行——代码既无等宽保证（终端本就等宽，但无视觉区隔）、也无语法着色、也无背景块包裹，和散文混为一团。
- 为什么伤害核心体验：这是一个 **coding agent**。模型每次回答几乎都带代码块（重构方案、补丁、命令、配置）。现在用户看到的不是「一段被框起、高亮的代码」，而是夹在散文里的几行裸文本 + 上下各一行刺眼的 ``` ```python ``` / ``` ``` ``` 噪音。代码与解释毫无视觉边界，扫读时无法一眼定位「哪里是代码、哪里是说明」。同类产品（claude-code / pi / Cursor 终端）对代码块都有等宽 + 语法色 + 缩进保留 + 围栏吞掉。这里是把主输出降级成纯文本流。
- 具体改进建议：
  1. 在 `flush_current`/`message_end`（shell.py:181-211）写 transcript 前，对累积文本做**最小 markdown 代码块识别**：按 ``` ```lang ... ``` ``` 拆段，代码段产出独立的 `_BlockUnit`（复用 widgets.py:35 的 block 机制 + `tool_pending_bg` 或新增 `code_bg`），并吞掉围栏行。
  2. `RichLog` 增加一个 `code(lang, src)` API（类比 `tool_start`），代码块用等宽（终端天然）+ 背景色带 + 不做按词折行（代码只在换行符处断，超长行右侧裁剪 + 提示），保留缩进。
  3. 起码的止损：在 `write()`（widgets.py:88）里识别首尾 ``` ``` ``` 行并过滤掉，别让围栏字面出现在屏幕。

---

### [P1] TAB 被静默丢弃（`char_width` 返回 0 → `Buffer.put` 直接 return）——工具输出里的缩进 / Makefile / 表格对齐无声崩塌

- 证据：
  - `prism/tui/markup.py:20-22` `char_width`：`if not ch or ord(ch) < 32: return 0`。`\t`(U+0009) 命中此分支 → **宽度 0**。
  - `prism/tui/buffer.py:36-38` `Buffer.put`：`w = char_width(ch); if w == 0: return`——**宽度 0 的字符被直接丢弃，连 cell 都不写**。
  - `prism/tui/buffer.py:50-58` `Buffer.write`：`self.put(cx, y, ch, style); cx += char_width(ch) or 1`——tab 被 `put` 丢弃，但 `cx` 因 `or 1` 仍前进 1 列。结果是「tab 字符消失、光标前进 1」，留下一个**本就存在的空白 cell**。
  - 取证（Buffer 30×2 渲染 `clean:\n\t\trm -f *.o`）：
    ```
    LEADING-TAB row 0 'clean:                        '
    LEADING-TAB row 1 '  rm -f *.o                   '   ← 两个 \t\t 只换来 2 格, 且是「幽灵空格」
    ```
    一个本该跳到第 8/16 列的制表符，变成了**前进 1 格、字符蒸发**。Makefile 的 recipe（`<TAB>$(CC) ...`）必须用 tab，现在渲染成 1 格缩进；Python/Go 里 tab 缩进的代码，缩进层级被压平。
  - 取证（`char_width` 单测）：`\t → 0`、`\n → 0`、组合重音 U+0301 → **1（应为 0）**、变体选择符 VS16 U+FE0F → **1（应为 0）**、零宽连接 ZWJ U+200D → **1（应为 0）**。
- 为什么伤害阅读体验：coding agent 最高频的动作就是 `Read` 工具读文件、`bash` 跑命令、`grep` 搜结果——这些输出里 tab 无处不在（Makefile、tab 缩进源码、`git log --oneline` 的表头、pytest/jest 的对齐输出、TSV）。tab 一律蒸发 + 进 1 格，意味着**所有 tab 缩进被压成 1 空格、所有 tab 对齐表格错位**。用户读到错乱的缩进会误判代码结构，读到错位的表格会误读数据。而这一切**没有任何提示**——用户以为文件本来就是这样的。
- 具体改进建议：
  - `char_width`（markup.py:18-22）明确把**宽度 0 的「可见空白/控制符」与「真零宽组合符」分开**：组合符（`unicodedata.category(ch)` 以 `'M'` 开头、或属 ` Cf` 的 ZWJ U+200D / VS U+FE00-FE0F）应返回 0 且由 `put` 叠到前一格；而 `\t` **不应进 `char_width=0` 这条死路**。
  - `Buffer.put`/`write`（buffer.py:36、57）对 `\t` 做 tab-stop 展开：`cx = (cx // TABWIDTH + 1) * TABWIDTH`（`TABWIDTH=8` 或 4），填空格到下一站；不要 `cx += char_width(ch) or 1` 一刀切。
  - 至少先让 `write`（buffer.py:53-57）的循环里 `if ch == "\t": cx = _next_tabstop(cx); continue`，避免 tab 蒸发。

---

### [P1] `wrap_segments` 只按显示宽度硬折行，无词边界感知——英文单词 / 标识符被从中间切开（`configuratio`+`n`、`value/po`+`s`）

- 证据：
  - `prism/tui/markup.py:173-185` `wrap_segments`：唯一换行条件是 `if rows[-1] and col + cw > width`——**只要放不下就换，完全不看字符是否是空格 / 标识符中间**。无 greedy word-wrap、无 break-long-word 例外标记、无连字符。
  - 取证（`The configuration parameter determines how the renderer processes long words`，width=20）：
    ```
    行0: 'The configuration pa'   ← 'parameter' 被切成 'pa' | 'rameter'
    行1: 'rameter determines h'   ← 'determines' 切成 'h' | 'ow' 之后的 'ow'
    行2: 'ow the renderer proc'   ← 'processes' 切成 'proc' | 'esses'
    行3: 'esses long words'
    ```
  - 在真实窄终端（40×24）渲染中更触目惊心，标识符被劈开：
    ```
     9│ 和 _cursor_rc，Input 退化为纯绘制  (ba       ← "(based_on" 切成 "(ba" | "sed_on"
    10│ sed_on widgets.py:320)
    13│ ，保留接口即可  (based_on 重构方案)             ← 逗号被挤到行首孤悬
    ```
    `value/pos`、`ctrl+u/ctrl+k`、`_line_starts` 这些代码标识符全被从中间斩断。
- 为什么伤害阅读体验：coding agent 的输出里满是英文标识符、路径、函数名。读者靠「词的整体」识别 token，把 `configuration` 切成 `configuratio`+`n`、把 `_line_starts` 切成 `_line_star`+`ts`（20×20 取证里就有 `_line_star` / `ts，保留`），等于强迫读者每行做一次脑内拼接，阅读速度骤降、且极易误读（`value/po` 看着像另一个东西）。CJK 因为每字皆可断所以没事，但只要混进英文/代码，断点就乱来。这是文本展示正确性的硬伤。
- 具体改进建议：
  - 在 `wrap_segments`（markup.py:182）的换行判定前先回溯到最近的空格/标点边界：若当前 token 是 ASCII 字母数字/下划线序列且会被切断，优先在它之前的空白处断行；CJK 字符仍允许任意断点。
  - 对超长不可断 token（如长 URL / 长 path）保留「按宽度硬切」作为兜底，但加一个 `allow_break=True/False` 标志，默认 ASCII 词内不切。
  - 参考算法：greedy + `textwrap.wrap` 的 break_long_words 语义，但按显示宽度（`char_width`）而非 codepoint 数。

---

### [P1] emoji / 组合符 / ZWJ 宽度错算——`👨‍👩‍👧` 被算成 8 列、组合重音占独立 cell，buffer 与终端错位

- 证据：
  - `prism/tui/markup.py:18-22` `char_width` 只看 `east_asian_width(ch) in ("W","F")`，**对零宽字符（组合符、变体选择符、ZWJ）一律按 `east_asian_width` 的 `A`/`N` 返回 1**，而非 0。
  - 取证（`char_width` 逐 codepoint）：
    ```
    组合重音 U+0301  east_asian_width=A  char_width=1   ← 应 0
    VS16    U+FE0F  east_asian_width=A  char_width=1   ← 应 0
    ZWJ     U+200D  east_asian_width=N  char_width=1   ← 应 0
    ❤       U+2764  east_asian_width=N  char_width=1
    ❤️              = ❤(1) + VS16(1) = 累加 2            ← 同一图形 ❤ 算 1、❤️ 算 2, 不一致
    👨‍👩‍👧          = 2+1+2+1+2 = 累加 8                  ← 真实终端渲染 2 列, buffer 预留 8 列
    ```
  - 取证（Buffer 渲染 `cafe\u0301XYZ`）：逐 cell 为 `['c','a','f','e','́','X','Y','Z']`——**组合重音被当作独立可见字形占第 4 列**，XYZ 被整体右移一位。真实终端会把组合符叠到 `e` 上，于是 `é` 后多出一个幽灵空格，后续整行与 buffer 的列号错位。
  - ZWJ 家庭 emoji `👨‍👩‍👧`：buffer 预留 8 列，终端只画 2 列，中间留下 **6 列幻影空白**；任何含 ZWJ 的 emoji（肤色组合、情侣、家庭、旗+修饰）都会 4 倍超占。
- 为什么伤害阅读体验：用户消息、commit message、PR 描述里 emoji 越来越常见（🎉 ✅ ⚠ 🚀），accented 文本（café、naïve、Müller）在国际化内容里是常态。这些字符一旦出现，要么把后续文本整体错位（组合符），要么在屏幕上留下大段说不清的空白（ZWJ），要么光标定位偏移导致编辑/选中错位。光标列计算（`Input.draw` widgets.py:454-457 也用 `char_width`）同步受害——在含 emoji 的行里移动光标会「跳不准」。
- 具体改进建议：
  - `char_width`（markup.py:18-22）新增零宽判定：`if unicodedata.category(ch).startswith("M"): return 0`（所有 Mark 组合符）；对 `Cf` 类的 ZWJ(U+200D)、VS(U+FE00-FE0F)、BOM 等显式 `return 0`。
  - `Buffer.put`（buffer.py:32-47）对零宽字符做**叠到前一格**而非丢弃：把组合符并进 `self.grid[y][cx-1]` 的字形（或至少不前进列）。
  - 对 emoji 序列做 grapheme cluster 聚合（`regex` 或手写 ZWJ/VS 合并），按整体 2 宽计，避免 8 列幻影。

---

### [P1] 工具结果截断只留头部 + 英文 "more lines" 提示 + 3 行/150 字符双重上限把计数自己吞掉——coding agent 的工具输出信息保真极差

- 证据：
  - `prism/shell.py:225` `tool_execution_end` 调 `_fmt_result(str(result))`；`prism/shell.py:455-467` `_fmt_result(result, max_lines=3, max_chars=150)`：先 `lines[:3]` + 追加 `  ... ({n} more lines)`，再 `if len(text) > max_chars: text = text[:max_chars] + "..."`。
  - 取证（20 行结果）：只展示前 3 行，尾部 17 行用英文 `  ... (17 more lines)` 一刀切——**整条 UI 是中文，唯独这句截断提示是英文**。
  - 取证（4 行 × 60 字符，触发双重截断）：
    ```
    FMT(double-trunc): 'xxxx...(60)\nxxxx...(60)\nxxxx...(30)...'
    → "(1 more lines)" 计数被 150 字符二次截断整个吞掉, 只剩裸 "..."
    ```
    即 `max_lines` 刚加了计数提示，`max_chars` 紧接着把提示自己截没——用户既看不到尾部，**连「被隐藏了多少」都不知道**。
  - 取证（单行 92 字符代码）：虽未被切（<150），但 `max_chars=150` 按 **Python codepoint 数计**，对 CJK（每字宽 2）意味着 150 codepoint = 300 显示列；对纯英文则 150 字符≈一行半长代码——一行稍长的 `def ... return ... # 注释` 就会被切尾，丢失返回值/注释。
- 为什么伤害阅读体验：coding agent 的工具输出（`Read` 文件、`bash` 跑测试、`grep` 搜结果）动辄几十上百行。现在一律只留头 3 行 + 150 字符，**而错误、断言失败、栈底总结、测试汇总恰恰都在尾部**——用户最想看的部分被精确地砍掉。加上计数提示本身也会被二次截断吞没，用户面对一个突兀的 `...` 完全无从判断「后面还有 3 行还是 300 行」，无法决定要不要展开/重跑。
- 具体改进建议：
  - `_fmt_result`（shell.py:455）：改为**头部 N 行 + 尾部 M 行**（head+tail），中间插一行 `[dim]…省略 K 行 (按 ↑ 展开 / 输入 /expand)[/dim]`，保留首尾两端的关键信息（命令头部 + 结果/错误尾部）。
  - 截断计数提示中文化、且放在**二次截断之后**确保不被吞：`… 还有 {n} 行`。
  - `max_chars` 按**显示宽度**（`sum(char_width)`）而非 codepoint 数计；或干脆只按行截断、行内超长走 `wrap`，不要字符级硬切。
  - 提供展开交互（点工具块 / 快捷键展开全文），别让 150 字符成为硬天花板。

---

### [P1] 文案中英混杂无规则——同一「agent 状态」用两种语言，中文 UI 里散落 `Refracting`/`error:`/`steer`/`Ctrl+C again to quit`/`more lines`

- 证据（直接摘录源码原文）：
  - `prism/shell.py:155` 折射动画：`[bold cyan]◇ Refracting[/bold cyan]`——**英文**；而同为「agent 中断/结束」语境的 `shell.py:47` 是 `[yellow]⏹ 已中断[/yellow]`——**中文**。一个 app 的忙碌态两种语言。
  - `prism/shell.py:239` `[red bold]✗ error:[/red bold]`、`shell.py:244` `⚠ {phase}/{point}: {error} (已降级)`——`error` 英文，`(已降级)` 中文，**同一行两种语言**。
  - `prism/shell.py:346` `⚡ steer → {name}`——英文 `steer`；`shell.py:348` `@{name}: 命名空间没有这个 agent`——中文 + 英文 `agent`。
  - `prism/tui/app.py:231` `[dim](Ctrl+C again to quit)[/dim]`——**整句英文**，落在否则全中文的提示流里。
  - `prism/shell.py:461` 截断提示 `  ... ({n} more lines)`——英文。
  - 对照：`widgets.py:105/115/123/127` 阶段标签「行动/观察/思考/直觉/反思」全是中文，`widgets.py:270` `无匹配命令`、`shell.py:322` `未知指令`、`shell.py:338` `@ 了就得说事`、`shell.py:365` `已回退`/`无改动可回退` 也全是中文。→ **基调是中文，却随时插英文术语，无规律**。
  - 大小写也不统一：`Refracting` 首字母大写，`error:`/`steer`/`more lines` 全小写，`agent` 小写。
- 为什么伤害阅读体验：文案语言不一致让产品显得「拼凑」——用户每碰到一个英文词都要停顿一下「这是术语还是没翻译」。最伤的是 **`◇ Refracting` 与 `⏹ 已中断` 同属 agent 运行态**，前者英文后者中文，用户无法把它们归为同一组语义。`Ctrl+C again to quit` 整句英文出现在中文提示里更是突兀——这是给用户看的关键操作引导，不是代码标识符，没有理由不本地化。
- 具体改进建议（建一张文案表统一为中文，专有名词/命令名保留原文）：
  | 现状 | 统一为 |
  |---|---|
  | `◇ Refracting` | `◇ 折射中` （与 `已中断` 同语系） |
  | `✗ error:` | `✗ 错误：` |
  | `(已降级)` | `（已降级）`（顺手修全角括号，见下条） |
  | `⚡ steer → {name}` | `⚡ 转向 → {name}` |
  | `(Ctrl+C again to quit)` | `（再按一次 Ctrl+C 退出）` |
  | `... ({n} more lines)` | `…（还有 {n} 行）` |
  | `命名空间没有这个 agent` | `命名空间没有这个 agent`（agent 作为既有术语可保留，但全文 agent/Agent 大小写统一） |
  - 建一份 `prism/tui/strings.py` 集中所有用户可见文案，杜绝散落硬编码。

---

### [P2] 标点全/半角混用，且对中文内容用半角括号——`未知指令。可用:`（全角句号+半角冒号）、`(已降级)`/`(重启生效)`/`(最近在上):` 半角括号包中文

- 证据（原文）：
  - `shell.py:322` `/{name} — 未知指令。可用: {' '.join(avail)}` —— **全角 `。` + 半角 `:`**，一句之内两套标点体系。
  - `shell.py:244` `⚠ ... (已降级)` —— 半角 `()` 包中文。
  - `shell.py:365` `已回退 {n}(重启生效)` —— 半角 `()` 紧贴中文，无空格。
  - `shell.py:372` `改动备份栈(最近在上):` —— 半角 `()` + 半角 `:` 收尾中文。
  - `shell.py:234` / `widgets.py:132` `(based_on ...)` —— 英文内容半角括号（合理），但它出现在中文行尾，与中文标点体系碰撞。
  - 对照：`shell.py:47` `⏹ 已中断` 无标点；阶段标签用 `▸` `·`（全角符号，一致）。
- 为什么伤害阅读体验：中文排版里，中文内容后接标点应用全角（`。：（）`），半角标点会让行文显得「漏风」、字距不均。`未知指令。可用:` 这种「全角句号紧跟半角冒号」是最典型的半成品本地化痕迹，读起来像机器翻译。半角 `()` 紧贴中文（`(已降级)`）还破坏了视觉上的字间呼吸。
- 具体改进建议：
  - 对中文上下文统一全角标点：`未知指令。可用：`、`（已降级）`、`已回退 {n}（重启生效）`、`改动备份栈（最近在上）：`。
  - 纯英文/代码上下文（`based_on`、`error: TypeError`）保留半角。
  - 规则：标点跟随其**前一个字符的语种**——前是中文则全角，前是 ASCII 则半角。

---

### [P2] 没有任何时间戳 / 工具耗时 / 消息序号——多轮对话零时序信息，回滚历史无法判断「哪步花了多久 / 谁先谁后」

- 证据：
  - `prism/tui/widgets.py:103-109` `tool_start` 返回的 block dict 字段仅 `{'name', 'bg', 'body'}`——**无 `started_at` / `duration`**。取证回读：`tool_start 返回的 block dict 字段: ['bg', 'body']`。
  - `RichLog.entries`（widgets.py:64）只存 `[("line", markup)] / [("block", dict)]`，**无任何时间字段**；全仓 grep `RichLog` 源码无 `time`/`stamp`/`elapsed` 写入路径。
  - `prism/shell.py:218-231` `tool_execution_start`/`tool_execution_end` 之间**没有计时**，结束时也不回填耗时。
  - 用户消息（`log.user`）、流式回复、认知阶段都无时间标记。
- 为什么伤害阅读体验：coding agent 一轮里可能跑十几个工具、调几次子 agent、穿插反思。用户回滚历史想复盘「哪一步慢」「这个工具卡了多久」「模型想了多久才动」——一无所有。调试性能问题、定位卡顿环节完全失去依据。同类产品至少在工具块上挂一个 `· 1.2s`。
- 具体改进建议：
  - `tool_start`（widgets.py:103）block 记 `t0=time.time()`；`tool_end`（widgets.py:111）回填 `dt = time.time()-t0`，在 head 后追加 `[dim]· {dt:.1f}s[/dim]`。
  - 长耗时（>2s）高亮为 `warning` 色，让慢调用一眼可见。
  - 可选：消息块右下角加相对时间戳 `· 14:32`。

---

### [P2] 空态文案缺失——输入框 placeholder 为空字符串，开屏除了 banner 没有任何「我能做什么 / 怎么开始」的引导

- 证据：
  - `prism/shell.py:37` `Input(id="dock", placeholder="")` —— **placeholder 是空串**。
  - `prism/tui/widgets.py:445-447` `Input.draw`：`if not self.value and self.placeholder and r == 0:` 才画 placeholder。placeholder 为空 → **输入框永远空着，无任何提示**。
  - 启动后用户看到的是：7 行彩色 banner（轮1/轮3 已批）+ 一个空的粉色边框框，**没有「问我任何问题」「/ 看命令」「@ 呼叫 agent」的引导**。Header 右侧虽有 `/ commands · @ agents · python`（widgets.py:16），但那是一行 dim 小字，且在 banner 抢占首屏时极易被忽略。
- 为什么伤害阅读体验：空态是产品的「第二次握手」（第一次是 banner）。一个空输入框 + 无引导，新用户不知道「能输入什么、斜杠命令有哪些、Python 表达式可直接跑」。竞品（claude-code / pi）开屏都有 placeholder 引导或欢迎语。
- 具体改进建议：
  - `shell.py:37` 设 `placeholder="问我任何问题 · / 看命令 · @ 呼叫 agent"`。
  - 或在 transcript banner 之后写一行 onboarding：`[dim]试试：帮我重构这个函数 / /help / @Prism 写个脚本[/dim]`。

---

### [P2] 认知块 `(based_on …)` 元信息后缀内联拼接，折行时被从中间劈开（`(ba` / `sed_on …`），且无避让

- 证据：
  - `prism/tui/widgets.py:130-133` `cognitive()` 把 `based_on` 拼成 `  [dim](based_on {safe})[/dim]` **直接追加在内容行尾**，与正文共享同一个 `_LineUnit`，走同一个 `wrap_segments`。
  - 取证（40×24 渲染）：
    ```
     9│ 直觉 ▸ CursorEditor 应持有 value/pos
    10│ 和 _cursor_rc，Input 退化为纯绘制  (ba      ← "(based_on" 被切
    11│ sed_on widgets.py:320)
    ```
    `(` 和 `based_on` 分家，`sed_on widgets.py:320)` 孤零零占一行；20×20 下 `(based_on 重构方案` / `)` 更是把括号拆到两行。
- 为什么伤害阅读体验：`based_on` 是「这条直觉/反思的依据」的元信息，本应是一个不可分割的小标签。现在它和正文一起被按宽度硬折，括号被劈开，既难看又破坏了「这是一条元信息」的整体感。叠加 P1#3（无词边界）的硬切，效果更糟。
- 具体改进建议：
  - 把 `based_on` 元信息**单独成行**或做成不可断的 inline 标签（`wrap_segments` 支持「原子段」：一段标记为 `no_break` 的文本要么整段放下、要么整体换行）。
  - 或降级为块的第二行（block body 多一行 `[dim]依据: {safe}[/dim]`），与正文分行，彻底避免被切。

---

### [P2] 滚动以「块(unit)」为粒度，scroll_up/down(3) 实际跳 10~11 行——混排下跳变不可控，回滚阅读一顿一顿

- 证据：
  - `prism/tui/widgets.py:171-181` `scroll_up(n=3)`/`scroll_down(n=3)` 以 **unit** 为单位跳，而 unit 是 `_LineUnit`(height=1) 与 `_BlockUnit`(height=2+padding) 的混合。
  - 取证（8 个 user 块 + 8 个 tool 块的 transcript）：`各 unit 高度: [3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3, 4]`，`scroll_up(3)` 前 3 个 unit = **跳 10 行**，后 3 个 unit = **跳 11 行**——同样按一次键，跳的行数不同。
  - 在 24 行屏上，一次「向上 3 unit」直接吃掉近半屏，用户想精确定位某行时永远对不齐；想连续翻阅时节奏一顿一顿。
- 为什么伤害阅读体验：（轮2 已批「滚动无 unread 指示」，此处是**滚动粒度**的新证据。）阅读长历史时，用户的预期是「按一下走几行」（line/半屏粒度），而不是「按一下跳过一整个工具块」。块粒度滚动让回滚变成「跳跃式寻路」，无法平滑扫读。
- 具体改进建议：
  - 把 `scroll_up/down`（widgets.py:171-177）改为**行粒度**：在展平的「可视行」序列上滚动 N 行（默认 1~3 行），而非 unit。
  - 或保留 unit 粒度但把默认步长降到 1 unit，并让 PageUp/PageDown（已有，app.py:244-247）走半屏——细分「微调 vs 翻页」两档。

---

## 本轮取证脚本（附录）

取证脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_text_forensics.py`。完整输出：`C:/Users/cty18/AppData/Local/Temp/prism_text_evidence.txt`。

要点：
- 直接调 `char_width`（markup.py:18）逐 codepoint 打印 `east_asian_width` 与计算宽度，覆盖 `\t`、组合重音 U+0301、VS16 U+FE0F、ZWJ U+200D、❤/❤️、🎉、👨‍👩‍👧 家庭序列、🇨🇳 国旗。
- `Buffer.write` 渲染 `a\tb\tc` 与 `clean:\n\t\trm -f *.o`，逐 cell dump 证明 tab 蒸发为幽灵空格、缩进被压平。
- `Buffer.write` 渲染 `cafe\u0301XYZ`，逐 cell dump 证明组合重音占独立列、后续文本右移。
- `wrap_segments` 对英文长句按 width=20 断行，证明单词从中间被切（`configuratio`+`n`）。
- `wrap_segments` 对中文长句按 width=20/14/8 断行，证明 CJK 折行正确（无半字，作为对照组）。
- `wrap_segments` 对跨行 markup（`[bold cyan]…[/bold cyan]`）按 width=14 断行，证明**标签不泄漏**（parse 在前，OK）——用作正向基线。
- `_fmt_result` 对 20 行 / 4 行×60 字符 / 单行 92 字符代码分别截断，证明只留头部、英文 `more lines`、双重截断吞掉计数。
- `_fmt_args` 对长路径 + 长内容截断，证明 60 字符对路径过短、按 codepoint 计。
- `PrismApp()._build()` + 手工 `log.user/tool_start/tool_end/thinking/cognitive` + `#current.update`，在 80×24/40×24/20×20 下 `_render_frame`+`render_plain` dump 逐行，证明代码围栏原样、单词/标识符被切、`(based_on …)` 被劈。
- 单独验证：Makefile tab 缩进渲染、双重截断吞计数（脚本外补跑确认）。

核心取证模式（tab 蒸发 + 双重截断吞计数）：
```python
# tab 被静默丢弃, 缩进压平
b = Buffer(30, 2)
b.write(0, 0, "clean:", Style.empty())
b.write(0, 1, "\t\trm -f *.o", Style.empty())
# row1 → '  rm -f *.o'  (两个 tab 只剩 2 格幽灵空格)

# _fmt_result 双重上限: max_lines 加了计数, max_chars 又把计数截没
_fmt_result("\n".join(["x"*60 for _ in range(4)]))
# → 'xxx...(60)\nxxx...(60)\nxxx...(30)...'   "(1 more lines)" 被吞
```
