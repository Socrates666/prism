# prism · plan

> 名字:棱镜把一束光分成多束 —— 这个工具的核心机制:**一个 IPython 内核,分出多个 agent / 多个长任务会话**。被 PrimeAgent 启发,致敬 pi 的简洁。

---

## 一句话形态

prism 是一个在**项目根启动**、**主 agent 享完整 IPython(共享命名空间,用户等价)、子 agent 由工厂生产(受限、固定工作区、赋予工具)**、靠 **actor(每 agent 线程 + inbox + inject)** 并发、靠**扩展点 patch + 可变区人格插件**实现增量扩建、**前端 textual 全屏 TUI 套壳**、追求**无中断日常交互**的简单 agent 工具。

并向 **RLM(Recursive Language Model)认知 harness** 演进:不可变 core + 认知树 + 直觉(scribe)+ 自指递归。

---

## 文件导航

| 文件 | 内容 | 状态 |
|------|------|:----:|
| [seed.md](seed.md) | 种子(用户原话)+ 项目命名 + werden 流程元数据 | — |
| [principles.md](principles.md) | 核心原则 1-16(+ RLM 修正方向) | 实施中 |
| [architecture.md](architecture.md) | 系统架构图 + 工程设计(目录/多agent/patch/继承/theme) | 实施中 |
| [lineage.md](lineage.md) | 被照亮的维度 + 试错记录(被否押注)+ prime-agent 翻译 | — |
| [status.md](status.md) | 现状总览(审计)+ 开放问题/风险 | 周期校准 |
| [roadmap.md](roadmap.md) | 实现路线 阶段 0–14 | 0–13 ✓ |
| [rlm/](rlm/) | **RLM 认知层**(提案 + 9 轮 werden 结论) | **提案/未实现** |

### RLM 子目录

| 文件 | 内容 |
|------|------|
| [rlm/README.md](rlm/README.md) | 提案总览(一句话/动机/状态/导航)+ 确定 vs open 总表 |
| [rlm/core.md](rlm/core.md) | ★不可变 core 契约(为何不可变 = 直觉不可绕过) |
| [rlm/tree.md](rlm/tree.md) | ★认知树:一树两轴(causes 搜索 / based_on 自指) |
| [rlm/cycle.md](rlm/cycle.md) | ★认知周期:直觉→思考→行动→观察;READ/WRITE/剪枝 |
| [rlm/scribe.md](rlm/scribe.md) | TreeScribe:小模型导航搜索树拼 search-state |
| [rlm/persistence.md](rlm/persistence.md) | SQLite Forest(选型 + schema) |
| [rlm/route.md](rlm/route.md) | 落地路线 R0–R6(标注确定 vs open) |

---

## 阅读顺序

1. **先读** [seed.md](seed.md)(为什么有这个项目)→ [principles.md](principles.md)(设计铁律)
2. **再读** [architecture.md](architecture.md)(长什么样)→ [status.md](status.md)(现在到哪了)
3. **要干活** [roadmap.md](roadmap.md)(阶段清单)
4. **要理解 RLM** [rlm/README.md](rlm/README.md) → rlm/core.md → rlm/tree.md → rlm/cycle.md(这三篇是 9 轮 werden 的核心结论)

---

## 两层定位

| 层 | 内容 | 状态 |
|----|------|:----:|
| **外壳**(多 agent 外壳) | IPython 内核 + actor 多 agent + patch + ext/ + TUI + 持久化 | **阶段 0–13 全 ✓**(190 测试) |
| **认知 harness**(RLM) | 不可变 core + 认知树 + 直觉 + 自指递归 | **提案/未实现**(见 [rlm/](rlm/)) |

外壳是地基(已立住),认知 harness 是上限(在 becoming)。两者关系见 [rlm/README.md](rlm/README.md) §范式抉择。

---

> 本目录由原 `PLAN.md`(单文件 753 行)结构化拆分而来。`PLAN.md` 现为指向本目录的薄壳。
> RLM 认知层 = 2026-08-10 讨论产物 + 9 轮 werden 诘问结论。
