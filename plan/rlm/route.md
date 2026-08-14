# 落地路线:创造 RLM 认知层

> **阶段定位**:创造期(非优化 / 非 crude-demo)。建真的 core + 树 + 直觉,实验在真系统上跑。
> **执行顺序**(用户定):**Plan → Core → Tree → Intuition(小模型)→ Experiment**。
> **状态图例**:✅ 本轮确定 / 🟡 open(有默认假设,动手前可改)

---

## 默认假设(动手前可改)

| 开叉 | 默认 | 理由 |
|------|------|------|
| 🟡 α/β 谁控搜索 | **α**:主模型控搜索 + 自指 reflect;小模型 = 直觉(导航树 + 拼 search-state,**不控决策**) | "用小模型" = 小模型当直觉,主模型当脑;β(小模型控搜索)作实验变体 |
| 🟡 forcing function | **a+c 混合**:loop 失败时浮现 failed 兄弟 + agent 自指 pattern + 结构要求 reflect 一步 | 单 a 太机械,单 c 依赖小模型眼力;混合最稳。b(挑衅子 agent)作变体 |
| 🟡 小模型选型 | glm-4.5-air 级(直觉),C3 实测延迟账 | 必须实测 scribe 时间 < 省 token 时间 |

> 这三个不动手前可改。一旦开建 Phase A,α/β 影响最大(决定 loop 结构)。

---

## Phase A · Core(优化基座)— 不可变契约 + loop 升级

> 把 prism 的线性 function-calling loop 升级为搜索循环,立起不可变 core 契约。**先于树和直觉**——契约是树和直觉的地基。

- [ ] ✅ **A1 · agent_loop 搜索循环**:`prism/agent_loop.py` 从线性(call→tool→call)重写为 **直觉→思考→行动→观察 + backtrack**。
      - 直觉 stage:调 `IntuitionBackend.select_context(state) → search-state`
      - 思考 stage:主模型在 search-state 上 → thought / action / 决策回溯
      - 行动:execute tool
      - 观察:result → CognitiveHook.on_cognitive_event(挂节点 / 标 failed → frontier 回父)
      - 🟡 α 默认:主模型控回溯决策;小模型只喂 search-state
- [ ] ✅ **A2 · 核心 ABC**(`prism/cognitive.py`):
      - `Forest`(ABC):`add_node/add_edge/mark/subtree/walk/prune` + `NullForest`
      - `CognitiveHook`(ABC):`on_cognitive_event/select_context/on_promote` + `NULL_HOOK`(空 = 退化为现状)
      - `IntuitionBackend`(ABC):`select_context(state) → search-state` + `NullIntuition`
- [ ] ✅ **A3 · core 硬不可变**(原则 10 修正):`guard.py` 拦写 `prism/` core(留 `ext/` 可写)。删 verify_and_revert 放行,改回拦写。
- [ ] ✅ **A4 · Agent 接入**:Agent 持 `cognitive_hooks: list`(空默认)、`forest`、`intuition`。
- [ ] **验收 A**:原 190 测试全绿(空 hook/NullForest/NullIntuition = 逐字节现状);搜索循环骨架跑通(无树时退化为线性)。

---

## Phase B · Tree(认知树)— SQLite Forest + 一树两轴

> 在 A 的 Forest ABC 上实现真树。两轴(causes 搜索 / based_on 自指)+ 两类节点 + 失败回溯。

- [ ] ✅ **B1 · SQLiteForest**(`prism/forest.py`):nodes(category/type/status)+ edges(relation)+ 递归 CTE(walk causes / based_on)。`NullForest` 跑通。
- [ ] ✅ **B2 · 两轴 + bridge 边**:
      - causes(thinking→thinking,树,backtrack)
      - based_on(thinking→thinking 任意,图,自指套娃)
      - produces/evidences(thinking↔context,挂载)
- [ ] ✅ **B3 · auto-attach**:CognitiveHook 监听 emit(thought/action/result)→ 挂 causes 节点(L0→L1,零门槛)。
- [ ] ✅ **B4 · reflect 工具**:agent 调 → 产 `reflection` 节点 + `based_on` 边(自指入口,可套娃)。🟡 归 core 默认工具还是 ext,落地定。
- [ ] ✅ **B5 · 失败回溯**:撞瓶颈 → `mark(node, failed)` → frontier 回 causes 父 → 另开子支。
- [ ] **验收 B**:树跨重启恢复;递归 CTE 正确走两轴;reflect 造节点 + based_on 反溯回原推理;backtrack 移 frontier。

---

## Phase C · Intuition(直觉系统)— 小模型导航

> 直觉 = 小模型选/排/压 → search-state。从第一步用小模型(非先启发式后升级)。

- [ ] ✅ **C1 · IntuitionBackend 小模型实现**:glm-4.5-air 级,`select_context` 做选/排/临时压(READ,不写回)→ search-state(根→frontier 路径 + failed 兄弟 + 近期 reflection)。
- [ ] ✅ **C2 · 性能**:`_context_sufficient()` 快速路径 + `active_context` 跨调用缓存(同轮连续工具调用不重触发)。
- [ ] ✅ **C3 · forcing(a+c 混合)**:search-state 里**浮现 failed 兄弟 + agent 自指 pattern**(小模型看出"你在这类地方总是 X");loop 失败时**结构要求 reflect 一步**。
- [ ] 🟡 **C4 · 延迟账实测**:scribe 时间 < 省 token 时间。不过关 → 退启发式(降级安全阀)。
- [ ] **验收 C**:search-state 含 frontier 路径 + failed 兄弟 + reflections;同轮不重触发;延迟账过关。

---

## Phase D · Experiment(事上磨)— 小白鼠验证涌现

> 真系统建好,放小白鼠磨。用 prism 现成 `spawn()` + `workspaces/` 隔离,多 condition 并发跑。

- [ ] ✅ **D1 · experiment runner**:spawn N 小白鼠(conditions:baseline 无树 / +tree+reflect / forcing-a / b / c),各 `workspaces/<name>/`,跑**同一**任务。
- [ ] ✅ **D2 · measurement**:run 完 dump 树 → `workspaces/<name>/tree.json`(可解释路径 = 数据)+ 计数{reflections / based_on 环 / failed 支 / depth}+ 任务结果。
- [ ] ✅ **D3 · 第一个实验**:reflection-friendly 任务(debug 微妙错误函数 / 带陷阱多步谜题——撞墙→换思路才通)。
      - 看:**+tree 那只真造 reflection 了吗**?based_on **真成环了吗**(自指发生)?**任务更好 / dead-end 更少吗**?
- [ ] ✅ **D4 · 证伪也要认**:+tree 那只不自指(树在那不用)/ 自指了没帮上忙 → bitter lesson 第二把刀往"自指涌现是多余脚手架"倒,**得认**,转纯外壳路线或换机制。
- [ ] **验收 D**:跑出 baseline vs +self-ref 对比数据;涌现签名(自指沿树 + 任务更好)**有/无明确**,据此决定路线。

---

## 阶段依赖与风险

```
A (core 契约) ──▶ B (树) ──▶ C (直觉) ──▶ D (实验)
   │                │           │            │
   └ 190 测试不破    └ 两轴+回溯   └ 延迟账     └ 涌现证伪也要认
```

- **A 是地基**,不先立契约,B/C 无处接。
- **D 是判官**——A/B/C 建得再漂亮,D 跑不出涌现签名,这套就是 bitter lesson 说的多余脚手架。
- 🟡 **最大阻塞**:α/β(A 之前最好定,否则 loop 结构返工)。

---

## 不在本路线(defer)

SQLite 跨 session 复合实验 / promote_node 涌现固化(R6)/ spawn=子树(R5)—— 都是 D 之后或 D 中按需加。本路线止于"证明自指涌现成不成立"。
