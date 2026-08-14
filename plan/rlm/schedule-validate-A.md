# 排期 · 主攻 A 验证(C 收尾 + D 实验)— 2026-08-14 修订

> **北极星**:拿到"二重树自指是否提升性能"的裁决(Phase D)。B(IPython 外壳)冻结新功能、只做够用 testbed;pi 扩展分叉 defer。
> **依据**:见导师分析(ThinkingKB「prism主攻A还是B的优先级裁决」)—— B 的独特性挂在 A 上,A 不挂 B;用 prism(IPython 裸持)是给 A 假说最慈善的证伪。
> **基线(2026-08-14 实测)**:外壳 0–13 闭合;RLM A·core / B·tree 已落地并合入 research 分支(prune 实现 + 复杂度优化 + 555 节点实证审计);**329 测试全绿**;TUI 已切自研(零 textual)。
> **图例**:✅ 已落地 / 🟡 进行中 / ☐ 待做 / ❄️ 冻结 defer

---

## 分支策略(2026-08-14 清理后)

| 分支 | 处置 | 理由 |
|------|------|------|
| `supergoal/rlm-core-tree` | **合回 main 后删除** | 主线(A/B 落地 + TUI),main fast-forward |
| `research/forest-search-complexity` | **已合入主线,删除** | prune/复杂度/审计三提交,冲突已解决、329 测试验证 |
| `origin/supergoal/pi-faithful-tui` | **删除(内容已被演进版取代)** | 同源 9 文件,HEAD 是其超集(+918 行认知层) |
| `pi-ext-cognitive` | **保留分支,撤 worktree,defer** | pi 扩展已实现 Phase C scribe(TS);D 裁决后重审 |
| worktree: `.worktrees/forest-algo`、`prism-pi-ext` | 撤除 | 分支合并/保留后,目录不再需要 |

**今后约定**:单人开发直接在 main 上做短周期提交;探索性工作用 `research/*` 或 `spike/*` 短命分支,合并即删。避免长命分叉再积压。

---

## 冻结 / defer(本轮不碰)

- ❄️ **B 外壳打磨**:theme 口子补完 / workspace 清理(开放问题 #15)/ 持久化并发锁(#18)/**TUI 折射动画、completion、配色类打磨**(8c5e851 之后的此类项)→ 全 defer 进 backlog。外壳只要"能稳定跑 D 实验"即合格 testbed。
- ❄️ **pi 扩展分叉**(`pi-extension.md` + `pi-ext-cognitive` 分支):作 D 的备选 condition,不在本轮。D 出结果才重审。
- ❄️ 阶段 14(可变 base):已被 RLM 硬不可变方向取代,正式放弃。

---

## 前置(动 C 之前,零风险优先)

- [x] ✅ 文档同步:status.md 测试数 → 329;A/B 标 ✓;TUI 自研入 lineage。(2026-08-14)
- [ ] ☐ **A3 硬不可变 flip** `prism/guard.py`:删 verify_and_revert 放行 → 改回拦写 `prism/` core,留 `ext/` 可写。(0.5d —— 原则 10 修正)
- [x] ✅ **B5 回溯补完**:失败回溯 + research prune(子树压摘要 + 外部入边重连)已随 research 合并入主线,6 测试覆盖。
- [ ] ☐ devlog 断档处理:08-10 之后无记录。要么恢复 devlog 习惯,要么在 plan/README.md 宣布"以 commit log 为准"。(0.1d)

---

## Sprint 1 · C 阶段收尾(目标:直觉焊进 core + 延迟账过关)

> 参考实现:`pi-ext-cognitive` 分支的 Phase C scribe(TS 版 选/排/压 + 缓存 + 降级)已跑通,Python 版可对照移植。

| 步 | 任务 | 落点 | 估时 | 验收 |
|---|---|---|---|---|
| C1 | SmallModelIntuition 接入 Agent + 测试(glm-4.5-air 级) | `cog_intuition.py` / `tests/test_cog_intuition.py` | 0.5d | `select_context` 返 search-state system msg(FakeModel 测) |
| C2 | 缓存命中测试(索引路径已有,补小模型缓存) | 同上 | 0.25d | 同 `_tree_signature` 不重调小模型 |
| C3 | forcing(a+c 混合) | `prism/agent_loop.py` `cog_patches.py` | 1.5–2d | search-state 浮现 failed/pattern + 连续失败→结构要求 reflect |
| C4 | 延迟账实测 + 降级 | 真任务(duckov 等) | 1d | scribe<300ms 且省 token;不过→退 Heuristic(降级阀,已就位) |

**里程碑 M1**:SmallModelIntuition 跑通 + forcing 生效 + 329+ 测试不破 + 延迟账过关(或降级)。

---

## Sprint 2 · D 实验(目标:裁决)

> D 是判官。A/B/C 再漂亮,跑不出涌现签名,整套是多余脚手架,**得认**。

| 步 | 任务 | 落点 | 估时 | 验收 |
|---|---|---|---|---|
| D1 | experiment runner | 新模块 | 1d | spawn N 小白鼠(baseline 无树 / +tree+reflect / forcing-a/b/c),同任务并发,各 `workspaces/<name>/` |
| D2 | measurement | `workspaces/` | 0.5d | dump `tree.json` + 计数{reflections / based_on 环 / failed 支 / depth} + 任务结果 |
| D3 | 第一个反思友好实验 | `workspaces/` | 1d | 微妙 bug 函数 / 带陷阱多步谜题。看自指是否真发生(555 节点实证审计脚本 `research/analyze_real_forest.py` 可复用作观测) |
| D4 | 裁决(证伪也要认) | `plan/rlm/` 结论 | 0.5d | 涌现签名 有/无 明确 → 路线定型 |

**里程碑 M2(项目级)**:涌现签名裁决落锤 → 重新决定 B 打磨与 pi 分叉。

---

## 合计

- 前置 ≈ 0.6d;C 收尾 ≈ 3.25–3.75d;D ≈ 3d。
- **到 D 裁决 ≈ 7–8 人日**(AI 辅助、单人、专注节奏)。

---

## 风险与降级

| 风险 | 触发 | 降级 |
|---|---|---|
| C4 延迟不过 | scribe ≥300ms 或不省 token | 退 Heuristic(降级阀已备),C 标"启发式够用",仍进 D |
| α/β 未定返工 | C3 后才发现小模型该控搜索 | **C3 前钉 α**(route.md 默认:主模型控搜索,小模型只喂 search-state) |
| **D null 结果** | +tree 那只不自指 / 自指没帮上 | **必须认**;转纯外壳(B)或换机制 —— 最高价值负结果,非失败 |
| 工程门阻塞 | mimosa commit 门对"exec=产品本质"的既有 finding 拦提交 | 已配 `.mimosa/security-policy.json` 威胁模型备案;提交走用户终端或门侧白名单(见工程约定) |

---

## 工程约定(2026-08-14 新增)

- **安全门**:ZCode 侧 mimosa 钩子在 commit 前跑 L3 全项目审计,高危硬拦。当前 9 个"高危"均为设计本质(agent 内核 exec / REPL exec / guard 测试 fixture),已在 `.mimosa/security-policy.json` threat model 备案。**agent 侧提交受阻时走用户终端**,不改代码迁就扫描器。
- **运行时状态不入库**:`.prism/memory/`、`.prism/forest.db`、`workspaces/`、`.mimosa/` 均已/应 gitignore;历史在 git 历史里可找回。
- **search 工具外发**:域名白名单(`_ALLOWED_HOSTS`)+ 仅 https;新增平台时把 API 域名加进白名单与 policy `network.allowedHosts`。
