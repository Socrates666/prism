# RLM 认知层 · 提案总览

> **状态**:讨论产物(设计提案, **未实现**)。分支 `proposal/rlm-cognitive-layer`。
> **来源**:2026-08-10 讨论 + **9 轮 werden 诘问**(把提案从模糊冲动逼成可落地的结构)。
> **RLM = Recursive Language Model**:模型能自我指涉(self-reference)、自我建构(self-construction),逐步涌现对复杂任务的理解。

## 一句话

现有 `compact()`(对齐 pi,阶段 0–13 已落地)是**被动应急**——窗口满了才把历史压成一段文字摘要。本提案把上下文管理从「事后压扁」升级为「一直在场的认知结构」:**不可变 core + 认知树 + 直觉(scribe)+ 自指递归**。

## 动机:为什么 compact() 不够

`compact()`(agent.py)把 `messages` 渲染成平文本 → 压成摘要 → **整个替换 history**。三个根本问题:

| # | 问题 | 根因 |
|---|------|------|
| ① | **信息丢失** | 结构(因果链、分治层级)被压成散文 |
| ② | **无任务边界** | 历史是单链表,没有"这是一棵新树" |
| ③ | **无自指能力** | 历史只记内容不记推理路径,无法回溯重组 |

RLM 的本质恰恰是 ③。对照原则 5(无中断,北极星):compact() 是**被窗口满打断**——它本身就是一种中断。认知层把上下文管理变成**一直在场、主动构造**的机制。

## 三个机制速览

1. **不可变 core**(见 [core.md](core.md))—— loop + Forest 契约 + ABC,硬不可变。**为何不可变 = 直觉不可绕过的物理实现。**
2. **认知树**(见 [tree.md](tree.md))—— **一树两轴**:causes(搜索/回溯,横向分治)+ based_on(自指/套娃,纵向)。节点两类(思维 + 上下文)用不同边;失败回溯。
3. **认知周期**(见 [cycle.md](cycle.md))—— 直觉→思考→行动→观察。直觉 = READ(选/排/临时压,每次 loop 不可绕过);剪枝 = WRITE(结构阈值触发)。

辅助:[scribe.md](scribe.md)(TreeScribe 小模型)、[persistence.md](persistence.md)(SQLite Forest)、[route.md](route.md)(落地 R0–R6)。

## 子文件导航

| 文件 | 内容 | 结论 |
|------|------|:----:|
| [core.md](core.md) | ★不可变 core 契约 + 原则 10/8 修正 | 确定 |
| [tree.md](tree.md) | ★认知树一树两轴(causes 搜索 / based_on 自指) | 确定 |
| [cycle.md](cycle.md) | ★认知周期 + READ/WRITE/剪枝 | 确定 |
| [scribe.md](scribe.md) | TreeScribe 小模型导航搜索树 | 部分 open |
| [persistence.md](persistence.md) | SQLite Forest 选型 + schema | 确定 |
| [route.md](route.md) | 落地路线 R0–R6(标确定 vs open) | 确定 |

## 确定 vs open 总表

### 【确定 SOLID】(9 轮 werden 逼出)
1. core 不可变 = 直觉不可绕过的物理实现(core 可变 → agent 能拆掉直觉)
2. core = loop(搜索循环)+ Forest 契约(ABC + 遍历原语)+ ABCs;core 不认识树实例
3. 认知树 = 一树两轴:causes(搜索/回溯)+ based_on(自指/套娃)
4. 搜索(causes)≠ 自指递归(based_on)—— 9 轮最关键的撞墙
5. reflect 工具 = 自指递归入口(沿 based_on,可套娃)
6. 节点两类(思维 + 上下文)用不同边;节点带状态(active/failed/success)
7. 直觉 = READ(选/排/临时压),每次 loop,焊进 core,不可绕过
8. 剪枝 = WRITE,结构阈值触发(非 agent 判断、非每次 loop)
9. IPython 不死,被 core 挡一块(agent 能碰世界对象,够不到 core loop/model backend)
10. loop 从线性 function-calling → 搜索循环(explore/evaluate/backtrack)
11. 认知周期:直觉→思考→行动→观察

### 【仍 open】
1. **谁控制搜索?**(主模型 α / 小模型 β)—— [scribe.md](scribe.md)
2. **小模型选型与延迟**(必须实测,方案成立硬门槛)—— [scribe.md](scribe.md)
3. **自指递归终止条件**(收敛/深度/目标/资源,或"一直在场")—— [tree.md](tree.md)
4. **任务边界判定** + `/task new` 兜底 —— [scribe.md](scribe.md)
5. **森林膨胀剪枝阈值具体值** —— [persistence.md](persistence.md)
6. **reflect 工具归 core 默认 还是 ext** —— [route.md](route.md)
7. **范式定位**(外壳 vs 认知 harness)—— 见下

## 范式抉择:外壳,还是认知 harness?

| 定位 | 需要认知层? | 理由 |
|------|:-----------:|------|
| **好用的多 agent 外壳**(类 prime Python 版) | 不需要 | 现有 compact + actor + patch 够用,这套过度设计 |
| **RLM 认知 harness**(能自我指涉、涌现理解) | **这套是骨架** | 没有认知树+core+自指,"自我指涉"无处落地 |

**建议**:R0–R2(核心契约 + 存储 + 启发式 scribe)**不依赖范式抉择**——它把认知结构做成"有则更强、无则退化"的可插拔层(R0 空钩子即现状)。先落 R0–R2 作能力储备,范式定位在用起来后自然清晰。若最终只做外壳,R0–R2 是可丢弃 spike,零核心污染(全是 ABC + ext/)。

> 决策权在用户:纳入路线(从 R0 开始)/ 搁置(作 spike 备查)/ 否决(纯外壳路线)。
