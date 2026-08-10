# ★ 不可变 core 契约

> werden round 0–5 的统合结论。本篇回答:**core 是什么、为什么不可变、不可变边界画在哪。**

## 一句话

**core 不可变,不是为了"稳定",是为了"直觉不可绕过"。** core 可变 → agent 不爽就能拆掉直觉那步、直接调 model。不可变 core 是"保证直觉每次都发生"的**物理实现**。

这句话把 5 轮 werden 缝起来:
- round 0 "不可变 core 冲动(为什么?)" → round 5 "为了递归不被绕过"
- round 1 "递归对象 = 认知树 data,不是实现 code" → core 是纯算子
- round 2 "core = step + ABC,零递归 in core" → 递归是 reflect 工具
- round 3 "Forest 契约同级,树实例是 data" → core 不认识树实例

---

## core 是什么(最小契约)

core = **loop + Forest 契约 + ABCs**,三样,不可变,一屏看完:

```
┌─ 不可变 core ──────────────────────────────────────────┐
│  1. loop          搜索循环(explore/evaluate/backtrack)  │
│                   直觉→思考→行动→观察,见 cycle.md       │
│  2. Forest 契约   ABC + 遍历原语(递归 CTE 走 causes/     │
│                   based_on);不持有树实例,只定义接口     │
│  3. ABCs          Agent / ModelBackend / CognitiveHook   │
│                   / IntuitionBackend                    │
└─────────────────────────────────────────────────────────┘
        ▲ core 黑盒: agent 够不到 loop / model backend
┌─ 可变 data ────────────────────────────────────────────┐
│  messages(工作记忆,L0)+ tree-nodes(认知树,L1)       │
└─────────────────────────────────────────────────────────┘
┌─ ext/(人格/策略) ──────────────────────────────────────┐
│  tools/prompts/patches/skills + scribe 策略(智能升级)  │
└─────────────────────────────────────────────────────────┘
```

**core 不认识树实例**:跟 loop/messages 同理——loop 不可变,它操作的 messages 可变;Forest 契约(ABC + 遍历原语)不可变,它操作的 tree-nodes 可变。"树进 core" = **Forest 契约进 core,某棵具体的树还是 data**。

## loop 升级:线性 → 搜索循环

现在的 `run_agent_loop` 是**线性 function-calling**(call→tool→call→...)。core 的 loop 要升级为**搜索循环**(explore / evaluate / backtrack):

```
loop:
  1. 直觉(scribe):读树,选/排/压 → search-state context     [READ, 不可绕过]
  2. 思考(主模型):context → 下一 thought / 决策回溯        [写新节点 或 标 failed]
  3. 行动:执行工具/spawn
  4. 观察:result → 更新树(新节点 / 标 failed→回溯)         [WRITE]
  → 回 1
```

这不是加 patch 能解决的,是 **loop 本体重写**。core 的"loop 一等公民"跟着升级。

## 机制进 core / 策略进 ext/

core 只硬编码**契约 + 广播点**,不知道树实例 / scribe 策略 / SQLite:

```python
# core 只硬编码 ABC + 广播点
class CognitiveHook(ABC):
    """认知事件观察者。空实现 = agent 退化为普通 agent(无任何认知层)。"""
    def on_cognitive_event(self, agent, event: dict) -> None: ...      # 观察认知事件
    def select_context(self, agent, messages) -> list: return []       # 返回额外上下文
    def on_promote(self, agent, node_id) -> str | None: return None    # 节点固化为实体

NULL_HOOK = CognitiveHook()   # 空钩子 = agent 退化为现状
```

**与现有三套自举机制同构**(第 4 套):

| 机制 | core 硬编码 | ext/ 策略 | 自举类型 |
|------|-------------|-----------|----------|
| `hooks["emit"]`(原则 9) | 事件广播点 + 默认渲染 | agent 替换 hooks | **显示自举** |
| `memory`(原则 6/7) | MemoryBackend ABC + dump 点 | FileMemory/自定义 | **状态自举** |
| `patch`(原则 11) | 五扩展点 + PatchRegistry | before/after/around | **行为自举** |
| **CognitiveHook**(本提案) | 认知事件广播 + Hook ABC | scribe/forest/promote | **认知自举** |

> `hooks["emit"]` 是显示自举,`CognitiveHook` 是认知自举——同一套设计哲学第四次应用。

**比 patch 松、比硬编码紧:**
- **比 patch 松**:patch 是拦截(around 可改/吞/替换);CognitiveHook 是广播(fire-and-forget,只观察)→ **空钩子也能跑,退化为普通 agent**(原 190 测试一字不改地绿)。
- **比硬编码紧**:广播点是 core 固定的固定点(认知事件类型写死),不是任意注入点 → 契约稳定,不怕 agent 乱改语义。

## 原则 10 修正

**当前(已实现)**:`guard.py` 允许写 prism/(备份 + verify_and_revert + /revert)。
**RLM 方向(未实现)**:core 回归**硬不可变**——`guard.py` 删除对 prism/ core 的放行,只允许 ext/ 可写。

| | 当前 原则 10 | RLM 修正 |
|---|---|---|
| prism/ core | 可写 + 备份 + 回退 | **硬不可变**(拦写) |
| ext/ | 可写 | 可写(不变) |
| 自我演进 | 改 core 代码 | 走 patch / ext / 认知树(改 data) |
| 理由 | "agent 自我演进" | **自我演进不需要改 core;改 core 会破坏直觉不可绕过** |

自我演进的对象是**认知树(data)**和 **ext/(策略)**,不是 core 代码。core 是固定算子,操作的 data 可变 → 真自指不破坏 core。

## 原则 8 边界(IPython 不死,被 core 挡一块)

agent 活在 IPython 里,原则上能 `from prism.model import OpenAIModel; OpenAIModel().chat(...)` 直接调模型、绕过 scribe。"不可绕过"在 IPython 环境里**唯一可能的物理实现** = core loop 对 agent 是**黑盒不可达**。

| agent 能直接碰 | agent 只能经 core 碰 |
|----------------|----------------------|
| 世界对象(造工具、造知识) | 主模型(model backend) |
| 读写自己的认知树(当 data) | loop 流程 |
| | 直觉阶段(scribe) |

**IPython 还在,agent 还是活对象,只是"无所不能"被 core 这堵墙挡了一块——恰恰挡住"绕过直觉"那一块。** 这跟"递归不被绕过"是一回事:不可绕过 = agent 够不到 loop。

> **【open】** 原则 8 边界的精确切法(哪些 model 访问点必须经 core)——待 loop 实际流程定稿时定。

## 确定 vs open

- ✅ core = loop(搜索循环)+ Forest 契约 + ABCs,硬不可变,不认识树实例
- ✅ 不可变 = 直觉不可绕过的物理实现
- ✅ CognitiveHook = 第 4 套自举(认知自举),空钩子退化为现状
- ✅ 原则 10 修正:core 硬不可变,删 guard 放行
- ✅ 原则 8 边界:agent 够不到 core loop/model backend
- 🟡 loop 搜索循环的精确结构 —— [cycle.md](cycle.md)
- 🟡 原则 8 边界精确切法 —— loop 定稿时定
