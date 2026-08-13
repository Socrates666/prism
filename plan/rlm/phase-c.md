# Phase C 实施计划 · 小模型 Intuition + forcing

> 承接 [route.md](route.md) Phase C。**rebase 已取消**(用户)。**反思 = C3 forcing**(用户确认)。
> 现状: A/B 已实装; Intuition 是 HeuristicIntuition(启发式无模型); reflect 工具有(手动); forcing 未实装。

## 目标

把 HeuristicIntuition(启发式) 升级为 **SmallModelIntuition**(驻场小模型 `glm-4.5-air` 读树拼 search-state), 并实装 **C3 forcing**(search-state 浮现 failed/pattern + 撞墙逼 reflect)。

默认 **α**(route.md): 小模型当导航员(拼 search-state, READ 不写树), 主模型控搜索/回溯/reflect。

## 拆步

- **[C1] SmallModelIntuition**(`cog_intuition.py` 新类, 保留 Heuristic 作降级):
  读最新树的 thought/failed/reflection → 调小模型拼 search-state(frontier 思路 + 别重复的失败 + 可用反思) → `[system]` msg 注 prompt。白盒 emit `cognitive/intuition`。
- **[C2] 性能**(cycle.md `_context_sufficient` + `active_context`):
  `_tree_signature()`(树 id + 节点数 + 末节点 id)检测新认知事件; 签名不变 → 复用缓存, 不重调小模型(同轮连续工具调用只跑一次)。
- **[C3] forcing**(cycle.md a+c 混合):
  - (a) search-state **浮现 failed 兄弟 + 自指 pattern**(小模型 prompt 引导: "你在这类地方总犯 X")
  - (b) agent_loop 检测**连续失败**(撞墙) → 结构要求 reflect 一步(逼反思, 不留 dead-end)
- **[C4] 延迟账实测 + 降级**(scribe.md 硬门槛):
  小模型推理 < 300ms 且省 token 才净赚; 异常/超时 → 退 HeuristicIntuition 启发式(降级安全阀, 不崩)。

## 验收

- SmallModelIntuition.select_context 返回 search-state system msg(FakeModel 测)
- 缓存命中: 同 `_tree_signature` 不重调小模型
- 降级: 小模型抛异常 → 启发式兜底返回, 不崩
- forcing(a): search-state prompt 引导浮现 failed/pattern
- forcing(b): 连续失败 → reflect 提示注入
- 原 32 测试全绿 + 新增 SmallModelIntuition / forcing 测试

## 顺序

**C1+C2(本轮)** → C3 forcing(下轮, 改 agent_loop) → C4 实测(跑 duckov 等大任务测延迟账)
