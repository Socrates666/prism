# 批判轮3：视觉美学（评审人：终端 UI 视觉/色彩/排版/动效评审专家）

评审视角：色彩系统（语义色选择与一致性、ANSI 256/truecolor 降级、浅色终端适配、accent 色滥用）、对比度与可读性（灰字灰底、暗色斜体、低对比装饰）、排版节奏（字重/符号、对齐、边框字符 round/square、留白密度、行高气息）、动效（refraction 动画/spinner 的品味：频率、干扰、闪烁）、主题整体气质（2026 一流 TUI 还是 1995 BBS）。

方法：通读 `prism/tui/css.py`、`app.py`（DARK/LIGHT 全色值）、`markup.py`（`_COLOR`/`Style.sgr`）、`widgets.py`（绘制调用）、`buffer.py`（box/cell）、`shell.py`（banner 频谱/status 动画）。写无头取证脚本（附录），实例化 `PrismApp` 经 `_build()`（**不调 `on_mount`**，不连网/不建 agent），手工 `log.user/thinking/tool_start/tool_end/cognitive/write` 喂入真实多阶段内容，在 dark 与 light 两主题下各渲染 80×24，dump Buffer 的**逐 cell fg/bg/attr 矩阵**，手算 WCAG 对比率，统计 page_bg 覆盖率与 token 死活。所有色值/对比率/矩阵均出自真实渲染，非脑补。

> 不重复轮1（布局/IA）、轮2（键盘）。轮1 提过「输出区误用 thinking_text 灰斜体」「banner 占首屏」「thinking_bg dead」「CSS border 死代码」「footer 两行浪费」——本报告只在**色彩学**层面给出新证据（如灰阶 token 撞色、banner 的饱和度证据、footer spinner 压暗），凡与布局/IA/按键相关者不重复。

共 **10 条**问题。分布：**P0 ×2，P1 ×5，P2 ×3**。

色值速查（取证实测，WCAG 对比率均以「设计意图背景」为参照：dark=#18181e，light=#ffffff）：

| token / markup | dark 值 | dark 对比 | light 值 | light 对比 |
|---|---|---|---|---|
| text | #d4d4d4 | 11.92:1 | #1f2328 | 15.8:1 |
| thinking_text/muted/tool_output | #808080 | 4.47:1 | #6c6c6c | 4.80:1 |
| dim | #666666 | 3.08:1 | #767676 | 4.04:1 |
| border_muted | #505050 | **2.19:1** | #b0b0b0 | **2.17:1** |
| editor_border（输入框边框） | **#ff1493** | 4.86:1 | #d63384 | 4.07:1 |
| markup `[yellow]` | #ffff00 | 16.46:1 | #ffff00 | **1.07:1** |
| markup `[cyan]` | #00d7ff | 10.24:1 | #00d7ff | **1.73:1** |
| markup `[green]` | #b5bd68 | 8.79:1 | #b5bd68 | **2.01:1** |

---

## 发现的问题

### [P0] 浅色主题下 markup 色彩集体失效——「反思/行动/✓」等语义标签对比度低至 1.07:1，等同于隐形

- 证据：
  - `prism/tui/markup.py:26-32` 的 `_COLOR` 表**写死**，与主题系统完全脱钩：`yellow=(255,255,0)`、`cyan=(0,215,255)`、`green=(181,189,104)`、`white=(212,212,212)` 永远是这几个 RGB，不随 `app.theme` 变化。
  - 而这些 markup 色被用在**高语义密度的标签**上：`widgets.py:105`「行动」`[cyan]`、`widgets.py:123`「思考」`[blue]`、`widgets.py:129`「反思」`[yellow]`、`shell.py:365`「✓」`[green]`、`shell.py:47`「⏹ 已中断」`[yellow]`、`shell.py:346`「⚡ steer」`[yellow]`、`shell.py:244`「⚠ patch_error」`[yellow]`。
  - **取证矩阵（light 主题，80×24，第 10 行「反思」认知标签）**：
    ```
    行10: 反思 ▸ ctrl+u 依赖 _line_starts, 保留接口即可  (based_on 重构方案)
    逐 cell: [反] fg=#ffff00 bg=·   [思] fg=#ffff00 bg=·   [▸] fg=· bg=· ID ...
    「反」字 fg=(255,255,0) bg=None
    → 对比率 #ffff00 on #ffffff = 1.07:1   (WCAG AA 正文需 4.5:1，非文本需 3:1)
    ```
  - `_COLOR` 全表在浅色 page 上的对比率（取证实测）：`yellow 1.07:1`、`cyan 1.73:1`、`green 2.01:1`、`white 1.48:1`、`accent 2.07:1`——**5 个常用 markup 色全部低于 3:1**，在白底上全部不达 WCAG 非文本最低线。
- 为什么伤害核心体验：浅色主题是**已上线、且暴露给 agent 动态切换的**（`shell.py:426-440 ThemeCtl`，agent 可 `theme.set('light')`）。一旦切到 light，每一条工具调用前的「行动」标签、每一段反思、每一次回退成功的「✓」、每次中断提示——全部变成白底上的浅黄/浅青，肉眼几乎不可见。这不是边界场景，是**整条对话的主干语义着色**在浅色下瘫痪。更要命的是用户根本不知道「看不见」是因为配色，只会以为这些标签没渲染。
- 具体改进建议：
  - 把 `markup.py:26` 的 `_COLOR` 从模块级常量改成**接收当前主题**的函数：`def color_map(theme): return DARK_COLORS if theme=='dark' else LIGHT_COLORS`，在 `parse_markup`/`Style.sgr` 路径注入 `app.theme`。
  - 浅色版重映射：`yellow→#9a7326`（对白 4.5:1，复用已定义却 dead 的 `warning` light 值）、`cyan→#0b7a8c`、`green→#4f7a3a`、`white→#1f2328`。
  - 最小止损：`cognitive()`（widgets.py:125）的 `color` 别再用裸 `[yellow]`/`[cyan]` markup，改走 `app.style(token)` 主题色（如 reflect 用 `style("warning")`、intuition 用 `style("custom_label")`），让主题系统接管。

---

### [P0] 输入框边框是 DeepPink `#ff1493`——全屏最持久可见的元素被涂成霓虹品红，accent 色严重滥用

- 证据：
  - `prism/tui/app.py:45` `"editor_border": Style(fg=_h("ff1493"))   # DeepPink`，浅色版 `app.py:61` `#d63384`。
  - `prism/tui/widgets.py:432` 聚焦时输入框边框取 `editor_border`，`widgets.py:433` `buf.box(...)` 全周描边。输入框是**唯一永远在屏**的交互组件（除非退出），这条粉色框每一帧都盯着用户。
  - **取证矩阵（dark 聚焦，第 19 行输入框上沿）**：
    ```
    行19: ╭──────────────────────────────────────...───────────────────╮
    边框 '╭' @ x=0: fg=(255,20,147)   '─' 同色   '╮' 同色
    editor_border #ff1493 = RGB(255,20,147)
    饱和度(max-min) = 235/255  (近满饱和)
    对比率 on 设计page #18181e = 4.86:1（高对比 = 刺眼，而非优雅）
    ```
  - 对照同类一流 TUI 的输入/面板边框色：claude-code 用低饱和的橙灰、pi 用 muted 的边框 token、lazygit/gh-dash 一律低饱和。**没有任何一个 2026 年的成熟 TUI 把主输入框画成纯品红**。
- 为什么伤害核心体验：边框的角色是「轻轻框定区域、提供结构感」，不是「尖叫着抢焦点」。一个饱和度 235/255 的霓虹品红边框，视觉重量盖过了它框住的内容（用户正在打的字）和上方的对话（这才是主角）。它把一个「工具」的气质瞬间拉回 MSN 个人空间/GeoCities——这是主题层面的一次「品牌定义级」事故，因为它出现在开屏第一帧、且永不消失。注释自己都写「亮粉深一点」，说明作者知道它太亮，但调完仍是品红，方向就错了。
- 具体改进建议：
  - `app.py:45` 改 `editor_border` 为低饱和的语义色：聚焦态用 `accent`（dark `#8abeb7` 青灰，对 page 8.53:1，温和且有辨识度）或 `primary`（`#5f87ff`，5.38:1）；不要自造一个独立于 accent/primary 体系的第三种「粉色」。
  - 想保留「聚焦高亮」语义，就让聚焦=accent、失焦=`border_muted`，二者只差明度不差色相，符合「同一语义两个状态」的设计纪律。
  - 彻底删掉 DeepPink 这条 token——它的存在本身就是诱惑后人复用。

---

### [P1] `page_bg` 定义了却从不绘制——70.8% 的屏幕像素透传终端默认背景，主题根本不掌控自己的画布

- 证据：
  - `prism/tui/app.py:44`/`:60` 两主题都定义了 `page_bg`（dark `#18181e`、light `#ffffff`），但全仓 grep 确认它**只被定义，从不被读取**（`_render_frame` app.py:287-304 不做任何 `fill_bg(page_bg)`）。
  - Buffer 初始化（`buffer.py:28`）每个 cell 是 `Style.empty()`（bg=None），`_render_frame` 只在 `_BlockUnit.draw`（widgets.py:42-46）对 user/tool 块做 `fill_bg`。
  - **取证：80×24=1920 cell 的 bg 字段统计**：
    ```
    [dark] bg=None(透传终端默认) 1359 (70.8%)   bg=具体色 561 (29.2%)
           分布: user_bg 块 240, tool_pending/success 块 320+0, 光标 1
    [light] 同样 70.8% 透传, 29.2% 有色
    → page_bg 在主题里写着 #18181e/#ffffff, 实际被画上去的 cell 仅 29.2%
    ```
  - 也就是说 Header 行、transcript 的行间空白、`#current`/`#status` 区、输入框内部、Footer 全部是 `bg=None`——渲染在**用户终端自己的背景色**上。
- 为什么伤害美感：一个「主题」的承诺是「我控制 fg + bg 的成对关系」。所有 fg（如 `text #d4d4d4`、`thinking_text #808080`）都是按 `#18181e` 这个暗底调出来的对比率。一旦用户终端是 Solarized Light / Dracula 蓝 / 任意非 `#18181e` 的底，这些 fg 立刻在错误背景上被评价：暗主题 fg 跑到亮终端 → 灰字白底全糊；亮主题 fg（`#1f2328`）跑到暗终端 → 黑字黑底全没。主题自诩有 dark/light 两套，实际上**两套都没有底色保障**，只是「调了前景色的半套主题」。
- 具体改进建议：
  - 在 `_render_frame`（app.py:288）创建 Buffer 后立即铺底：`buf.fill_bg(0,0,cols,rows, self._bg_rgb("page_bg"))`（需让 `page_bg` token 也以 RGB 元组存取，现已如此）。
  - 或至少在 `Terminal.__enter__`（terminal.py:135）用 `\x1b]11;rgb:18/18/1e\x07` 设终端默认背景、`__exit__` 还原——但 in-app fill 更可靠（不受终端 OSC 支持度影响）。

---

### [P1] 灰阶塌缩 + 失焦边框低于 3:1——三种语义共用一个灰，未聚焦输入框边框近乎消失

- 证据：
  - `prism/tui/app.py:38-39` DARK 中 `"thinking_text": Style(fg=_h("808080"), italic=True)`、`"tool_output": Style(fg=_h("808080"))`，加上 `app.py:36` `"muted": Style(fg=_h("808080"))`——**三个语义 token 同为 `#808080`**。
  - 取证实测（dark，on page）：`muted/thinking_text/tool_output` 全部 `#808080 = 4.47:1`，`dim #666666 = 3.08:1`，`border_muted #505050 = 2.19:1`。
  - `widgets.py:432` 未聚焦输入框边框 = `border_muted`，dark `#505050` = **2.19:1**、light `#b0b0b0` = **2.17:1**——**两主题都低于 WCAG 非文本组件 3:1 最低线**。聚焦时跳到 DeepPink 4.86:1（见 P0#2），两者色相+明度同时剧变，没有「同一元素的两种状态」的连续感。
  - 后果：`tool_output`（理应可读的工具输出）和 `thinking_text`（理应弱化的旁白）视觉权重**完全相等**；用户无法靠灰度区分「这是结论性的输出」还是「这是模型的碎碎念」。
- 为什么伤害美感：好的灰阶是阶梯——`text → secondary → tertiary → quaternary → border` 至少 4~5 级，每级明度差足够大以承担不同信息层级。这里把「正文次级 / 思考 / 工具输出」三件事压成同一级 `#808080`，等于砍掉了信息层级的视觉维度；又把 `border_muted` 压到 2.19:1 让边框「在却在不在」。整套灰阶是塌的。
- 具体改进建议：
  - 拉开灰阶：`text #d4d4d4` → `secondary #a0a0a0`(约 7:1) → `tertiary/thinking #7a7a7a` → `tool_output #9a9a9a`(比 thinking 亮一档，表达「可读输出」) → `dim #5a5a5a` → `border_muted #4a4a4a` 但**仅在画了 page_bg 的前提下**用，否则 border_muted 要再提亮到 ≥3:1。
  - 未聚焦输入框边框不要用 2.19:1 的 `#505050`；要么提到 ≥3:1（dark 下约 `#5f5f5f`），要么干脆失焦时不画边框只留极淡缩进，避免「看得见却看不清」的尴尬半存在。

---

### [P1] 光标色硬编码 `(0,0,0)/(220,220,220)` 不随主题——浅色主题下光标块对比仅 1.37:1，看不见打字位置

- 证据：
  - `prism/tui/widgets.py:463`：
    ```python
    buf.put(cx_screen, cy, ch, Style(fg=(0, 0, 0), bg=(220, 220, 220)))   # 反相光标
    ```
    这是全仓**唯一**的光标实现，颜色写死，不读 `app.theme`、不读任何 token。
  - **取证**：浅色主题（page 意图 `#ffffff`）下定位光标 cell：
    ```
    光标 cell: (3, 20, 'l')   fg=(0,0,0) bg=(220,220,220)
    光标块 bg=#dcdcdc vs 白底 = 1.37:1   (WCAG 非文本需 3:1 → 形同虚设)
    深色 page #18181e 下同光标块 = 12.89:1 (可见)
    ```
- 为什么伤害美感/体验：光标是「我正在这里打字」的唯一锚点，是焦点/活性的头号指示器。深色下它是个亮块（12.89:1，OK），浅色下它变成白底上一块浅灰（1.37:1），用户根本找不到光标在哪，尤其多行编辑时（`max_lines=6`）。而且它和主题系统彻底脱节——主题切了，光标不跟着切，等于主题切换是个半成品。
- 具体改进建议：
  - `widgets.py:463` 改用主题色反相：聚焦光标 = `Style(fg=page_bg_rgb, bg=text_rgb)`（深底亮字反转、浅底暗字反转，两主题都对 page ≥7:1）。把 `page_bg`/`text` 暴露成 RGB 元组（已是）即可。
  - 或引入 `cursor` token，dark 用亮青 `#00d7ff` 块、light 用深青 `#0b7a8c` 块，与 accent 体系呼应。

---

### [P1] 启动 banner 是五原色全饱和彩虹 `█████`——开屏即 1990s ANSI art，主题气质定义级违和

- 证据（轮1 已批 banner **占空间**，此处补**色彩学**证据）：
  - `prism/shell.py:289` `_spectrum = ["#ff1744", "#ffd000", "#00ff7b", "#00d4ff", "#c850ff"]   # 鲜艳分光(满饱和)`，`shell.py:291-292` 5 行各刷一色 `█████ ████ ...`。
  - 取证实测饱和度（max-min）/255：
    ```
    #ff1744 红  232/255    #ffd000 黄 255/255    #00ff7b 绿 255/255
    #00d4ff 青 255/255     #c850ff 品红 175/255
    → 5 行各一色, 饱和度 175~255/255, 红/黄/绿/青/品红 五原色并置
    ```
  - 这五个色**全是 markup `/` hex 直填**（`markup.py:120` 走 `#rrggbb` 分支），不经过主题，dark/light 一样糊脸；且和主题自身的低饱和 Tomorrow Night 调色板（accent `#8abeb7`、text `#d4d4d4`）**完全不是同一套色彩语言**。
- 为什么伤害美感：banner 是产品的第一张脸。五原色满饱和并置是视觉上最刺、最「吵」的组合（色相轮上等距纯色互拉，眼睛要同时适应 5 种波长），这是 BBS/早期 ANSI 标题、GeoCities 闪图的语法。一个自称「类 pi 的一流 coding agent」用这套开场，等于穿花衬衫进董事会议室。更糟的是它和正文用的克制色系断裂——开屏像 rave party，正文像图书馆，用户每次启动都要经历一次气质切换。
- 具体改进建议：
  - 若要保留「棱镜分光」概念，用**单色相、多明度**的渐变（如 accent 体系内 `#8abeb7 → #5f87ff → #9575cd` 三档），或干脆单色 `◆ Prism`（Header 已有此位 `widgets.py:23`）。
  - 五色饱和度统一压到 ≤120/255，行数压到 1 行（与轮1 空间建议一致，但此处是色彩止损）。

---

### [P1] Footer busy spinner 被压暗成 `[dim]` 灰，且与「◇ Refracting」形成两套互不一致的「忙碌」视觉

- 证据（轮1 批过 footer **占两行**，此处补**动效/色彩**证据）：
  - `prism/tui/widgets.py:488-490`：忙碌时 `right = f"{frame} {right}"`，而整行 `right` 被裹进 `[dim]...[/dim]`（`widgets.py:490`）。spinner 帧 `⠋⠙⠹...`（braille）与 model/thinking 文字**一起变 dim**。
  - 取证矩阵（dark busy，第 23 行 footer）：
    ```
    行23: '                                       ⠏ glm-4.6 · thinking off'
    spinner '⠏' @ x=55: fg=None dim=True   ← 唯一动效元素被 dim 压暗, 且 fg=None(终端默认前景)
    model 'glm' @ x=57: fg=None dim=True
    dim #666666 on page = 3.08:1
    ```
  - 同一「agent 工作中」语义，另一处在 `shell.py:155` 用 `[bold cyan]◇ Refracting[/bold cyan]`（cyan `#00d7ff` on page = **10.24:1**，粗体）。→ 一边是 10.24:1 粗体青、一边是 3.08:1 dim 灰，**同一状态两种视觉权重，差 3 倍对比 + 两种色相**。
  - spinner 频率：`int(time.time()*8) % 10`（widgets.py:488）= 8 fps，主循环 busy 时 `>0.12s` 刷一帧（app.py:182）≈8.3 fps——频率本身 OK，问题在它被 dim 成了「快熄灭的小灯」。
- 为什么伤害美感：spinner 的全部职责是**抓住余光、确认「活着、在干活」**。把它 dim 到 3.08:1 + 放在 60 列之外的角落，它就成了一个「要看才看得见」的细节，丧失了外围感知功能；用户会反复怀疑「是不是卡死了」。而真正抢眼的忙碌指示（◇ Refracting 粗体青）又在另一个位置、用另一套色，两者不打招呼——忙碌态的视觉语言是分裂的。
- 具体改进建议：
  - spinner 不要 `[dim]`：用 `accent` 或一个专用 `busy` token（如 dark `#8abeb7` 8.53:1），让它自带「我在动」的存在感。
  - 统一忙碌视觉：要么只用 footer spinner、要么只用 ◇ Refracting，**不要两套并存且权重相反**。建议保留 footer spinner（信息更全：model+thinking+动画），把 `#status` 的 ◇ Refracting 去掉或降级为与 spinner 同色同权重。
  - spinner 放到 model 文字**左侧紧贴**，别隔 60 列空白。

---

### [P2] 认知阶段标签用色随心所欲——5 个对等阶段 4 种 markup 色 + 1 个无色，无色阶体系

- 证据：
  - `widgets.py:105`「行动」`[cyan]`(#00d7ff)、`widgets.py:115`「观察」**无色仅 `[bold]`**、`widgets.py:123`「思考」`[blue]`(#5f87ff)、`widgets.py:129`「直觉」`[magenta]`(#9575cd)、`widgets.py:129`「反思」`[yellow]`(#ffff00)。
  - 这 5 个是同一套「认知循环」里的对等阶段标签，却用了 4 种互不相干的色相 + 1 个破例不着色；明度/饱和度也毫无规律（cyan 满饱和亮青、blue 中蓝、magenta 暗紫、yellow 纯黄）。
- 为什么伤害美感：语义着色的价值在于「颜色 = 类别」的稳定映射。这里颜色更像「作者写到哪随手挑了一个」，用户无法从颜色反推阶段类型（为什么「反思」是黄、「直觉」是紫？没有认知依据也没有色彩学依据）。加上「观察」破例无色，规律彻底碎掉。
- 具体改进建议：
  - 给 5 阶段定一个**单色相、靠字重/符号区分**的体系：如全部用 `accent` 色，行动/观察（外部动作）用粗体、思考/直觉/反思（内部推理）用斜体；或用 2 色封顶（行动系=青、推理系=紫），不要 5 色。
  - 「观察」补上和「行动」同系的色，恢复规律。

---

### [P2] truecolor 无 256 色降级——`COLORTERM` 非 truecolor 的 tmux/旧 SSH 下，整套配色静默回退到默认前景

- 证据：
  - `prism/tui/markup.py:37-47` `_fg_code`：tuple 一律 `38;2;r;g;b`，int 索引才走 `38;5;i`。主题色（`app.py` 的 `_h(...)` 全是 tuple）与 markup `#hex`（`markup.py:120`）**全部走 truecolor**。
  - 取证实测 SGR 参数：`accent → 38;2;138;190;183`、`editor_border → 38;2;255;20;147`、`yellow → 38;2;255;255;0`——**没有任何一条做 256 色近似**。
- 为什么伤害美感/健壮性：大量真实环境默认不是 truecolor：`tmux` 老配置（`default-terminal` 非 `tmux-256color` + `terminal-overrides` 未设）、部分企业 SSH 跳板机、Windows `cmd.exe`（非 WT）、CI 日志。这些终端收到 `38;2;r;g;b` 要么忽略、要么渲染成默认前景色——于是 accent 青、editor 粉、banner 五彩**全部塌成同一个终端默认色**，整套精心配色在一部分用户那里就是纯色字符画。一个宣称「2026 一流 TUI」的产品应当优雅降级，而不是「不支持 truecolor 就裸奔」。
- 具体改进建议：
  - 在 `Terminal.__enter__`（terminal.py:135）探测 `os.environ.get("COLORTERM")` 是否含 `truecolor`/`24bit`；否，则设 `self._truecolor=False`。
  - `_fg_code`（markup.py:37）在非 truecolor 时把 RGB 近似到最近 xterm-256（标准立方根量化公式），发 `38;5;i`。`Style`/主题色路径同步走这个近似。
  - 216 色立方 + 24 灰阶的最近邻映射约 20 行，零依赖即可。

---

### [P2] 语义色板 62% 是死配置——24 个 token 里 15 个从未被渲染路径读取，「设计系统」名存实亡

- 证据：
  - 取证统计（dark 主题 24 个 token）：实际经 `style()`/CSS `$token` 引用的仅 ~9 个（`accent`/`text`/`thinking_text`/`editor_border`/`border_muted`/`user_bg`/`tool_*_bg` 等）。
  - **死 token（定义即虚构）15 个**：`warning #ffff00`、`primary #5f87ff`、`border #5f87ff`、`border_accent #00d7ff`、`success #b5bd68`、`error #cc6666`、`muted #808080`、`custom_label #9575cd`、`md_heading #f0c674`、`tool_output #808080`、`user #d4d4d4`、`page_bg`、`thinking_bg`、`cognitive_bg`、`dim`（dim 仅经 markup `[dim]` 间接生效，非经 `style("dim")`）。
  - 其中 `error`/`success` 尤其讽刺：代码里报错/成功**根本没用这两个 token**，而是用 markup `[red]`/`[green]`（`shell.py:239/365`），所以 `error #cc6666`/`success #b5bd68` 这两个语义色定义了却完全旁路。
- 为什么伤害美感：一个色彩系统的价值是「可推理」——设计师和后人能看着 token 表判断「这个语义是什么色、对比够不够」。当 62% 的 token 是死的，token 表就成了谎言：你以为有 `warning` 体系，实际警告色走的是 markup `[yellow]`（且在浅色下隐形，见 P0#1）；你以为 `error` 是 `#cc6666`，实际报错是 markup `red #cc6666`——巧合同色但路径不同，一旦改一个不改另一个就会漂移。系统失去了单一事实源。
- 具体改进建议：
  - 二选一：(a) 把所有 markup 着色（`[red]`/`[green]`/`[yellow]`/`[cyan]`）改成走 `style(token)`，让 `error`/`success`/`warning`/`accent` 等 token 成为唯一事实源；(b) 删掉所有死 token，token 表只留实际生效的，别留诱惑。
  - 优先做 (a)：既修了 P0#1（markup 主题化）、又消灭了死 token、又建立了「语义色单一来源」，一举三得。

---

## 本轮取证脚本（附录）

取证脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_aesthetic_forensics.py`。完整输出：`C:/Users/cty18/AppData/Local/Temp/prism_aesthetic_evidence.txt`。

要点：
- `make_app()` 实例化 `PrismApp`，调 `_build()`（compose + CSS parse + mount），**不调 `on_mount`**（避免连网/建 agent/写 banner）。
- `seed(app)` 手工 `log.user/tool_start/tool_end/thinking/cognitive(intuition|reflect)/write` 喂入多阶段真实内容。
- `render(app, theme)` 切 `app.theme` 后 `_render_frame(24,80)`，得到真实 `Buffer`。
- WCAG 对比率手算：`lum`（gamma 线性化）→ `contrast = (Lmax+0.05)/(Lmin+0.05)`。
- cell 矩阵 dump：遍历 `buf.grid[y]`，打印每 cell 的 `[ch] fg=#.. bg=#.. [BIDU]`。
- page_bg 覆盖率：统计全屏 `cell.style.bg is None` 的占比。
- token 死活：`set(DARK) - 实际经 style()/CSS 引用的 token`。
- 覆盖 10 组取证：page_bg 覆盖率(dark/light)、浅色 [yellow] 失效矩阵 + `_COLOR` 全表对比率、editor_border 饱和度/对比率、灰阶 token 对比率、光标浅色对比率、banner 五色饱和度、footer spinner dim 矩阵、阶段标签色映射、truecolor SGR 参数、死 token 清单。

核心取证模式（逐 cell + 对比率）：
```python
# 证明浅色主题 [yellow]「反思」标签隐形
buf = render(app_light)                      # 80x24 真实渲染
for y in range(24):
    if "反思" in "".join(c.ch for c in buf.grid[y]):
        for x in range(80):
            if buf.grid[y][x].ch == "反":
                fg = buf.grid[y][x].style.fg   # → (255,255,0)
                # bg=None(透传) → 按设计意图 page_bg=#ffffff 评价
                contrast((255,255,0), (255,255,0))  # → 1.07:1  不可读
```

```python
# 证明 page_bg 从不绘制
bg_none = sum(1 for row in buf.grid for c in row if c.style.bg is None)
# → 1359/1920 = 70.8% 透传终端默认背景
```
