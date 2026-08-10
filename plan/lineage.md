# 演进谱系:维度 / 试错 / prime-agent 翻译

## 被照亮的维度(按诘问出现顺序)

| # | 维度 | 来源 |
|---|------|------|
| 1-13 | (调用范式/路线/输入授权/护栏/状态器官/daemon/灵活/持久化/无中断/daemon可插拔/后端可插拔/前端REPL/显示自举) | 前期诘问 |
| 14 | 【自我修复=扩建】增量不覆盖 | 用户深化 |
| 15 | 【扩展点 patch】before/after/around | 用户定 |
| 16 | 【可变区=人格插件】全局共享非单例 | 用户定 |
| 17 | 【主/子能力分层】主完整IPython / 子工厂受限无裸exec | 多agent诘问 |
| 18 | 【工作区分层】主=根cwd / 子=workspaces独占 + 文件工具闭包 | 用户定 |
| 19 | 【actor 并发】每agent线程+inbox+inject,绕开asyncio exec阻塞 | 多agent诘问 |
| 20 | 【通讯分层】读eventual直接访问 / 写inbox触发 | 用户定 |

> RLM 认知层另逼出 9 个维度,见 [seed.md](seed.md#9-轮-werden-关键结论速查)。

---

## 关键决策与被否定的押注(试错记录)

1-12. (前期:demo否/范围/路线/deepagents/远程/备份/分支/daemon/mem0/TUI/显示 — 见前版)
13. 核心只读 → 否:增量扩建(绕开 reload 冲突)
14. 覆盖+reload → 否:增量+注册表
15. 自我修复=改代码 → 修正:=扩建
16. 单例可变区 → 否:全局共享非单例
17. **exec to_thread(推共享池)** → 否:exec 跟 agent 循环一体
18. **await b.chat(直接对象调用)** → 否:进入对方执行;改为 inject 消息(递条子)
19. **共享命名空间 + 各自工作区 cwd** → 矛盾(cwd 进程级);改为**工作区分层 + 文件工具闭包**(绕开 cwd)
20. **子 agent 享完整 IPython** → 否:子 agent 工厂受限(无裸 exec),只有赋予的工具 → 隔离/安全

> RLM 试错(被否押注):
> - 「思维树 + 上下文树」两棵树 → 否:一树多边(权衡两树权重是伪问题)
> - 「树是 ext/ 人格插件」 → 否:树是 loop 同级基础设施(Forest 进 core,树实例是 data)
> - 「树是被动上下文仓库」 → 否:树是主动推理搜索树(失败回溯)
> - 「直觉 = 改树,每次 loop」 → 否:直觉 = READ(选/排/临时压),改树 = WRITE(剪枝,结构触发)
> - 「搜索树回溯 = 自指递归」 → 否:搜索是 causes 轴;自指是 based_on 轴(一树两轴)

---

## prime-agent 翻译 / 借鉴记录

**源**: `PrimeIntellect-ai/prime-agent` `packages/agent/src/agent-loop.ts`

**借鉴 → prism**: function calling / 双层 while / streamResponse(delta) / executeToolCalls / EventStream / AbortSignal → `agent_loop.py`(function-calling + 事件流 + 流式)。砍 compaction/steering/parallel(后续)。

**textual TUI 抄 pi**(packages/tui): 全屏 alternate-screen + transcript(滚动对话区) + dock(底部输入) 布局(fullscreen.ts)。textual 抄: `App`+`RichLog`(transcript)+`Input`(dock); 组件 Box→Container / Input→Input / Markdown→Markdown。~~多 agent 输出分屏~~ **已取消(用户定)**: 只用单 transcript, 子 agent 输出汇入主视图(带 [name] 前缀), 不开多面板。

**prism 独有(超 prime)**:
- 主 agent 完整 IPython + 共享命名空间(prime 子 agent 独立 session,不共享)
- **子 agent 工厂受限**(prime 子 agent 也是完整 session,prism 子 agent 无裸 exec + 工厂赋予工具)
- 扩展点 patch(改 react 逻辑,prime 的 supplemental 只改 prompt/memory)
- 工作区分层 + 文件工具闭包(prime 靠独立 sessionDir)
- 输入即授权 / @ 路由 / 增量扩建

**关键差异**: prime 子 agent = 独立 session(隔离,无 race,放弃共享);prism 子 agent = 工厂受限(共享命名空间魅力留给主 agent + 用户,子 agent 受控隔离)。prism 的"共享命名空间"是 prime 放弃的路。

**复刻踩坑**: input_transformers_post 传 list / tool_calls 缺 type / run() Out[] 重复。
