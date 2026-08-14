# 实验 · 二重树的反思能力验证（网页游戏生成任务）

> 对应 `plan/rlm/schedule-validate-A.md` Sprint 2（D1 runner / D2 measurement / D3 反思友好实验）。
> 分支 `research/dual-tree-reflection`，短命实验分支，裁决后合并即删。

## 背景与假说

**二重树** = 一树两轴（`plan/rlm/tree.md`）：

- **causes 轴**（横向）：思维节点单父成树，撞瓶颈 → `mark(failed)` → 回溯另开支（搜索）
- **based_on 轴**（纵向）：任意思维节点连边，反思连回被反思节点，反思可被再反思（自指递归，RLM 灵魂）

555 节点审计（`research/FOREST_RUNTIME_AUDIT.md`）确证：机制已建、灵魂未活——
`reflect` 工具从未装配进任何 agent、无任何路径调 `mark(FAILED)`、0 条 based_on 边，树退化为线性日志。

**本次实验假说**：把最小装配补上（`enable_cognitive_cycle` + `add_tool(make_reflect_tool)`，零 core 改动，
全部在 runner 层装配），在反思友好任务（带陷阱的网页游戏生成）上：

- H1（结构性）：反思链条出现——reflection 节点 + based_on 边 > 0，且非全部孤立
- H2（行为性）：反思是**真的**——反思内容指向具体失败/模式，且反思后行为改变（换路而非重复）
- H3（对比性）：树条件 vs 无树 baseline，反思从"文本里的自言自语"变成"结构化可累积的器官"

**证伪也要认**（schedule 风险表）：若装配后仍然 0 反思 / 反思是仪式性套话 → 二重树现状裁决为"不自指"，是最高价值负结果。

## 设计

### 任务：网页游戏生成（子 agent 生成 6 个 prompt）

`prompts/0X-*.md`，每个是单文件 HTML 游戏任务，**内置 2-3 个微妙陷阱**（典型一版实现会做错的具体规则，
如碰撞边界、计分规则、首点击安全），任务要求自我验证交付。陷阱让任务"反思友好"（会先失败、需要改）。

**prompt 中性原则**：任务 prompt 绝不提"反思/认知树/forest/reflect"——不引导证人。

### 条件（每游戏 × 每条件 = 1 只小白鼠，各占独立 run 目录）

| 条件 | 装配 | 检验什么 |
|------|------|----------|
| `tree`（实验组） | SQLiteForest + enable_cognitive_cycle(启发式直觉) + **reflect 工具装配** + 自指意识 prompt（既有） | 二重树反思能力 |
| `base`（对照组） | NullForest，无认知层、无 reflect 工具 | 无树时模型自发反思（只在文本里）的水平 |

两组共用：同模型（PRISM_MODEL）、同 max_turns、同系统提示基底（角色+环境说明，中性）、同任务 prompt。

### 运行（D1 runner）

`runner.py`：每只小白鼠一个**独立进程**（cwd=自己的 run 目录，互不踩踏），
orchestrator 线程池并发。采集三类证据：

- `events.jsonl`：事件流（assistant 文本、工具调用/结果、认知事件 intuition/reflect）——subscribe 落盘
- `memory/<name>.json`：完整对话 transcript（FileMemory）
- `forest.db`：认知树（仅 tree 组）——反思链条的一手证据

### 测量（D2 measurement）

`measure.py` 对每个 tree 组 run 提取：`tree.json`（全节点+边快照）+ 结构化指标
{reflections 数 / based_on 边数 / based_on 链长 / failed 节点数 / causes 分叉度 / 深度 /
reflect 工具调用数 / raw forest 操作数}；base 组提取 {文本内自发反思行为}（交给分析 agent）。

### 分析（子 agent 逐 run 裁决）

每游戏一个分析子 agent，读该游戏两组 run 的全部证据，按统一量规裁决：

1. **结构性反思链条**：based_on 边存在？反思链（反思→被反思→更深）连续？
2. **反思质量**：真反思（指向具体失败节点/模式、可操作）vs 仪式性（"我要更仔细"套话）？
3. **行为改变**：反思/mark(failed) 之后，后续动作是否换了路线（不再撞同一堵墙）？
4. **对照**：base 组文本里的自发反思有没有？和 tree 组比缺了什么（可累积？跨轮可见？）？
5. **任务结果**：game.html 是否产出、陷阱规则是否做对（次要证据）。

### 产出

- `analysis/<game>.md` × 6：逐游戏裁决
- `REPORT.md`：汇总 + H1/H2/H3 判定 + 对 D4（路线定型）的建议

## 目录约定

```
research/dual-tree-reflection/
  README.md        本设计文档
  prompts/         6 个游戏任务 prompt（子 agent 生成）
  runner.py        并发实验 runner（单subject/编排两用）
  measure.py       树指标提取 + tree.json dump
  analysis/        子 agent 逐游戏分析报告
  REPORT.md        最终裁决
  runs/            运行时数据（gitignore：forest.db/events.jsonl/transcript/game.html）
```
