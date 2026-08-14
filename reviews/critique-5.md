# 批判轮5：可发现性与新手体验（评审人：终端 UX 可发现性/新手引导评审专家）

评审视角：冷启动第一屏说了什么没说什么、帮助系统覆盖率与正确性、功能（补全/历史/滚动/主题/思考开关）不读源码能否发现、agent 状态（在干什么/卡没卡/失败了怎么办）能否一眼看懂、认知层黑话（直觉/反思/折射/forest）对新用户是否有引导、渐进披露与空态/错误态的自救能力。

方法：通读 `prism/shell.py`、`prism/tui/{app,widgets,markup,buffer}.py`、`prism/{commands,agent_loop,agent_registry,model}.py`、`ext/commands/*.py`、`ext/agents/*`、`plan/rlm/README.md`，走「新用户路径」：冷启动 → 打第一句话 → 犯错 → 求助 → 补全 → 换目录再启动。写无头取证脚本（附录），`PrismApp().run(headless=True)` 装配 + `on_mount`（dummy key，不发任何网络请求），按 `tests/test_tui.py` 的 submit 手法喂输入，`render_to_string(24,80)` 逐帧 dump、逐 cell 检查 fg/bg；另用子进程验证「无 API key」与「非项目根目录」两种冷启动。所有渲染片段 / cell 矩阵 / traceback 均出自真实取证，非脑补。

共 **12 条**问题。分布：**P0 ×3，P1 ×7，P2 ×2**。

> 不重复轮1（布局/IA）、轮2（键盘交互，含 Escape 无提示、补全方向键失效、无历史）、轮3（视觉）、轮4（文案，含空 placeholder、``` 围栏泄漏）。与本轮视角有交集者只做**新证据深化**：轮2 提过「Escape 无提示」→ 本轮给全量键位 0/N 有文档的系统性证据；轮4 提过「空 placeholder/空态无引导」→ 本轮证明**默认输入路由本身就是陷阱**（自然语言→Python 报错）且报错无自救引导；轮4 提过模型输出围栏泄漏 → 本轮证明**用户自己的输入**和 **/help 自己的文案**也在被 markup 解析器吞。

---

## 发现的问题

### [P0] 没配 API key 的第一次启动直接崩出 Python traceback——TUI 一帧都没渲染

- 证据：
  - 启动链：`prism/tui/app.py:156` `run()` 先调 `self.on_mount()`（无 try/except），`prism/shell.py:251` → `restore_agents` → `prism/agent_registry.py:88` `OpenAIModel(...)` → `prism/model.py:44-47` `OpenAI(api_key=... or os.getenv("OPENAI_API_KEY"))`。环境无 `OPENAI_API_KEY` 时 openai 客户端在**构造期**抛错，一路裸传到顶层。
  - 子进程取证（清掉 key 后 `python -m prism.shell`，崩溃发生在进入 `Terminal()` 之前，用户看到的是普通 shell 里的裸栈）：
    ```
    File "prism\tui\app.py", line 156, in run
        self.on_mount()
    File "prism\shell.py", line 251, in on_mount
        main_agent, subs = restore_agents(self, emit)
    File "prism\agent_registry.py", line 88, in restore_agents
        model = OpenAIModel(
    File "prism\model.py", line 44, in __init__
        self.client = OpenAI(
    openai.OpenAIError: The api_key client option must be set either by passing api_key
    to the client or by setting the OPENAI_API_KEY environment variable
    ```
  - `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`PRISM_MODEL` 只在 `model.py:33-37` 的 **docstring** 里提过，UI 内零提示；仓库也没有根级 README（只有 `plan/`、`devlog/` 的开发文档），新用户无从得知要先配环境变量。附带伤害：`tests/test_tui.py` 在无 key 环境下同样全体失败（取证：`test_tui_mounts_main_agent_and_widgets` FAILED, openai.OpenAIError）——「用测试验证装好了」这条路对新手也是断的。
- 为什么新手会卡住/流失：这是**字面意义上的第一秒**。一个 clone 下来直接 `python -m prism.shell` 的新用户，看到的是 15 行和自己无关的 Python 内部栈，「The api_key client option must be set」这句唯一的线索埋在栈底、还是英文。没有「如何配置」、没有「配完再跑」、没有降级模式（哪怕进 TUI 显示配置引导）。绝大多数用户在这里就关窗口了。
- 具体改进建议：
  1. `shell.py` `on_mount`（或 `main()`，shell.py:470）入口先自检：`if not os.getenv("OPENAI_API_KEY") and not agent_yaml_key:` → 打印/渲染一段三行引导：`未检测到 API key。请设置 OPENAI_API_KEY（或 OPENAI_BASE_URL 指向兼容网关）后重新启动。` 然后 `sys.exit(2)`，别让 openai 的构造异常裸奔。
  2. 更好的做法：key 检查放在 `Agent` 创建**之前**，允许 TUI 以「未配置态」启动，transcript 写引导块、输入框 placeholder 提示配置方法，`@` 路由在未配置时给出明确报错。
  3. 根目录补一个 20 行 README：安装 → 配 key → 启动 → `/help`。

---

### [P0] 自然语言默认路由是 Python exec：新用户第一句话必然得到 SyntaxError/NameError，且报错不给任何出路

- 证据：
  - `prism/shell.py:349-358`：输入不以 `/` 或 `@` 开头 → 直接 `exec(compile(text, "<prism>", "exec"), ns)`，异常只写一行红字 `[red]{type(e).__name__}: {e}[/]`，无任何后续建议。
  - 取证（E 组，新用户裸打两句话，80×24 渲染帧）：
    ```
    09│ how to refactor this function
    11│ SyntaxError: invalid syntax (<prism>, line 1)
    13│ 怎么重构这个函数
    15│ NameError: name '怎么重构这个函数' is not defined
    ```
    英文整句 → SyntaxError；中文整句恰好是合法 Python 标识符 → NameError。
  - 「要和 agent 对话必须 `@Prism ...`」这一事实，全 UI 只有 Header 右侧一行 dim 小字 `widgets.py:16` `"/ commands · @ agents · python"`，冷启动整屏取证：出现 `/help` 字样 **False**、出现 `@Prism` **False**、placeholder 为空串（`shell.py:37`）。轮4 已批「placeholder 为空」，但那条建议的文案「问我任何问题」恰恰会**误导**用户裸打自然语言——真正的问题是默认路由根本不通向 agent。
- 为什么新手会卡住/流失：新用户对 coding agent 的本能操作就是打一句自然语言。这里的第一反馈是一条红色的 Python 异常，看起来像「程序坏了」而不是「你用错了入口」。没有「你是不是想问 agent？用 @Prism」的提示，没有 `/help` 指路，用户第二次尝试大概率还是自然语言（换个说法），再次报错，然后流失。对知道内情的人这是 feature（python 直通），对不知道的人这是 onboarding 黑洞——而产品恰恰没有把「知道内情」的成本付掉。
- 具体改进建议：
  1. `on_input_submitted` 的 exec 异常分支（shell.py:355-356）加启发式引导：当异常是 `SyntaxError/NameError` 且文本不含明显代码特征（`=`、`(`、`:`、行数>1 等）时，追加一行 `[dim]（这是 Python 直通模式。要问 agent 请用 @Prism <问题>；/help 查看指令）[/dim]`。
  2. 冷启动 banner 末尾加一行 onboarding（`shell.py:290-293` 之后）：`[dim]试试：@Prism 帮我看看这个项目 · /help 查看指令[/dim]`——注释写着「不打印 banner/tools/cmds」（shell.py:282），不打印全表可以，但**一个指路都没有**就是另一回事。
  3. placeholder（shell.py:37）改为 `@Prism 问事 · /help 指令 · 直接输入跑 Python`，把三种路由明示在输入框里。

---

### [P0] 用户自己输入的方括号被当 markup 标签吞掉：`arr[0]` 之后整行变黑（对比度 1.7:1），`[i]`/`[TODO]` 直接蒸发

- 证据：
  - `prism/shell.py:301` `log.user(text)` **不做转义**；`prism/tui/widgets.py:158-160` block body 渲染走 `parse_markup`；`prism/tui/markup.py:153-164` 遇 `[...]` 一律当标签：body 是数字 → `markup.py:123-124` `fg=int(...)`（`[0]`→前景纯黑），未知 body → 空 delta、字符**整段删除**。
  - 取证（F 组，提交 `看下 arr[0] 和 arr[i] 哪里越界 [TODO] 修一下`，80×24 帧 + 逐 cell）：
    ```
    09│ 看下 arr 和 arr 哪里越界  修一下        ← [0]/[i]/[TODO] 全部消失
    cell[1]='看' fg=default bg=(52,53,65)
    cell[6..8]='arr' fg=default
    cell[10]='和' fg=0 bg=(52,53,65)          ← [0] 之后整段 fg=(0,0,0)
    cell[13..31] 'arr…哪…里…越…界…修…下' fg=0  ← 黑字压在 user_bg #343541 上
    ```
    `#000000` on `#343541` = **1.73:1**（WCAG 正文 4.5:1）——用户消息的后 2/3 在暗色主题里基本不可见。`parse_markup` 佐证：`seg='看下 arr' fg=None` → `seg=' 和 arr' fg=0` → 后续全部 fg=0。
  - 代码库其实**知道**这个坑并保护了另外两条路径：认知事件 `shell.py:234` 与工具结果 `widgets.py:116` 都做了 `.replace("[", "\\[")`，唯独**用户回显**没有。转义语法 `\[` 存在（markup.py:149）但 UI 内零文档。
- 为什么新手会卡住/流失：coding agent 用户输入里方括号无处不在——`arr[i]`、`[TODO]`、markdown 链接 `[文档](url)`、异常文本 `list index out of range`、粘贴的日志 `[INFO] ...`。新用户第一次带方括号提问，就会看到**自己的话被吃掉一半、剩下的变黑**，第一反应是「这 app 有 bug / 我是不是打错了什么控制字符」。没有任何报错、没有任何文档解释这是 markup 语法。这是把一个内部渲染协议的泄漏直接砸在用户脸上。
- 具体改进建议：
  1. `shell.py:301` 改为 `log.user(text.replace("[", "\\["))`（与 cognitive/tool_end 同款处理），一行修掉回显路径。
  2. 更彻底：`_LineUnit`/`RichLog.write` 区分「内部 markup 消息」与「用户/工具原文」，原文走 `parse_markup(escape=True)`（markup.py 加 `escape` 参数把未配对/未知标签按字面处理）。
  3. 若坚持暴露 markup 给用户（像 IRC 彩色码那样的「特性」），就必须文档化：`/help` 加一段「输入支持 [red]…[/] 着色，字面 [ 用 \[ 转义」。现在的状态是：特性存在、转义存在、文档为零。

---

### [P1] /help 的用法语法被自己的 markup 解析器吞掉——`[name]`、`[n|none]`、`[coder]`、`[描述]`、`[prompts|tools|skills|all]` 全部不显示

- 证据：
  - `ext/commands/help.py:14-16` 把 DESC 原样拼进多行文本返回；`shell.py:328-329` `log.write(result)` → `parse_markup` 吃掉所有 `[...]` 段。
  - 取证（B 组，`/help` 渲染帧 80×24，左为 DESC 原文、右为屏幕实际显示）：
    ```
    DESC 原文: 最大轮数: /maxturns [n|none]  (默认 none=无限信任LLM)
    屏幕实际:   /maxturns   最大轮数: /maxturns   (默认 none=无限信任LLM)   ← [n|none] 没了
    DESC 原文: 切换/查看模型: /model [name]
    屏幕实际:   /model      切换/查看模型: /model                            ← [name] 没了
    DESC 原文: 重载 ext/ 插件: /reload [prompts|tools|skills|all]
    屏幕实际:   /reload     重载 ext/ 插件: /reload                          ← 参数表整个没了
    DESC 原文: 创建新 skill: /skill-create <name> [描述]
    屏幕实际:   /skill-create 创建新 skill: /skill-create <name>             ← [描述] 没了
    DESC 原文: spawn 子 agent: /spawn <name> [coder]
    屏幕实际:   /spawn      spawn 子 agent: /spawn <name>                    ← [coder] 没了
    ```
    `/maxturns` 在帮助里看起来**不接任何参数**；`/reload` 的四种重载范围一个都看不到。帮助系统恰好把自己最该交付的信息——参数语法——删掉了。
- 为什么新手会卡住/流失：`/help` 是新手遇到错误后的第一求助点。它现在给出的命令签名是残缺的：用户照着屏幕上的 `/reload` 裸敲，得到全量重载而非预期的只重载 prompts；想给 skill 建模板时不知道 `/skill-create` 还能带描述。用户无法区分「这条命令没参数」和「帮助把参数弄丢了」，要么放弃功能，要么靠试错。
- 具体改进建议：
  1. `help.py:15-16` 拼行时对 desc 转义：`desc.replace("[", "\\[")`（项目内已有同款先例 shell.py:234）。
  2. 或者让所有指令输出走一条「默认转义、显式标记才解析 markup」的写入口（`RichLog.write_plain()`），命令返回值当纯文本——命令作者不该需要懂 TUI 的 markup 协议才能写一条帮助。
  3. 补一条单测：`/help` 输出的每个 DESC 渲染后必须包含原文里的 `[` 数量（现在必挂）。

---

### [P1] 同一份命令表，/help、补全浮层、未知指令报错给出三个互相矛盾的答案

- 证据（三组取证对照）：
  - `/help` 列出 **9** 条：`/goal /help /maxturns /model /reload /skill /skill-create /spawn /thinking`——**漏掉 `/revert`、`/backups`**（取证 B：`/help 漏掉: ['/backups', '/revert']`）。
  - 补全浮层 **11** 条，且尾部乱序：`['goal','help','maxturns','model','reload','skill','skill-create','spawn','thinking','revert','backups']`（`shell.py:94` `sorted(...) + ["revert","backups"]` 直接拼接，revert/backups 排在 thinking 之后，非字典序；取证 D）。
  - 未知指令报错 **11** 条：`/nope — 未知指令。可用: /revert /backups /goal /help …`（`shell.py:321`，取证 C）。
  - 根因：内置命令 `/revert`/`/backups` 走 `shell.py:360-375` `_builtin_command`，不在 `self.commands` 里；`help.py:11` 只读 `ctx["commands"]`，而浮层（shell.py:94）和报错（shell.py:321）各自手工补挂。同一个事实有三处独立维护，已经漂移。
- 为什么新手会卡住/流失：新手建立信任的方式是「帮助说的和实际发生的一致」。现在 `/help` 说没有 `/revert`，敲 `/revert` 却能用；浮层里 `/revert` 排在最后且和字母序格格不入。用户会开始怀疑所有列表都不完整，然后回到「什么都试一遍」的石器时代。更讽刺的是：**未知指令的报错比 /help 更完整**——帮助系统是全 app 信息量第二低的那一个。
- 具体改进建议：
  1. 建单一事实源：`PrismApp.all_commands()` 返回 `{name: desc_or_callable}`，`self.commands`、`_builtin_command`（shell.py:360）、`_on_input_changed`（shell.py:94）、未知指令报错（shell.py:321）、`help.py` 全部读它。
  2. 浮层排序统一 `sorted(...)`；给内置命令补 DESC（`_builtin_command` 返回值带描述），`/help` 就能列出全部 11 条。
  3. `/help` 头部加一句「键位见底部 / 按 ? 查看按键」，把命令帮助和按键帮助串起来（见下条）。

---

### [P1] 键位帮助体系整体缺失：全 app 10+ 个按键绑定，文档化的有 0 个

- 证据（轮2 已单独提过 Escape 无提示，此处给全量盘点这一**系统性**缺口）：
  | 按键 | 行为 | 代码 | 任何 UI 文档？ |
  |---|---|---|---|
  | Esc | 中断运行中的 agent | shell.py:42-47 | 无 |
  | Ctrl+C | 清空输入 / 双击退出 | app.py:217-233 | 无（仅触发后出现一句英文 `(Ctrl+C again to quit)`） |
  | Tab | 补全选中命令 / 光标处循环插入 `@agent` | shell.py:49-83 | 无 |
  | Shift+Enter | 输入框换行 | widgets.py:358-361 | 无 |
  | Ctrl+A/E/U/K/W | 行首/行尾/删到行首/删到行尾/删词 | widgets.py:390-403 | 无 |
  | PageUp/PageDown/Home/End | 滚动 transcript（半屏/顶/底） | app.py:244-251 | 无 |
  | ↑/↓ | 单行时滚 transcript | app.py:252-260 | 无 |
  - 取证（B/D 组）：`/help` 输出中含 Esc/Tab/Ctrl/按键字样 = **False**；补全浮层渲染文本中含 `Tab/↑/↓/Enter/选择` 提示 = **False**；Header 只有一行 `"/ commands · @ agents · python"`（widgets.py:16，不涉及任何按键）；Footer 只有 `model · thinking`（widgets.py:486）。
- 为什么新手会卡住/流失：这些绑定里有**高频刚需**：Shift+Enter 换行（不告诉你，你永远以为输入框是单行的）、Tab 补全（不告诉你，浮层出现你只会继续打字）、Esc 中断（轮2 已证明 Ctrl+C 不能中断）。终端用户不会去按 F1——他们靠 header/footer 的键位提示带路（pi/claude-code 都在 footer 常驻 `? for help` 一类提示）。这里 footer 两行 60+ 列空白（轮1 已批浪费），却一个键位都不肯放。
- 具体改进建议：
  1. `/help`（help.py）扩成三段：`指令` / `按键`（上表照抄）/ `输入路由`（`/` 指令、`@` agent、裸文本=Python）。这不需要新框架，就是往 DESC 后面多拼十几行字符串。
  2. Footer 第二行（widgets.py:486）右侧在 idle 时显示 `[dim]? 帮助 · esc 中断 · shift+enter 换行[/dim]`，busy 时让位给 spinner。
  3. 提供一个全局 `?` 键（`_dispatch_key`，app.py:214）打开同一个帮助浮层，覆盖「不记得命令名」的场景。

---

### [P1] 补全浮层高亮了 `/model`，Enter 却提交裸前缀 `/mod`——标准「回车接受」缺失，且浮层提交后残留

- 证据（D 组，走真实输入路径）：
  - 逐字符输入 `/mod` → 浮层过滤出 `['model']`、选中 `model`（渲染帧：第 10 行 `▸ /model`，输入框 `/mod`）。
  - 按 Enter（`widgets.py:358-364` 直接 `self.app._input_submitted(...)` 提交 `self.value`，**不看浮层**）：
    ```
    /mod
    [red]/mod — 未知指令。可用: /revert /backups /goal /help /maxturns /model /reload /skill /skill-create /spawn /thinking[/]
    Enter 后浮层还在吗: True        ← 提交清空走 dock.clear()，不触发 _on_input_changed，浮层不消失
    ```
  - 正确路径只有 Tab（shell.py:53-61），而 Tab 的这一职责在全 UI 无任何提示（见上条）。
- 为什么新手会卡住/流失：浮层画了 `▸` 高亮、画了 `(1/n)` 分页指示，视觉语言承诺「这是个可选列表」。所有补全 UI（shell、浏览器地址栏、IDE）的肌肉记忆都是 **Enter 接受**。这里 Enter 反而把残缺前缀当命令提交，回你一条红色「未知指令」+ 一整行命令表——用户明明「看到并选中了」/model，却被系统告知它不存在。叠加浮层残留，屏幕同时出现：错误信息 + 旧浮层 + 空输入框，状态彻底不可读。轮2 证明了 ↑↓ 选不了；这条证明即便不动箭头、纯靠过滤+Enter 也过不去。补全的可达路径只剩「知道 Tab 秘籍的人」。
- 具体改进建议：
  1. `Input.on_key` 的 enter 分支（widgets.py:358）之前问一句 app：`if self.app._completion_active(): 取 selected_value 回填后再提交`（或至少回填不提交）。
  2. 提交路径统一走「值变化」：`Input` 提交清空后调用 `app._on_input_changed("")`（或 app 层 `_input_submitted` 末尾 `self._hide_cmd_overlay()`，shell.py:296），消灭浮层残留。
  3. 浮层底部加一行 `[dim]↑↓ 选择 · Tab/Enter 补全 · Esc 关闭[/dim]`（SelectList.draw，widgets.py:265 附近），把三件事一次讲清。

---

### [P1] 换个目录启动，9 条命令全部蒸发，`/help` 自己都变成「未知指令」——启动零自检

- 证据：
  - `shell.py:248-249` `load_ext("ext", ...)` / `load_commands("ext", ...)`、`commands.py:23` `Path("ext") / "commands"`、`agent_registry.py:30` `agents_dir="ext/agents"`——全是**相对 cwd** 的路径。仓库根有 `ext/`，但 `pyproject.toml` 装出来的 `prism` 命令可以在任何目录跑。
  - 子进程取证（cwd = 临时目录，dummy key）：
    ```
    cwd: C:\Users\cty18\AppData\Local\Temp\prism_cwd_test
    commands: []
    --- /help in empty cwd ---
    '/help'
    '[red]/help — 未知指令。可用: /revert /backups[/]'
    completion items: ['revert', 'backups']
    ```
    TUI 正常起来了、banner 照放、输入框照粉——但指令系统、agent prompt、tools、skills 全部静默缺失，唯一剩下的「帮助」是未知指令报错里那两个内置命令。启动时 `emit` 有 `ext_error` 通道（commands.py:40-42），但目录不存在时根本不触发（`if not cdir.is_dir(): return {}`，连一条日志都没有）。
- 为什么新手会卡住/流失：新用户不会理解「命令加载和 cwd 有关」这种实现细节，他们看到的是「同一个程序，换了个文件夹就少了一半功能，而且没告诉我」。`/help` 报「未知指令」尤其荒诞——求助本身成了错误。没有任何「未找到 ext/，正在裸奔」的警告，用户只能靠猜（或读源码）发现差别。
- 具体改进建议：
  1. `on_mount` 末尾加自检并写 transcript：`if not self.commands: log.write("[yellow]⚠ 未找到 ext/ 插件目录(当前 cwd=…)：指令/skill/agent 配置未加载。请在项目根启动或配置 PRISM_EXT_DIR。[/yellow]")`。
  2. ext 路径解析改为「包根/安装前缀 + 环境变量覆盖」：`Path(os.getenv("PRISM_EXT_DIR", Path(__file__).parent.parent / "ext"))`，别赌 cwd。
  3. `/help` 空表时（help.py:12-13 现在返回 `(无可用指令)`）附原因和修复建议，而不是一句孤零零的括号。

---

### [P1] agent 卡在重试/网络错误时 UI 是黑箱：auto_retry 事件被静默丢弃，最终错误只有裸异常文本、无下一步

- 证据：
  - `prism/agent_loop.py:116-120` 网络失败会 emit `auto_retry_start`（attempt、error）与 `auto_retry_end`（attempts、gave_up）。`prism/shell.py:193-244` 的 emit 处理器**没有这两个分支**（也没有 turn_start/message_start/turn_end），事件直接蒸发。
  - 取证（G 组，直接调 `app.agent.hooks["emit"]`）：
    ```
    喂入 5 个事件(turn_start/message_start/auto_retry_start/auto_retry_end/turn_end)后 transcript 新增 0 行
    喂入 error 事件后 tail:
      '[red bold]✗ error:[/red bold] [red]APIConnectionError: Error code: 401 - invalid api key[/red]'
    ```
    重试期间用户看到的只有 `◇ Refracting...`（shell.py:150-159）——一个不说明在做什么、重试到第几次、还剩几次的动画。
  - 最终 `error` 文案是异常 `repr` 原样输出，401/超时/限流/欠费全部长一个样，没有「检查 OPENAI_API_KEY」「稍后重试」「用 /model 换 endpoint」这类下一步。`turn_start/turn_end` 等被丢的事件倒是无伤大雅，但 auto_retry 是**用户等待体验**的直接来源。
- 为什么新手会卡住/流失：新用户最容易碰到的故障就是网络/密钥/限流，而这恰恰是 UI 表现最差的场景：动画照转（像活着）、没有重试信息（像卡死）、失败后一行天书（像坏了）。用户无法区分「正常思考中」「在重试」「已经死了」三种状态，唯一能做的是按 Esc（还得先知道 Esc 能中断——见键位那条）。状态不可理解 = 不信任。
- 具体改进建议：
  1. `emit`（shell.py:193）补两个分支：`auto_retry_start` → status 行改为 `[yellow]↻ 重试 {attempt}: {error 截断}[/yellow]`（复用 `_start_status` 的线程，比静默 Refracting 信息量大一个量级）；`auto_retry_end` → `log.write(f"[yellow]✗ {attempts} 次重试后放弃: {error}[/yellow]")`。
  2. `error` 分支按异常类型给指引：401/403 → `检查 OPENAI_API_KEY / OPENAI_BASE_URL`；timeout → `网络超时，可重试或 /model 换模型`；其余保留原文。落点在 shell.py:236-239。
  3. 顺手把 `turn_*`/`message_start` 这类事件在 emit 里显式 `pass` 注明「有意忽略」，避免下一个读代码的人以为漏了。

---

### [P1] 认知层黑话（直觉/反思/based_on/折射/forest）对新用户零引导——默认就开、从天而降

- 证据：
  - 默认配置 `PRISM_INTUITION=small`（shell.py:266-276），即**每个新用户第一次对话**就会看到 `直觉 ▸ …（基于 …）`（widgets.py:125-133，magenta）与 `反思 ▸ …`（yellow）、`思考 ▸ …`（blue）、`行动/观察`（cyan/bold）、忙碌态 `◇ Refracting...`（shell.py:155）。
  - 这些词在 UI 内的解释：**零**。`/help` 取证：不含 `直觉/反思/折射/forest` 任何字样；banner 之后无 legend；placeholder 为空。唯一「文档」是 `plan/rlm/*.md`——而且是写给开发者的设计提案（状态自标「未实现」），仓库**没有根 README**，新用户拿不到任何一份面向用户的说明。
  - `based_on` 后缀（widgets.py:130-132）指向 forest 的自指轴（plan/rlm/tree.md 的概念），用户看到的只是一串神秘英文元信息；`PRISM_INTUITION` 环境变量（off/heuristic/small 三档，shell.py:266-276）决定直觉开不开，UI 内无处可查、无处可改。
- 为什么新手会卡住/流失：新用户的第一次运行会同时遭遇两套未知词汇：`◇ Refracting`（它在干嘛？折射是什么？）和彩色阶段标签（直觉是模型说的还是我说的？based_on 什么意思？）。轮3 已批这些标签的颜色乱、轮4 已批中英混杂，但**语义层面**的引导缺失没被提过：没有任何一处告诉用户「这是 RLM 认知循环：直觉→思考→行动→观察，based_on 是依据链」。用户只能把「直觉/反思」当成噪音忽略——认知层作为产品差异点，对新手是纯负资产。
- 具体改进建议：
  1. 首次出现认知块的会话，在其上方插一行一次性 legend（`log.write("[dim]认知循环: 直觉→思考→行动→观察 · based_on=依据 · 详见 /help 概念[/dim]")`，用 forest 里已有的 session 维度判首次）。
  2. `/help` 加「概念」段：3 行讲清 直觉/反思/折射/based_on 是什么、`PRISM_INTUITION` 三档怎么配。
  3. `◇ Refracting` 与轮4 的建议合并解决：改「折射中…」或直接说人话（「思考中/调用工具中」——tool_execution_start 事件其实已有，status 行可以在工具调用期间显示 `▸ {tool_name}`，比恒定 Refracting 信息量大得多）。

---

### [P2] 主题切换与直觉开关没有任何用户级入口：`theme.set('light')` 只能「求 agent」或懂 Python 直通

- 证据（H 组取证）：`available_themes: ['dark','light']`；命令表无 `/theme`（`'theme' in app.commands → False`）；`/help` 输出无 theme 字样；`ThemeCtl` 只挂在 agent namespace（shell.py:277，类定义 shell.py:426-440）。想切浅色的用户只有两条路：用 `@Prism` 自然语言求 agent（还得指望 agent 知道自己 namespace 里有 theme 对象），或裸敲 Python `theme.set('light')`（得先知道 namespace 直通这件事——而这件事的唯一提示是 header 里那个 `python` 单词）。`PRISM_INTUITION` 三档同理，只有环境变量一条路。
- 为什么新手会卡住/流失：浅色终端用户是真实存在的群体，而本产品的浅色主题**做都做了**（轮3 证明它还做坏了）。功能存在但入口是「和 AI 聊天让它帮你切」——这不是渐进披露，是把开关藏进抽屉再锁上。发现成本远高于价值。
- 具体改进建议：
  1. 加 `/theme [dark|light]` 指令（ext/commands/theme.py，10 行，调 `ctx["app"].available_themes` + 赋 `app.theme`），`/help` 自动收录。
  2. `/config`（或扩展 `/help`）列出 `PRISM_INTUITION`、`PRISM_MODEL`、`PRISM_TIMEOUT`、`OPENAI_BASE_URL` 等环境变量及当前值——它们现在是产品唯一配置机制，却完全不可见。

---

### [P2] 冷启动 footer 就谎报军情：显示从未配置过的 `gpt-4o-mini`

- 证据（A/I 组取证）：环境无 `PRISM_MODEL`、`ext/agents/prism/agent.yaml` 无 model 字段 → `model.py:49` 兜底 `"gpt-4o-mini"` → footer 常驻 `gpt-4o-mini · thinking medium`。而这个项目的文档/意图全程是 GLM 系（ext/agents 里 thinking_level: medium、model.py 注释 glm）。用户没配过任何模型，状态栏却言之凿凿地显示一个具体模型名，没有任何「默认值」标记，也不知道 `/model` 能改（除非翻 /help）。
- 为什么新手会卡住/流失：状态栏是用户校准信任的锚点。第一次启动就显示一个和自己无关的模型，用户要么以为「这就是接的模型」而困惑于后续行为，要么怀疑配置丢了。属于小伤口，但发生在第一屏、且与「模型到底是什么」这个 agent 用户最关心的问题直接相关。
- 具体改进建议：`widgets.py:483-486` footer 显示 `model or '未配置模型'`；或检测到 env 未设时显示 `gpt-4o-mini (默认 · /model 可切换)`。同时 `thinking medium` 同理可标 `/thinking 可调`。

---

## 本轮取证脚本（附录）

主脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_disc_forensics.py`，完整输出 `C:/Users/cty18/AppData/Local/Temp/prism_disc_evidence.txt`。另两组子进程取证（无 key 崩栈、非项目根 cwd）为一次性命令，输出已摘录在上文。

要点：
- `mount()` = `PrismApp().run(headless=True)`（装配 + on_mount，`OPENAI_API_KEY` 设 dummy 仅为通过 `OpenAI()` 构造，全程零网络请求）。
- `submit(app, value)` 按 `tests/test_tui.py` 手法设 `dock.value/pos` 后 `dock.on_key(Key("enter"))` + `_drain()`，走真实提交路径。
- `frame()` = `render_to_string(24,80)` 逐行 dump；F 组另开 `app._render_frame` 遍历 `buf.grid` 逐 cell 打印 `fg/bg`，证明 `[0]` 后整段 fg=(0,0,0)。
- `type_into()` 逐字符 `dock.on_key(Key(ch, ch))`，走 `Input.on_key` → `app._on_input_changed`，真实触发补全浮层。
- G 组直接调 `app.agent.hooks["emit"]` 注入 `auto_retry_*`/`turn_*`/`error` 事件，数 transcript 行数差。
- 覆盖 9 组场景：A 冷启动帧（含「全屏找不到 /help/@Prism/placeholder」断言）、B /help 覆盖度与自吞语法、C 未知命令清单、D 补全浮层（键位提示缺失 + Enter 拒收 + 浮层残留）、E 自然语言双报错帧、F 用户输入方括号吞字/变黑（逐 cell）、G emit 事件覆盖率、H 主题/配置可发现性、I footer 状态。

核心取证模式（「用户看到什么 vs 系统知道什么」对照）：
```python
# /help 自吞参数语法: DESC 原文 vs 渲染结果
parse_markup("  /maxturns   最大轮数: /maxturns [n|none]  (默认 none=无限信任LLM)")
# → ['  /maxturns   最大轮数: /maxturns ', '  (默认 none=无限信任LLM)']  [n|none] 被当标签吃掉

# 用户消息变黑: 提交后逐 cell
buf.grid[9][10].style.fg  # → 0  即 (0,0,0)，压在 user_bg (52,53,65) 上 = 1.73:1

# Enter 拒收补全: 浮层选中 model, Enter 后
# transcript: '/mod — 未知指令。可用: …'   app._completion_active() → True (浮层残留)
```
