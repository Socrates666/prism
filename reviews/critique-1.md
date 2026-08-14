# 批判轮1：布局与信息架构（评审人：终端 UI 布局/IA 评审专家）

评审视角：屏幕空间分配、区域划分（输入区/输出区/状态区/边框/滚动区）、视觉层级（什么该突出什么该弱化）、信息组织顺序、主次关系、空间浪费或拥挤、不同终端尺寸下的布局合理性。

方法：通读 `prism/tui/*` 与 `prism/shell.py`，写无头渲染取证脚本（附录 A），实例化 `PrismApp` 经 `_build()`（不跑 `on_mount`，不连网/不建 agent），手工喂入多轮对话/thinking/tool/流式/超长内容，在 80×24 / 120×40 / 200×50 / 60×20 / 80×16 等尺寸下把 `Buffer` 逐行 dump 成带行列标尺的可视化文本。所有渲染输出均为真实取证，非脑补。

共 9 条问题。分布：**P0 ×1，P1 ×4，P2 ×4**。

---

## 发现的问题

### [P0] 流式回复区 `#current` 高度无上限，任何长回复都会把输入框/历史挤出屏幕

- 证据：
  - `prism/tui/widgets.py:220-223` `Static.measure()` 返回**整段内容**换行后的行数，无任何上限：
    ```python
    def measure(self, width: int) -> int:
        iw = max(1, width - 2)
        rows = wrap_segments(parse_markup(self.content), iw) or [[]]
        return max(1, len(rows))   # ← 没有 max 上限
    ```
  - `prism/tui/widget.py:64-71` `layout()` 对 `auto` widget 直接采用其 `measure()`，并入 `fixed_sum`，**只给 `fr`（transcript）做 `max(0, ...)` 兜底，从不限制 auto 的上限**：
    ```python
    elif kind == "auto":
        m = w_.measure(width)
        hgt = max(cs.min_height, m)   # ← 只看 min，不看 max
        needs.append(hgt); fixed_sum += hgt
    ```
  - `prism/shell.py:16-22` CSS 里 `#current { height: auto; min-height: 1; ... }` 也没有 max-height 概念，且 css 根本不支持 max-height。
  - `prism/shell.py:202-205` `message_update` 每个 delta 都把**整段累积文本** `current.update("".join(current_buf))` 塞进 `#current`，直到 `message_end` 才 flush。也就是说流式期间 `#current` 单调膨胀。
  - **渲染取证（SCENARIO C，喂入 40 段长文本到 #current，80×24）的 region 分配**：
    ```
    rows  0- 0 (h= 1)  Header   #header       x=0 w=80
    rows  1- 1 (h= 0)  RichLog  #transcript   x=0 w=80      ← 历史区被压成 0 行
    rows  1-54 (h=54)  Static   #current      x=0 w=80      ← current 撑到 54 行
    rows 55-55 (h= 1)  Static   #status       x=0 w=80
    rows 56-58 (h= 3)  Input    #dock         x=0 w=80      ← 输入框被推到第 56 行(屏外)
    rows 59-60 (h= 2)  Footer   #footer       x=0 w=80      ← 页脚屏外
    SUM height = 61  (screen rows = 24, overflow = 37)
    ```
    实际渲染 0-23 行全部被 `#current` 的流式文本铺满，**transcript、dock、footer 全部消失**。

- 为什么伤害核心体验：这是一个 coding agent，长回复（几十行代码 + 解释）是**最常见**的场景，不是边界情况。一旦回复超过约 16 个换行行，用户在**整个流式生成期间**看不到历史、看不到自己正在输入的内容、也看不清输入框边框——而恰恰这段时间用户最想盯着输出读。这是把核心交互（看模型流式回答）直接打碎。
- 具体改进建议（精确到函数/常量）：
  1. 在 `prism/tui/css.py` 的 `ComputedStyle` 增加 `max_height: int = 0`，`parse_css` 解析 `max-height:` 声明（参考已有 `min-height` 写法 css.py:83-84）。
  2. 在 `prism/tui/widget.py:64-71` 的 `auto` 分支加 clamp：`hgt = max(cs.min_height, min(m, cs.max_height or m))`。
  3. 给 `#current` 设上限，如 `#current { height: auto; min-height: 1; max-height: 6; }`。
  4. 让 `Static.draw`（widgets.py:225-233）在内容超过 `h` 时**只画末尾 h 行**（贴底滚动，类似 RichLog 的 follow 语义），否则裁剪后只显示开头反而看不到最新流式内容。

---

### [P1] 主输出区 `#current`（流式回答）被画成「思考」样式——把最重要的内容视觉降级

- 证据：
  - `prism/tui/widgets.py:228` `Static.draw` 写死用 `thinking_text` 样式：
    ```python
    text_style = self.app.style("thinking_text")   # dim #808080 + italic
    ```
  - `prism/tui/app.py:38` `"thinking_text": Style(fg=_h("808080"), italic=True)` —— 灰色 + 斜体。
  - `#current` 在语义上是**正在生成的助手主回答**（shell.py:177-178 `update_current` / 202-205 message_update 写入），不是思考。但渲染取证里它和真正的思考块（`思考 ▸ ...`）视觉权重完全一样，甚至更弱。
  - 渲染取证（SCENARIO B，busy + 流式，80×24）第 16-17 行就是这段被降级的主回答，夹在历史（上）和 `◇ Refracting...`（下）之间，又灰又斜：
    ```
    16│  好的, 我会先抽出 CursorEditor 类, 把 value/pos/_cursor_rc/_line_starts/_move_l
    17│  ine 全部搬过去, Input 只保留边框绘制和光标反相。ctrl+u 和 ctrl+k 也
    18│  ◇ Refracting...
    ```
- 为什么伤害美感/体验：视觉层级完全反了。模型**正在说的正话**应该是全屏最醒目的内容，结果被画得比历史记录还灰、还斜体，像旁白/草稿。用户读流式输出时眼睛要额外费力，且无法一眼区分「这是结论」还是「这是中间思考」。
- 具体改进建议：
  - `Static` 不应硬编码样式 token。改成读 CSS `color`（css.py 已支持 `color:` 声明，widget 里却没用）：`text_style = self.app.style(cs.color_token) if cs.color_token else self.app.style("text")`。
  - `PrismApp.CSS` 给 `#current { color: $text; }`（正常文本色，非斜体）；若想区分「流式中」，可用一个稍暗但仍正色的 `streaming` token，生成完毕转正色，而不是直接套 thinking。

---

### [P1] CSS 声明的 `border` 是死代码——transcript 没有任何可见边界，区域划分含糊

- 证据：
  - `prism/shell.py:18` `#transcript { height: 1fr; border: round $accent; padding: 0 1; }` 明明声明了圆角边框。
  - 但 `prism/tui/app.py:287-304` `_render_frame` 拿到 `ComputedStyle` 后**只调用 `w.draw()`，从不读取 `cs.border` / `cs.border_token` 去画框**：
    ```python
    regions = layout(self._widgets, styles, rows, cols)
    for w, (x, y, w_, h) in zip(self._widgets, regions):
        ...
        w.draw(buf, x, y, w_, h)   # ← 没有根据 cs.border 先 buf.box()
    ```
  - 全仓 `buf.box(` 实际绘制**只有一处**：`prism/tui/widgets.py:433`（Input 自己画的 dock 边框）。`ComputedStyle.border` 只在 `css.py` 里被 set/merge，渲染路径从不消费它（已 grep 确认）。
  - 渲染取证（SCENARIO A，80×24）可以清楚看到 transcript（1-16 行）**上下都没有边框线**，最后一行内容（15 行）和下方空白（16-18 行）之间毫无分隔，输入框边框（19-21）像悬在虚空里：
    ```
    14│  反思 ▸ ctrl+u/ctrl+k 是行内删除, 依赖 _line_starts, 确认 CursorEditor 暴露该方
    15│  法即可。  (based_on 重构方案)
    16│                                                                  ← transcript 末行, 无下边框
    17│                                                                  ← #current(空)
    18│                                                                  ← #status(空)
    19│ ╭──────────────────────────────────────────────────────────────────────────────╮
    ```
- 为什么伤害体验：`pi`/Textual 风格里 transcript 是一个有框的「主面板」，用户靠边框感知「这块是可滚动的历史区」。这里声明了边框却不画，导致（a）声明即谎言，后来人会被 CSS 误导；（b）transcript 下沿和两个永久空白行（见下条）视觉粘连，用户分不清「滚到底了」还是「这只是空白」。
- 具体改进建议（二选一，推荐前者）：
  1. 在 `_render_frame`（app.py:291-296）`w.draw` 之前判断 `cs.border`：先 `buf.box(x,y,w,h, border_style=self.style(cs.border_token))`，并把传给 `w.draw` 的内部区域收进一格（`x+1,y+1,w-2,h-2`）。这样 CSS 的 border 才真正生效。
  2. 若确实想要 pi 那种无边框纯色带风格，就把 `#transcript`/`#dock` 的 `border:` 声明从 CSS 删掉，别留死配置骗人。

---

### [P1] 闲置时 transcript 与输入框之间**永久浪费两整行空白**（`#status` + `#current` 各占一行却为空）

- 证据：
  - `prism/shell.py:20` `#status { height: 1; ... }` —— 固定 1 行，**始终占位**。
  - `prism/shell.py:19` `#current { height: auto; min-height: 1; ... }` —— 即使内容为空，`Static.measure`（widgets.py:220-223）对空串也返回 `max(1,1)=1`，所以**空也占 1 行**。
  - 闲置态 `#status` 内容为空（`_stop_status` 调 `status.update("")`，shell.py:173），`#current` 也为空（非流式）。渲染取证（SCENARIO A，80×24）第 17、18 行就是这两行纯空白。
  - 量化：80×24 下 transcript 只有 16 行，这两行空白 = 内容区的 **12.5%** 被白送。60×20 下 transcript 仅 12 行，2 行空白 = **16.7%**（见 SCENARIO E region：transcript rows 1-12 共 12 行，current/status 各吃 1 行空）。
    ```
    region layout @ 60x20:
      rows  1-12 (h=12)  RichLog  #transcript   ← 只有 12 行内容
      rows 13-13 (h= 1)  Static   #current       ← 空
      rows 14-14 (h= 1)  Static   #status        ← 空
      rows 15-17 (h= 3)  Input    #dock
    ```
- 为什么伤害体验：终端行是稀缺资源，尤其在大家默认 80×24、或分屏开侧边栏把宽度/高度压更小的时候。闲置（用户读历史、思考下一步）是占比最高的状态，此刻白白扣掉 ~1/7 的内容高度，纯属「为偶尔出现的 refracting 动画留位」的成本错配。
- 具体改进建议：
  - 让 `#status` **按需出现**：默认 `height: 0`，仅 `_agent_busy=True` 时通过 overlay 或动态改 `min-height` 浮现一行（overlay 机制 app.py:306 已有，直接复用）。
  - `#current` 空时也应收成 0：`Static.measure` 当 `not self.content.strip()` 时返回 0（widgets.py:220），配合 `min-height: 0`。这样闲置态 transcript 直接顶到 dock 上方，多出 2 行。

---

### [P1] 启动 ASCII banner 占去 transcript 近半可视高度，把「真信息」挤下首屏

- 证据：
  - `prism/shell.py:282-293` `on_mount` 往 transcript 写 1 空行 + 5 行 `█████` 字母画 + 1 空行 = **7 行**，且**每次启动都写**（无「仅首次」判断）。
  - 渲染取证（SCENARIO D，80×24，transcript=16 行）：banner 占第 2-7 行（5 行画 + 前导空行），其后第 8-16 行全空，banner 实占 6/16 ≈ **37.5%** 的可视 transcript。
    ```
    01│
    02│  █████ ████  █████ ████  █   █
    03│  █   █ █   █   █   █     ██ ██
    04│  █████ ████    █   ███   █ █ █
    05│  █     █  █    █      █  █   █
    06│  █     █   █ █████ ████  █   █
    07│
    08│ ... (8-16 全空)
    ```
  - 60×20 时 transcript 仅 12 行，banner 占比升到 ~50%。
- 为什么伤害体验：banner 是一次性的自我标榜，却永久驻留在滚动历史顶部、并霸占首屏。用户启动后第一眼看到的不是「我能做什么」而是 5 行彩色方块，首屏信息密度极低。coding agent 用户开屏想看的是 cwd/model/可用命令，不是 logo。
- 具体改进建议：
  - 缩成 1 行（如 `◆ Prism · glm-4.6 · /help`），或只在 `rows >= 30` 时才画完整 5 行 banner，小屏退化成单行标题。
  - 或写到 Header（widgets.py:9-24 已有标题位 `◆ Prism`），别占用宝贵的滚动历史行。

---

### [P2] 宽终端（200 列）内容被拉到 ~198 列宽，无最大可读宽度，长行无法扫读

- 证据：
  - `prism/tui/widgets.py:148-149` `RichLog._ensure_units`：`body_iw = max(1, iw - 2)`，`iw` 就是整个 transcript 宽度，没有任何「阅读最佳宽度」上限。
  - 渲染取证（SCENARIO A3，200×50）正文行换行到 ~198 列，例如第 4 行单行塞了 100+ 中文字符。在真终端里这种行长极难扫视，眼球要大幅水平移动。
  - 普通文本（`_LineUnit`，widgets.py:31-32）左缩进仅 1 格，右侧无对称留白，宽屏下文字贴着左右边缘，视觉上「散」。
- 为什么伤害美感：终端不是网页，没有 max-width 约束时 200+ 列的纯文本行阅读体验断崖式下降。同类产品（pi/claude-code）在宽屏都会做内容居中或限宽。
- 具体改进建议：
  - 在 `RichLog._ensure_units` 引入 `body_iw = min(iw - 2, MAX_READ_WIDTH)`，`MAX_READ_WIDTH` 取 100~110（约对应中文 50 字）。
  - 多余宽度作为左右对称留白（`_LineUnit.draw` / `_BlockUnit.draw` 的起始 x 居中计算），而非只左缩 1 格。

---

### [P2] 「思考」内容是裸文本行，而工具/用户消息是全宽色块——`thinking_bg` 定义了却没用，视觉分组不一致

- 证据：
  - `prism/tui/widgets.py:120-123` `thinking()` 走的是 `self.write(...)` → 生成 `_LineUnit`（无背景）：
    ```python
    def thinking(self, text: str) -> None:
        for sub in (text or "").split("\n"):
            self.write(f"[blue]思考[/blue] [dim italic]▸ {sub}[/dim italic]" ...)
    ```
  - 而 `user()`/`tool_start()`/`tool_end()` 生成 `_BlockUnit`（widgets.py:35-46），`_BlockUnit.draw` 调 `buf.fill_bg(...)` 铺全宽背景色带。
  - `prism/tui/app.py:41` 主题里明明定义了 `"thinking_bg": _h("282832")` 和 `"cognitive_bg"`，但全仓 grep 显示 `thinking_bg` **只在 app.py 定义，再无任何引用**（dead）。
  - 后果：渲染取证里「思考 ▸ …」（SCENARIO A 第 1-3 行）和普通正文一样是灰字裸行，没有像「✓ 观察」「用户消息」那样的背景色带包裹，导致思考块在密集对话里**边界模糊、无法一眼框选**。
- 为什么伤害美感：信息架构上「思考/直觉/反思」是一个语义阶段，理应和「行动/观察」享有同级的视觉分组（色块）。现在它降级成散行文本，用户回滚历史时难以快速定位「这段是模型的推理」。
- 具体改进建议：
  - 把 `thinking()` 改成产出 `_BlockUnit`（带 `thinking_bg`），与 `cognitive()` 统一成块状阶段标签。参考 `tool_start`（widgets.py:103-109）的 block 构造方式。
  - 顺带让 `cognitive_bg`（同样 dead）也真正用上。

---

### [P2] Footer 占两行，第一行只放了一个 cwd，近一整行浪费

- 证据：
  - `prism/tui/widgets.py:474-475` `Footer.measure` 固定返回 2：
    ```python
    def measure(self, width: int) -> int:
        return 2
    ```
  - `prism/tui/widgets.py:477-490` `draw`：第 0 行只写左上角 cwd（dim），其余全空；第 1 行才右对齐写 `model · thinking · busy`。
  - 渲染取证（SCENARIO A，80×24）第 22 行仅 ` prism-tui-review`，右边 ~60 列空白；第 23 行才是状态信息。
    ```
    22│  prism-tui-review
    23│                                                                  · thinking off
    ```
- 为什么伤害美感：footer 是「状态条」语义，本该是一行紧凑信息。拆成两行、且第一行 90% 空白，既浪费 1 行高度，又显得布局松散没设计感。
- 具体改进建议：
  - `Footer.measure` 返回 1；`draw` 单行排版：左侧 `cwd`、右侧 `model · thinking · spinner`，用空格撑开（参考 Header 的左右分栏写法 widgets.py:21-24）。

---

### [P2] 命令补全浮层宽度直接铺满整屏（`cols-2`），对短命令名严重过宽

- 证据：
  - `prism/shell.py:99-101`：
    ```python
    h = min(len(cmds), 8)
    y = max(0, self._rows - 6 - h)
    sl = SelectList([{"value": c} for c in cmds])
    self._cmd_overlay = self.show_overlay(sl, 1, y, max(1, self._cols - 2), h)   # ← 宽=cols-2
    ```
  - 命令名都是 `/model`、`/thinking`、`/revert` 这种 ≤10 字符的短串，浮层却占满整行宽。200 列屏上会出现一条近 200 宽的浮层里只左侧塞了几个短词，右侧大片留白。
- 为什么伤害美感：浮层尺寸应贴合内容。过宽的补全面板在视觉上像「弹了个全屏窗口」，喧宾夺主，和「轻量补全提示」的心智不符。
- 具体改进建议：
  - `shell.py:101` 宽度加 cap：`w = min(self._cols - 2, max(20, longest_cmd_len + 12))`，让浮层宽度跟随最长候选项。

---

## 本轮渲染取证脚本（附录）

取证脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_render_forensics.py`。要点：

- `PrismApp()._build()` 装配（compose + CSS parse + mount），**不调 `on_mount`**（避免连网/建 agent/写 banner）。
- `seed_conversation()` 手工调用 `log.user/thinking/tool_start/tool_end/write/cognitive` 喂入多轮真实内容。
- `render_at(rows, cols)` 设 `_rows/_cols`、`log._invalidate()`（强制按新宽重排）、`_render_frame` → `render_plain`，再用 `framed()` 加行列标尺 + `region_map()` 打印每个 widget 的 (x,y,w,h) 与 SUM/overflow。
- 覆盖场景：A/A2/A3（idle 多轮 @ 80×24/120×40/200×50）、B（busy+流式）、C（超长 #current 爆破）、D（启动 banner）、E/E2（窄/矮屏 60×20、80×16）。

核心取证函数片段：
```python
def render_at(app, rows, cols, caption):
    app._rows, app._cols = rows, cols
    app.query_one("#transcript")._invalidate()
    buf = app._render_frame(rows, cols)
    return framed(buf, caption) + "\n\n" + region_map(app, rows, cols)

def region_map(app, rows, cols):
    regions = layout(app._widgets, app._style_for, rows, cols)
    ...  # 打印 rows y-y (h=h) Widget #id，以及 SUM 与 overflow
```

完整渲染输出（含全部场景的逐行 dump）见同目录 `prism_render_evidence.txt`（脚本运行时自动写出）。报告内引用的片段均截取自该输出。
