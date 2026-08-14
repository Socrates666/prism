# 批判轮6：一致性与极端情形（评审人：终端 QA / 一致性与鲁棒性评审专家）

评审视角：终端 resize 行为（布局重算 / 缓冲残留 / 光标 / 滚动位置保位 / 最小尺寸）、渲染循环一致性（脏区 / diff flush / 内存增长 / 刷新率）、竞态与异步（流式 delta 与按键并发 / 事件泵 / agent 崩溃后状态机 / 中断后半成品）、终端状态卫生（崩溃退出 raw mode / 光标 / alt screen / 窗口标题恢复）、跨平台（Windows/POSIX escape / SIGWINCH / 颜色探测）、一致性（信息双源 / 命名 / 格式）、数字与边界（0 项 / 空 / 超长单行 / 负数 / None 尺寸）。

方法：通读 `prism/tui/{app,buffer,terminal,widgets,widget,markup,css}.py`、`prism/shell.py`、`prism/agent.py`、`prism/agent_loop.py`。写无头取证脚本（附录，放系统临时目录，**绝不放进项目**，不跑交互主循环、不开 raw mode），实例化 `PrismApp().run(headless=True)`（dummy key，零网络）拿到真实 `emit` 闭包，按 `tests/test_tui.py` 手法直接驱动 `emit` / `_render_frame` / `Buffer` / `render_diff`，在极端尺寸矩阵、resize 前后、crash 路径下断言状态。所有脚本输出均为真实取证，非脑补。

共 **9 条**问题。分布：**P0 ×1，P1 ×4，P2 ×4**。

> 不重复轮1–5（共 54 条）。与本视角有交集者只用新证据深化：
> - 轮5 P0「无 key 崩栈」与本轮「agent crash 卡 busy」**根因不同**（轮5 是 on_mount 构造期崩、本轮是运行期 agent 线程崩后状态机不归位），且本轮补「status 线程泄漏 + pending tool 冻结 + 主循环永久刷帧」三条新症状。
> - 轮2「Esc 中断」依赖 `_agent_busy` 判断 —— 本轮证明这个 `_agent_busy` 在**并发 agent** 和 **crash** 下本身就是不可靠的（双源/多写者），是轮2 没碰过的状态一致性根因。
> - 轮3「page_bg 从不绘制」是色彩问题；本轮「render_diff 不清屏 / 不处理行数变化」是**渲染管线鲁棒性**问题，路径不同。

---

## 发现的问题

### [P0] agent 运行期异常后 UI 状态机永久卡 busy：spinner 永转、Esc 中断失灵、pending 工具块冻结，唯一出路是重启

- 证据：
  - `prism/agent_loop.py:82` `_emit({"type": "agent_start"})` 与 `:188` `_emit({"type": "agent_end"})` 之间**整个 loop 体没有 try/finally**。重试耗尽时 `agent_loop.py:121` 直接 `raise`（网络/密钥/限流超时 —— 这是任何 LLM agent 的**头号故障路径**），`raise` 一路传出 `run_agent_loop`，`:188` 的 `agent_end` **永远不可达**。
  - `prism/agent.py:303-312` `_actor_loop` 用 `try/except` 兜住，但只 `emit({"type":"error",...})`，**不补发 agent_end**：
    ```python
    except Exception as e:
        self.emit({"type": "error", "error": f"{type(e).__name__}: {e}"})
    ```
  - `prism/shell.py:195-200` 只有 `agent_end`/`steer_interrupt` 两个事件会 `_agent_busy=False` + `_stop_status()`；`shell.py:236-239` 的 `error` 分支**只** `flush_current()` + 写一行红字，**不碰** `_agent_busy`，**不调** `_stop_status()`。
  - 取证（直接驱动真实 `emit`：先 `agent_start`，再 `error`，不补 `agent_end`）：
    ```
    busy_before = False
    busy_after_agent_start = True
    alive_nonmain_threads_after_start = 5   (4× _actor_loop + 1× _status_loop)
    busy_after_error(NO agent_end) = True    ← 永久 True
    alive_nonmain_threads_after_error = 5   ← _status_loop 线程仍在跑
    >>> busy 卡 True?  True
    >>> status 动画线程仍在跑?  True
    ```
  - 连锁后果（均经代码路径 + 取证确认）：
    1. `app.py:182` 主循环 `if self._agent_busy and now - last_render > 0.12: self._dirty = True` —— busy 卡 True 导致**即使无任何输入/输出，主循环也每 0.12s 强制全量刷一帧**，CPU 持续占用、终端持续重绘。
    2. `shell.py:42` Esc 中断判断 `if event.key == "escape" and self._agent_busy` —— busy 卡 True 意味着 agent **其实已经死了**，但用户按 Esc 仍会调 `agent.stop()`（对一个已结束的 run 设 abort，无效），用户以为「中断了」，其实 agent 早崩了，只是错误信息被埋在滚动历史里。
    3. `_status_loop`（shell.py:150-159）线程泄漏：`_stop_status` 只在 agent_end 调，crash 不调，线程每 0.4s 永久 `call_from_thread(status.update, "◇ Refracting...")`，即「折射中…」动画对一个已经死掉的 agent **永远转下去**。
- 为什么伤害核心可靠性：网络抖动 / 401 / 限流 / 超时是 coding agent **每天都会遇到**的故障，不是边界。一旦命中（且 `max_retries` 用尽，`agent_loop.py:121` raise），UI 进入「假活」状态：spinner 照转（像在干活）、Esc 无效（像卡死）、错误只有历史里一行红字（像坏了）。用户分不清「还在跑 / 重试中 / 已经死了」，且**无任何自愈**——只能双击 Ctrl+C 退出整个会话（轮2 已证 Ctrl+C 在有文本时是清空输入、空输入双击才退出），丢失全部上下文。这是把「最常见故障」直接变成「不可恢复死锁」。
- 具体改进建议（精确到函数）：
  1. `agent_loop.py:82-188` 用 `try/finally` 包住 loop 体，`finally: _emit({"type":"agent_end"})`（或新增 `agent_crashed` 事件），保证任何 raise 都归位。这是根因修复。
  2. `shell.py:236` 的 `error` 分支兜底：`app._agent_busy = False; _stop_status()`，并清理 `pending_tool[0]`（见下条）。即便 agent_loop 修了，UI 层也应有「error 即终止回合」的防御。
  3. `agent.py:311` `_actor_loop` 的 except 里补发 `self.emit({"type":"agent_end"})`（或专门的 `agent_crashed`），双保险。

---

### [P1] 主/子 agent 共用一个裸 `_agent_busy` bool，被多个线程直接写：并发时子 agent 结束会把「仍在跑的主 agent」抹成 idle

- 证据：
  - `_agent_busy` 是 `App` 上的一个普通属性（`app.py:87`），**没有引用计数、没有锁**。两处 emit 都直接写它：
    - 主 emit `shell.py:196` `app._agent_busy = True` / `:199` `app._agent_busy = False`。
    - 子 agent emit `make_subagent_emit`（`shell.py:394` `app._agent_busy = True` / `:396` `app._agent_busy = False`）。
  - 且这些写发生在 **agent 线程**里（emit 从 agent 线程调用），而读发生在**主循环线程**（`app.py:182`、`shell.py:42` Esc 判断、`widgets.py:487` Footer spinner）。跨线程裸读写一个 bool（CPython 靠 GIL 不至于撕裂，但**语义上是无协调的多写者单读者**，典型的状态双源/竞态气味）。
  - 取证（主 emit + 子 emit 交错）：
    ```
    busy_before = False
    after main agent_start: busy = True
    after sub  agent_start: busy = True
    after sub  agent_end  : busy = False   (主 agent 仍在跑!)
    >>> 单 bool 被子 agent_end 抹成 False, 主 agent 还在跑
    after main agent_end : busy = False
    ```
  - `spawn`（`prism/spawn.py` 存在，且 `/spawn` 是已上线指令，见轮5 /help 清单）意味着主+子并发是**设计内的真实场景**，不是假设。
- 为什么伤害一致性/可靠性：子 agent 先返回（极常见：子 agent 跑一个快任务）→ `_agent_busy=False` → 主循环停止强制刷帧（`app.py:182`）→ 主 agent 的流式 spinner **提前熄灭**，用户以为「全做完了」其实主 agent 还在跑；同时 Esc 中断判断（`shell.py:42`）因 `_agent_busy=False` 而**对仍在运行的主 agent 失效**——用户按 Esc 没反应，因为 UI 认为「没人在忙」。反过来若主先结束、子还在跑，busy 也被抹 False。状态机与真实并发完全脱钩。
- 具体改进建议：
  - 把 `_agent_busy` 从 bool 改成**引用计数 / 活跃 agent 集合**：`self._active_agents: set` 或 `self._busy_depth: int`。`agent_start` → `depth+=1`，`agent_end`/`error` → `depth-=1`，`_agent_busy = depth > 0`。
  - 所有跨线程写都走 `call_from_thread`（与 `log.write` 同款，shell.py 已有该机制），消除裸跨线程属性写。
  - Footer spinner / Esc 判断 / 主循环刷帧 三处都读这个派生属性，改成读 `self.is_busy`（property）。

---

### [P1] transcript（`RichLog.entries` + `_units`）单调膨胀，零上限、零回收——长会话内存只增不减

- 证据：
  - `prism/tui/widgets.py:64` `self.entries: list = []`，`:88-91` `write()`、`:96-100` `user()`、`:103-109` `tool_start()`、`:120-133` `thinking/cognitive` **全部只 append，从不 trim**；`clear()`（`:93`）是全清（用户手动），不是回收。
  - 没有 `max_entries` / 环形缓冲 / LRU：取证 `hasattr(rl, "max_entries")=False`、`hasattr(rl, "_cap")=False`。
  - `_units`（`widgets.py:68`，按宽度缓存的可视行）同样无界，且每次宽度变化**整体重建**（见下条）。
  - 取证（喂 20000 条）：
    ```
    appended 20000 entries in 0.046s; len(entries) = 20000
    has max_entries / _cap?  False  False
    len(_units) = 20000
    approx payload chars stored in entries ~ 1508890   (仅文本, 未含 Style/Cell 对象开销)
    ```
  - 每条 entry 还会派生 `_LineUnit`/`_BlockUnit`，每个 unit 持有 `parse_markup` 出来的 `(str, Style)` 列表——一个长会话（几千轮、每轮带代码块/工具输出）轻易数十万对象，`entries` + `_units` 双份持有。
- 为什么伤害可靠性：coding agent 会话动辄数小时、上百轮、每轮含长代码/工具输出（`Read` 整文件、`grep` 海量结果）。内存只增不减意味着：跑得越久越胖，最终在受限环境（容器、CI、低配机）触发 OOM 或 swap 抖动；且因为 `_units` 也在膨胀，每次 resize 的代价随会话长度线性恶化（见下条 P1 perf）。这是「能用，但越用越慢越胖」的慢性病。
- 具体改进建议：
  - `RichLog` 加 `max_entries`（如 2000），`write`/`append` 时若超限**从头部丢弃**（`entries.pop(0)` 或用 `collections.deque(maxlen=...)`），同步丢弃对应 `_units` 并 clamp `_top`。
  - `_units` 与 `entries` 解耦生命周期：只对「视口附近 ±N」的 unit 物化，远离视口的按需重建（窗口化），避免双份全量持有。
  - 至少给 `RichLog` 一个 `trim(keep_last=N)` 并在 `message_end` / `turn_end` 后惰性调用。

---

### [P1] resize 时滚动位置漂移：`_follow=False`（用户向上滚读历史）时 `_top` 是 unit 索引，折行重排后指向完全不同的内容

- 证据：
  - `prism/tui/widgets.py:145-162` `_ensure_units(iw)`：宽度变化即 `_cache_iw != iw` → **整体重新 `wrap_segments`**，`_units` 列表长度与每个 unit 的内容都随宽度变。
  - `widgets.py:193-207` `draw`：`_follow=False` 时 `start = max(0, min(self._top, total))`——`_top` 是一个**纯 unit 索引**，resize 后不重算。`scroll_up`（`:171-175`）只改 `_top`/`_follow`，不记录「我滚到了哪条逻辑内容」。
  - run 主循环 resize 时只 `prev=None` + `_dirty=True`（`app.py:170/179`），**不通知 RichLog 重定位滚动锚点**。
  - 取证（短行 + 一条长行，80 宽长行=1 unit、40 宽折成 ~3 unit）：
    ```
    units @80w = 7   units @40w = 9
    _top=3 @80w 顶行: SHORT-B
    _top=3 @40w 顶行: ONG LONG LONG LONG LONG LONG L   ← 同一 _top=3, 内容从 SHORT-B 跳成长行折断碎片
    ```
    用户原本盯着 `SHORT-B` 读，拖一下窗口宽度，视口顶行突变成一截 `ONG LONG…`（长行被劈开的中间段），阅读连续性断裂。
- 为什么伤害一致性：终端用户**频繁** resize（拖窗口、分屏、tmux 缩放）。向上滚读历史更是高频（轮2/轮4 都证过滚动体验差）。二者叠加时，用户正在精读的那段内容会随每次列变化**不可预测地跳走**，且没有任何「回到原来那行」的机制（没有书签、没有 unread 指示）。对一个以「回滚历史复盘」为核心价值的 coding agent，滚动锚点不稳等于历史不可信。
- 具体改进建议：
  - 把滚动锚点从「unit 索引」改为「逻辑内容锚」：`scroll_up` 时记录当前视口顶对应的 `entry` 索引 + 该 entry 内的行偏移；resize 后按锚重定位（`_top = locate(anchor_entry, anchor_offset)`）。
  - 或至少在 `_follow=False` 且宽度变化时，尝试保持「视口顶第一条 entry 的第一行」可见（按 entry id 而非 unit 序号定位）。
  - 退一步：宽度变化时若无法精确保位，给一个 `[dim]布局已重排[/dim]` 提示，别让用户以为是自己眼花。

---

### [P1] 每次列变化都全量 re-wrap 整个 transcript（O(总字符数)），长会话 resize 卡顿达数百毫秒

- 证据：
  - `prism/tui/widgets.py:146-162` `_ensure_units`：`if iw != self._cache_iw:` → 遍历**全部** `self.entries`，对每条 `parse_markup` + `wrap_segments` 重建 `_units`。没有任何增量/缓存/惰性。
  - 取证（2000 条中等长度 entry，resize 触发一次全量 re-wrap）：
    ```
    resize 120->60 on 2000 entries: re-wrap took 326.5 ms
    resize 60->120 on 2000 entries: re-wrap took 325.4 ms
    ```
    单次 resize 阻塞主线程 ~0.33s（且这只是 2000 条；与上条内存增长叠加，长会话下会更长）。Windows 拖拽 resize 会连续触发数十次 size 变化（每次 `term.size()` 取回新值，`app.py:176` 判不同即 `_dirty` + `prev=None`，下一帧 `_render_frame` → `RichLog.draw` → `_ensure_units` 全量重排）。
- 为什么伤害一致性/体验：0.33s 的主线程阻塞 = 整个 TUI（按键、流式输出、spinner）冻结 0.33s。拖拽窗口时连续触发 → 肉眼可见的卡顿掉帧、输入响应延迟。会话越长越卡，形成「越用越卡」的负反馈。一个号称「流畅自绘」的 TUI 在 resize 上卡成幻灯片，与「类 pi 一流体验」的定位矛盾。
- 具体改进建议：
  - `_ensure_units` 改**惰性 + 增量**：只物化视口需要的 unit（`_bottom_start`/`_top` 附近 ±一屏），远离视口的 entry 不 re-wrap；滚动到时再按需展开。
  - 对 resize 做**节流/去抖**（debounce ~50ms）：连续 size 变化只在停止后 re-wrap 一次（`app.py:175-179` 现在每帧都判，可加 `_resize_timer`）。
  - 缓存「每个 entry 在若干离散宽度档位下的 wrap 结果」（如每 8 列一档），resize 命中相邻档位直接复用。

---

### [P2] `render_diff` 不处理行数变化、从不清屏（无 `\x1b[2J`/`\x1b[J`）：契约脆弱，是潜在的残留/错位隐患

- 证据：
  - `prism/tui/buffer.py:163-173` `render_diff(prev, cur)`：只 `for y in range(cur.rows)`，`prow = prev.grid[y] if prev and y < prev.rows else None`。**若 `prev.rows > cur.rows`（终端缩高），prev 多出的行既不在循环范围、也不发任何清屏序列**——它们原样留在屏幕上。
  - 全程无 `\x1b[2J`（清屏）也无 `\x1b[J`（清到屏末）：取证 `render_diff(prev_30rows, cur_24rows)` 的输出，`含全屏清屏? False`、`含清到屏末? False`，`max row touched = 24`（prev 的 25–30 行 OLDROW 完全没被覆盖）。
  - 即便是「首帧」路径 `render_diff(None, cur)`：取证 `rows touched=[1..24]`、`has_2J=False`——**首帧也只逐行重画、从不清屏**，依赖 alt screen 本身是干净的。一旦 alt buffer 被复用（同终端连续两次 prism、或终端未正确进入 alt screen），残留会透出。
  - 当前 run 主循环靠 resize 时 `prev=None`（`app.py:170/179`）+ 单线程同步保证 prev/cur 同尺寸，**绕过**了行数不一致；但 `render_diff` 是 `__init__.py` 导出的公开函数（`from .buffer import render_diff`），其隐式契约「prev 与 cur 必须同 rows 同 cols」没有任何断言/防御，任何外部调用者或未来重构一旦传入不同尺寸即静默错位。
- 为什么伤害鲁棒性：这不是「现在必现」的 bug，而是「渲染管线的脆弱契约 + 零防御」。diff 渲染器天然要面对尺寸变化（这正是 resize 的定义），而它对「行变少」「列变少」都无能为力又不报错。一旦上游任何一处忘了 `prev=None`（例如未来给 overlay / 多面板加局部 diff），残留就会直接漏到屏幕上。
- 具体改进建议：
  - `render_diff`（buffer.py:163）开头：若 `prev is None or prev.rows != cur.rows or prev.cols != cur.cols`，先发 `\x1b[2J\x1b[H`（全清 + 回原点）再逐行画，作为「尺寸变化即全量」的硬保证。
  - 或在缩高时对 `y in range(cur.rows, prev.rows)` 发 `\x1b[{y+1};1H\x1b[2K`（逐行清）。
  - 至少给函数加 `assert prev is None or (prev.rows==cur.rows and prev.cols==cur.cols)`，把隐式契约变显式。

---

### [P2] 宽字符被窄字符覆盖后留下「孤儿 cont cell」：Input 光标反相、重绘时会半隐半现

- 证据：
  - `prism/tui/buffer.py:32-48` `put`：写宽字符时把 `x+1` 标 `cont=True`；但**写窄字符覆盖某一格时，不会清理相邻格可能残留的 cont**。
  - 取证（`Buffer(3,1)`，先 put 宽字符 `中`@x=0 占 x=0,1，再 put 窄 `X`@x=0 覆盖左半）：
    ```
    覆盖宽字符左半(中->X@x=0): cells=['X','',' '] cont=[False,True,False]
    ```
    x=1 仍是 `cont=True, ch=''` 的孤儿。`_row_to_ansi`（buffer.py:142-144）遇 cont 直接 `continue` 跳过 → 该格渲染为空。结果：原本的 `中` 被替换成 `X` + 一个**幽灵空格**，后续整行视觉列号与逻辑列号错位。
  - 贴边退格分支（buffer.py:44-48）注释自承缺陷：`# 理论上还需标记 x-2, 但贴边情况罕见, 容忍`。
  - 真实触发路径：`Input.draw` 的光标反相（`widgets.py:461-463`）`buf.put(cx_screen, cy, ch, Style(fg=..,bg=..))` 单格覆盖——若光标停在某个宽字符（CJK）的左半，该宽字符右半的 cont 变孤儿，光标块旁边出现半个消失的字符。取证（`put(2,0,'中')` 贴边退格）：`cells=[' ','中',' ']`（退到 x=1，x=2 留空）。
- 为什么伤害一致性：CJK 是本产品主语言（文案、阶段标签、用户输入全是中文）。光标在中文输入上移动/闪烁时半隐半现、宽字符覆盖后留下幽灵空格，会让用户觉得「字符被吃了一半」。在精确的 cell-grid 渲染模型里，cont 孤儿是经典的对齐错位源头。
- 具体改进建议：
  - `Buffer.put`（buffer.py:39）写入新 cell 前，**清理目标格及其可能影响的邻居**：若新字符是窄字符（w==1）且目标格的左邻是某宽字符的左半（`grid[y][x-1].ch` 宽且 `grid[y][x].cont`），清掉左邻的宽字符（或重置其 cont）；若新字符是宽字符且会覆盖到下一格已是非 cont 的内容，先清下一格。
  - 更稳妥：`put` 写 (x,y) 时，若 `grid[y][x]` 原本是个宽字符的左半（`not cont and char_width(ch)==2`），把 `x+1` 复位为 `_blank()`；若原本是 cont，把 `x-1` 复位。即「覆盖时连带清掉被破坏的宽字符配对」。

---

### [P2] 无最小尺寸守护：`cols<3` 或行高过小时 Input 边框（`box` 需 w≥2）静默消失，用户看不到输入框

- 证据：
  - `prism/tui/buffer.py:97` `box`：`if w < 2 or h < 2: return`——宽度 <2 直接不画边框。
  - `prism/tui/widgets.py:433` `Input.draw` 调 `buf.box(x,y,w,h)`，`w<2` 时边框整体不画；`widgets.py:434` `ix=x+1, iw=max(1,w-2)`，`cols` 极小时文本写入全部越界裁剪。
  - 取证（极端尺寸矩阵，均不崩，但 Input 边框不可见）：
    ```
    rows= 1 cols= 80 -> OK, drawn_chars=78, input_border_visible=False
    rows= 0 cols= 80 -> Buffer(80x1) OK, input_border_visible=False
    rows=24 cols=  0 -> Buffer(1x24) OK, drawn_chars=0, input_border_visible=False
    rows=24 cols=  1 -> drawn_chars=0, input_border_visible=False
    rows=-1 cols= -1 -> Buffer(1x1) OK, drawn_chars=0   ← 负数也被 max(1,..) 吃掉
    rows= 3 cols=  3 -> drawn_chars=2, input_border_visible=False
    ```
  - 不崩是好事（`Buffer.__init__` `max(1,cols)`/`max(1,rows)` 兜底，`put` 越界静默裁剪，`layout` 对 auto widget 抛异常降级为 1，`widget.py:67-68`），但**没有任何最小尺寸提示**：用户把终端缩到 1 行 / 极窄，看到的是一片空白或半截 Header，输入框无声蒸发，不知道「窗口太小」。
- 为什么伤害一致性/体验：分屏把终端压到很窄、tmux 缩放、手机端 SSH 是真实场景。「不崩」是底线，但「静默退化成空屏」让用户以为程序卡死。同类 TUI 在过小尺寸下会画一行 `[terminal too small]` 提示。
- 具体改进建议：
  - `App.run`（app.py:153）或 `_render_frame`（app.py:287）开头判断最小尺寸（如 `cols < 20 or rows < 8`）：若是，`buf` 只画一行居中的 `[dim]终端过小 (需 ≥20×8, 当前 {cols}×{rows})[/dim]`，跳过正常布局。
  - `Buffer.__init__`（buffer.py:25）对 `cols<=0 or rows<=0` 至少 `log/warn`，别静默吞掉（负数变 1×1 是「假装正常」）。

---

### [P2] 终端状态卫生两处缺口：POSIX `_old_term` 依赖后台线程才赋值（退出竞态）；`on_mount` 在 `with Terminal()` 之前且无 try/except

- 证据：
  - **POSIX 恢复竞态**：`prism/tui/terminal.py:241` `self._old_term = termios.tcgetattr(0)` 只在 `_read_loop_posix`（**后台 daemon 线程**，`terminal.py:136-137` 启动）内部赋值，`__enter__`（`:130-138`）**不赋值**。`_teardown_posix`（`:230-236`）靠 `if hasattr(self, "_old_term")` 判断是否恢复。取证：`Terminal()` 实例化后 `hasattr(_old_term)? False`。
    - 竞态窗口：若 `__exit__` 在输入线程执行到 `tcgetattr` 之前被调用（快速退出 / 主线程异常 / `_quit` 立即置位），`hasattr=False` → `tcsetattr` 不执行 → **终端永久卡在 cbreak（无回车、无 echo）**，用户回到 shell 后敲字全乱。
    - 即便 `hasattr=True`，异常分支把 `_old_term=None`（`:244`），`tcsetattr(0, TCSADRAIN, None)` 会 `TypeError`，被 `except: pass`（`:235`）吞掉 → 同样不恢复。
  - **on_mount 无防护且在 Terminal 之前**：`app.py:153-159` 顺序为 `_build() → on_mount() → (headless? return) → with Terminal()`。`on_mount`（shell.py:131-293）里做大量易失败操作（`restore_agents` 建 `OpenAIModel`、`load_ext` 读 cwd、`SQLiteForest(".prism/forest.db")` 开 SQLite、`load_commands` 读 ext/）。任一抛错（无 key / ext 目录缺失 / `.prism` 无写权限 / forest.db 锁）→ 异常**裸传顶层**，`run()` 对 `on_mount` 零 try/except，连「TUI 起不来给个降级画面」的机会都没有（轮5 P0 已证无 key 崩栈，这里补「任何 on_mount 异常都同款裸崩，且发生在进终端之前所以连 alt screen 都没进，错误直接糊在用户当前 shell 里」）。
- 为什么伤害可靠性：终端卡 cbreak 是**会毁掉用户整个 shell 会话**的灾难性后果（轮5 P0 的崩栈至少不破坏终端状态；cbreak 残留会让用户以为「键盘坏了」）。on_mount 的脆弱让「加载 ext 失败 / forest.db 权限」这类与核心逻辑无关的环境问题直接表现为程序崩溃。
- 具体改进建议：
  - POSIX 恢复不依赖线程：在 `__enter__`（terminal.py:131，POSIX 分支）**主线程里**先 `tcgetattr` 存 `_old_term` 再 `setcbreak`，再启线程读输入；`__exit__` 永远能恢复。当前把状态保存塞进线程是反模式。
  - `_teardown_posix`（terminal.py:233）判断改成 `if getattr(self, "_old_term", None):`（None 也跳过），并在恢复失败时 `print('\x1b[?25h')` + 写 stderr 一行「终端恢复失败」让用户知情。
  - `run()`（app.py:156）给 `on_mount` 包 `try/except`：失败时进一个降级 TUI（transcript 写错误 + 修复建议），或至少 `print` 友好提示后 `sys.exit(2)`，别让裸栈糊在用户 shell 里（与轮5 P0 的入口自检建议互补）。
  - 顺手：`Terminal.__enter__`（terminal.py:135）当前只发 `\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H`，`__exit__`（`:153`）发 `\x1b[?25h\x1b[?1049l`——**配对正确**（alt screen 进/出、光标隐/显），这点是好的；但 `App.TITLE`（app.py:67 / shell.py:24 `"Prism"`）定义了却**从未**用 `\x1b]0;...\x07` 设置窗口标题，也无恢复——属于「定义即死配置」（与轮3 死 token 同类），建议要么用上、要么删掉别留误导。

---

## 本轮取证脚本（附录）

主脚本写在系统临时目录（**未放入项目**）：`C:/Users/cty18/AppData/Local/Temp/prism_edge_forensics.py`，完整输出：`C:/Users/cty18/AppData/Local/Temp/prism_edge_evidence.txt`。resize 滚动漂移另跑了一段聚焦脚本（同目录内联）。

要点（全程无头、不开 raw mode、不跑交互主循环）：
- `mount()` = `PrismApp().run(headless=True)`（`OPENAI_API_KEY=sk-dummy` 仅过 `OpenAI()` 构造，零网络），拿到真实 `emit` 闭包（`app.agent.hooks["emit"]`）与 `make_subagent_emit`。
- **T1/T2/T8（状态机）**：直接驱动 `emit({"type":"agent_start"/"error"/"agent_end"})` + `_drain()`，断言 `_agent_busy`、`threading.enumerate()` 存活线程、`pending_tool` block 的 `bg`。
- **T3（内存）**：`RichLog.write` × 20000，断言 `len(entries)`、无 `max_entries`、`len(_units)`、payload 字符数。
- **T4（滚动漂移）**：手工喂短行+长行，`scroll_home`/手设 `_follow=False,_top=3`，切宽度后 `render_plain(_render_frame)` 取视口顶行，证明同一 `_top` 在 80w/40w 指向不同内容。
- **T5（perf）**：2000 entry，`time.time()` 包 `_render_frame` 的 resize 重排，量到 326ms。
- **T6（极端尺寸）**：`(rows,cols) ∈ {(1,80),(0,80),(24,0),(24,1),(-1,-1),(1,1),(3,3)}`，断言不崩 + `input_border_visible`。
- **T7（diff）**：构造 `Buffer(20,30)` vs `Buffer(20,24)`，正则提取 `render_diff` 输出里的 `\x1b[y;1H` 行号、查 `\x1b[2J`/`\x1b[J`。
- **T9（宽字符）**：`Buffer(3,1)` 先 put 宽字符再 put 窄字符覆盖，逐 cell dump `ch`/`cont`。

核心取证模式（crash 卡 busy + 滚动漂移）：
```python
# T1: agent 崩后 _agent_busy 不归位 (agent_loop.py:188 不可达, shell.py error 分支不重置)
emit({"type":"agent_start"}); app._drain()      # busy=True, 起 _status_loop 线程
emit({"type":"error","error":"boom"}); app._drain()
assert app._agent_busy is True                   # 永久 True
assert any(t.name=="_status_loop" for t in threading.enumerate() if t.is_alive())  # 线程泄漏

# T4: 同一 _top, resize 后指向不同内容
rl._follow=False; rl._top=3
# @80w: SHORT-B     @40w: 'ONG LONG LONG...' (折断碎片)  → 滚动锚点漂移
```
