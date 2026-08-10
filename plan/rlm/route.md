# 落地路线 R0–R6

> 每阶段独立可验、不破坏现有 190 测试。核心契约先行(R0),实现可降级(R2 启发式 → R3 模型)。
> 标注:✅ 本轮确定 / 🟡 仍 open。

## R0 · 核心契约(地基,零行为变化)
- [ ] ✅ `CognitiveHook` ABC + `NULL_HOOK`(NullScribe);Agent 持 `cognitive_hooks: list`(空默认)
- [ ] ✅ 定义认知事件类型(emit 点广播:thought/action/result/reflection/promote)
- [ ] ✅ Agent 在 emit 处广播给 hooks(空 list → 无操作)
- [ ] **验收**:原 190 测试全绿;空 hook 的 agent 行为与现在逐字节相同

## R1 · SQLite Forest(存储,不接 agent)
- [ ] ✅ `prism/forest.py`:SQLiteForest(nodes/edges schema + category + status + 递归 CTE)
- [ ] ✅ Forest API:`add_node / add_edge / mark / subtree / walk / prune`
- [ ] **验收**:写读跨重启恢复;递归 CTE 正确走 causes/based_on;NullForest 跑通

## R2 · 纯启发式 TreeScribe(无小模型,先跑通)
- [ ] ✅ TreeScribe:启发式评分(recency + 深度 + relation)选/排子树载入 search-state prompt
- [ ] ✅ `_context_sufficient()` 快速路径 + `active_context` 跨调用缓存
- [ ] ✅ CognitiveHook(HeuristicScribe)接 R0 广播 → 自动挂树(L0→L1)
- [ ] ✅ 压 = READ(临时缩写,不写回)
- [ ] **验收**:search-state 含 frontier 路径 + 失败兄弟支;同轮连续工具调用不重触发;token < 全历史基线

## R3 · 小模型决策 + 任务边界
- [ ] 🟡 scribe 接小模型(glm-4.5-air 级)做决策:① 哪些节点载入 ② 新任务 vs 延续
- [ ] 🟡 **谁控制搜索(α 主模型 / β 小模型)—— 阻塞项,必须先定**(见 [scribe.md](scribe.md))
- [ ] 🟡 新任务 → 新树根;延续 → 挂当前树;`/task new` 手动切兜底
- [ ] **验收**:任务边界判定 + 延迟账实测(scribe 时间 < 省 token 时间);失败可回退 R2 启发式

## R4 · 自指递归(reflect 工具 + based_on 边)★RLM 内核
- [ ] ✅ `reflect` 工具:agent 对自己 subtree 重组推理 → 产出 `reflection` 节点,沿 `based_on` 连回原节点
- [ ] ✅ reflection 可被再 reflect(套娃)—— 这才是自指递归(区别于搜索)
- [ ] 🟡 自指终止条件:收敛 / 深度上限 / 目标达成 / 资源预算(或"一直在场")
- [ ] 🟡 reflect 归 core 默认工具 还是 ext/
- [ ] **验收**:reflect 产 reflection 节点;沿 based_on 反溯能回到原推理路径;套娃 ≥ 2 层

## R5 · 递归与 spawn 整合(spawn = 子树)★对接原则 13
- [ ] ✅ spawn 的子 agent 其树是**父 agent 树的子树**(非 inject 字符串)
- [ ] ✅ 子 agent 结果沿 causes 折回父树;横向分治递归有了结构表达
- [ ] **验收**:spawn 建子树;父能查子子树;结果 fold 回父节点

## R6 · 涌现固化桥(promote_node → ext/)
- [ ] ✅ `promote_node(id)`:把高复用 pattern 子树抽成 `ext/skills/<name>.md`(L1→L2)
- [ ] ✅ 剪枝(第三触发器):树超阈值 / 任务边界 → 老子树压成摘要节点
- [ ] 🟡 剪枝阈值具体值
- [ ] **验收**:recurring pattern promote 成 skill;新 session 自动加载该 skill;剪枝后树规模 bounded

---

## 阻塞项(必须先解才能推进)

1. **🟡 α/β 谁控制搜索**(R3 阻塞)—— 决定 agent_loop 整个结构。详见 [scribe.md](scribe.md)。
2. **🟡 自指终止条件**(R4)—— 决定 reflect 会不会无限套娃。

## 范式抉择不阻塞 R0–R2

[README.md](README.md) §范式抉择:R0–R2 不依赖"外壳 vs 认知 harness"定位。先落 R0–R2 作能力储备(全是 ABC + ext/,零核心污染),范式定位在用起来后自然清晰。

---

> 落地工具:triage(R0–R2 每阶段独立验收)/ plan(整段写计划)均可。
