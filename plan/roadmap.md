# 实现路线

> 阶段 0–13 全 ✓(190 测试)。阶段 14(可变 base + 回退)脚手架在 `guard.py`,但**将被 RLM 方向(硬不可变 core)取代**,见 [rlm/route.md](rlm/route.md)。

### ✓ 阶段 0 · 骨架 + 本地内核 + REPL + function-calling loop
- [x] agent_loop.py(function calling + 事件流)/ model.py(chat_stream)/ @ 路由 / .env

### ✓ 阶段 1 · 对齐 pi agent 基线(语义 + prompt, 用户定)★

**详见 [docs/alignment-pi.md](../docs/alignment-pi.md)** —— 对齐审计(偏离项 + 增量映射)。

**语言鸿沟**: pi = TS SDK, prism = Python(IPython 核心)。"严格对齐" = 语义/行为/prompt 对齐, 非 SDK 复用。prism 是 pi agent 的 Python 增量实现。

**偏离修正(全部完成, test_alignment 验收)**:
- [x] D1 事件命名对齐 pi(message_update·delta / message_start / tool_execution_start/end)
- [x] D2 state 命名对齐(history→messages; 补 streaming_message/error_message)
- [x] D3 system prompt override/append 机制(_resolve_system_prompt / append_to_system_prompt)
- [x] D4 inject 区分 steer/followUp(PriorityQueue 优先级) + 显式 subscribe
- [x] D5 retry(auto_retry 事件) + thinking_level + compact()

**增量(建在 pi 基础上, 已审计)**: 多agent actor / patch五点 / workspace闭包 / guard护栏 / @路由+IPython / ext容错 / 能力分层 —— 详见 alignment-pi.md §3

**验收**: D1-D5 全对齐, 增量映射清晰

### ✓ 阶段 2 · textual TUI 套壳(原则 8 升级)
- [x] textual 全屏 TUI(transcript + dock, 抄 pi)
- [x] @ 路由挪进 TUI 输入(单行 @name → inject)
- [x] transcript can_focus=False(点击不抢 Input 焦点)
- [ ] **遗留**: theme 口子——namespace 未暴露 app 句柄, agent 够不到 self.theme(见 architecture.md Theme 节)
- [ ] **已取消**: 多 agent 输出分屏(用户定, 改单 transcript 汇入)
- [x] **验收**: TUI 跑, @main 对话, 流式输出

### ✓ 阶段 3 · actor 异步(原则 15)
- [x] Agent 线程 + inbox + inject
- [x] agent emit 跨线程到 TUI(call_from_thread)
- [x] **验收**: 主 agent run 不冻 TUI; inject 递条子 agent 处理(跨 agent inject 待阶段 7)

### ✓ 阶段 4 · 扩展点 patch(原则 11)
- [x] patch.py(PatchRegistry before/after/around + 异常降级)
- [x] agent_loop 五点 patchable(build_messages/stream_response/execute_tools/should_stop/emit)
- [x] Agent 持有 patches; TUI 显示 patch_error 降级
- [x] **验收**: around patch 包裹 execute_tools 改行为,不改 base(patches 缺省 no-op)

### ✓ 阶段 5 · 注册表 + 可变区(原则 12)
- [x] registry.py(Registry tool/prompt/skill + load_ext 容错) + default_registry 全局共享池
- [x] Agent 加 registry 参数, _extra_tools += registry.tools()
- [x] **集成闭环**: shell on_mount 调 `load_ext` + main agent 传 `default_registry` → ext/ tool 真正可用
- [x] **ext/ 实例**: `web_search`(Bing 搜索) + `code-review` skill
- [x] **验收**: ext/tools 丢 .py 已有 agent 能用;坏的跳过+emit

### ✓ 阶段 6 · 多 agent 工厂 + 工作区(原则 13/14)★
- [x] spawn.py(spawn 工厂 + make_file_tools 闭包绑 ws)
- [x] workspaces/<name>/ 独占分配(已存在报错)
- [x] 子 agent kind=sub 无裸 exec,工厂赋予工具; spawn(parent=) 注册进父 namespace
- [x] **验收**: bob 文件操作落 workspaces/bob/,不踩主 agent

### ✓ 阶段 7 · 多 agent 通讯(原则 16)
- [x] inject 跨 agent(actor 阶段 3 已有); spawn(parent) 让主 agent 命名空间持子 agent
- [x] 读 eventual(直接属性访问 last_result/messages)
- [x] **验收**: 主 inject bob 干活 bob 处理; 主读 bob.last_result; inject 立即返回

### ✓ 阶段 8 · 增量扩建自我修复 + 护栏(原则 2/7/10)
- [x] guard.py: 包装主 agent exec 的 open, 写 prism/ 核心 → 备份 + 放行
- [x] Agent.add_patch(point, fn, kind) / add_tool(tool): 运行时扩建正道
- [x] Agent.execute 用受限 builtins(open=guarded)
- [x] **验收**: add_patch 改 react 不改 agent_loop.py; 护栏放行 ext/ 备份 prism/

### ✓ 阶段 9 · 白盒 + 黑盒测试(用户定)
- [x] **白盒**: 单元测试覆盖率拉满(补 router/model/patch 接入点)
- [x] **黑盒**: 端到端集成(test_e2e: main→spawn→inject→workspace) + TUI Pilot(test_tui: 结构/焦点/不崩)
- [x] **验收**: pytest 全绿; e2e 跑通 main→spawn→inject→workspace 全链路

### ✓ 阶段 10 · 持久化 + 后端可插拔(原则 6/7)

> **落地**: `prism/memory.py`(MemoryBackend ABC + NullMemory + FileMemory); Agent 加 memory + dump()/启动 restore(run 后 auto-dump); shell 建 FileMemory('.prism/memory')。

- [x] **后端接口(原则7)**: MemoryBackend ABC(save/load/clear/keys) + NullMemory + FileMemory
- [x] **周期 dump**: agent.run 后 auto-dump messages
- [x] **强杀重启恢复**: Agent __init__ load(name) → messages 恢复
- [x] **NullMemory**: 默认能跑(开发/测试)
- [ ] **daemon**: DaemonRuntime(后台进程跨 TUI)——后续/开放问题
- [x] **验收**: 强杀重启恢复对话(test_memory: restore + cross_session); NullMemory 跑通

### ✓ 阶段 11 · 跨会话传递验证(复现原始痛点)
- [x] **复现种子**: "IPython 跨会话 agent 交互" —— test_cross_session_continuation
      - 场景A: 会话1 run+dump → 会话2 restore 记得历史
- [x] **验收**: 跨会话对话延续(test_memory)

### ✓ 阶段 12 · 运行时接通(theme 口子 + 子 agent 输出可见)

> **落地**: shell ThemeCtl(跨线程切主题) + namespace['theme']; make_subagent_emit(汇入主 transcript 带 [name]); /spawn 指令。

- [x] **theme 自举口子**: on_mount 暴露 ThemeCtl → agent 能 `theme.set(...)`
- [x] **子 agent emit 汇入**: make_subagent_emit 带 [name] 前缀
- [x] **spawn 便捷路径**: `/spawn` 自动接 emit + 注册 namespace
- [x] **验收**: theme 可切(test_runtime); /spawn 建子 agent(test_runtime monkeypatch)

### ✓ 阶段 13 · 结构化 system prompt(角色/指令/准则拆分)

> **设计动机**: 当前 `system_prompt` 是一整段字符串。拆成**结构化段**, 各段独立可组合/覆盖; `/goal` `/skill` 注入对应段, 对齐 pi 的 systemPrompt 可组合性。

**SystemPrompt 结构(prism/prompt.py)** —— 8 段:`role`/`environment`/`capabilities`/`instructions`/`guidelines`(默认,按 kind+tools)/ `goal`(`/goal`)/ `skills`(`/skill`)/ `extra`(兼容旧 append)。

**接口**: `render()`(markdown `## 段标题` 组合)/ `set_override`(整体替换,对齐 pi)/ `set_goal` / `add_skill` / `add_extra`。

- [x] SystemPrompt 类 + Agent 接入(`system_prompt` 改 property → `prompt.render()`)+ `/goal` `/skill` 进专属段
- [x] **验收**: 渲染含 `## 角色` `## 指令` 等标题; `/goal` 进 goal 段; override 整体替换生效

### 阶段 14 · 可变 base + 自动回退 + /revert(agent 自我演进) ★将被 RLM 取代

> ⚠️ **此阶段方向被 9 轮 werden 推翻**: core 将回归**硬不可变**(原则 10 修正,见 [principles.md](principles.md) §原则 10)。
> 当前 `guard.py` 已有 verify_and_revert/revert_latest/list_backups 脚手架,但 PLAN 未勾完。
> **下一步不是补完阶段 14,而是按 [rlm/route.md](rlm/route.md) 把 core 钉成硬不可变**(删除对 prism/ core 的放行,只允许 ext/ 可写)。

- [ ] guard 退役拦写 → 备份+放行(现状脚手架)
- [ ] 自动回退(reload sanity)+ /revert 第一公民指令
- [ ] **验收**(若仍要做): agent 改 prism/agent.py → 改坏 reload 失败 → 自动回退; /revert 列/回退
