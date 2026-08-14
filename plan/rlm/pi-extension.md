# 可行性研究:用 pi 扩展实现「思维树嵌入 ReAct」

> **问题**:能否做一个 `@earendil-works/pi-coding-agent` 扩展,把 RLM 认知层(认知树 +
> 直觉 + 自指)嵌入 pi 自己的 ReAct 循环,从而**取代** prism 在 Python 里自建循环 + patch 接入的做法?
>
> **结论**:**可行,且 fit 出乎意料地干净** —— prism 当前的每一个嵌入点都有 1:1 的 pi 扩展对应,
> 其中 `custom-compaction.ts` 官方示例几乎就是「scribe 小模型」模式的现成原型。
> 唯一的硬 gap(原生树遍历循环)prism 自己目前也没做,所以不算倒退。
>
> **状态**:研究产物(2026-08-12),决策权在用户:做(pi 扩展路线)/ 不做(留 prism Python 路线)。

---

## 0 · 术语对齐

| 词 | 含义 |
|----|------|
| pi | `@earendil-works/pi-coding-agent`(TS/Node,pi-coding-agent 本体) |
| ReAct | function-calling agent loop(prism 的 `agent_loop.py` / pi 的 agent loop) |
| 思维树 | RLM 认知树/forest:一树两轴(causes 搜索 / based_on 自指)+ 直觉(scribe) |
| 嵌入 | 把思维树焊进 ReAct 循环:每轮注入 search-state(直觉 READ)+ 观察挂树(WRITE)+ reflect 工具 |

---

## 1 · 结论先行

**pi 扩展能完整覆盖 prism 当前"思维树对 ReAct 的嵌入"。** 而且有三个意外红利:

1. **`context` 事件 = 直觉 READ 的天然落点**,且按 pi lifecycle **每轮 turn 都触发**(包括工具回合后),
   精确满足「直觉每次 loop、不可绕过」(plan/rlm/cycle.md 铁律)。
2. **`session_before_compact` + `custom-compaction.ts` 官方示例** 已经演示「用另一个便宜小模型做摘要」
   —— 这正是 prism Phase C 的 scribe/直觉小模型模式,几乎可直接搬。
3. **prism 的 D1–D5「对齐 pi」工作全免费**:事件命名 / state / system-prompt override / steer / compact
   这些 prism 花了一轮轮补的语义对齐,在 pi 扩展里天然就是 pi 语义。

---

## 2 · 嵌入点映射表(prism → pi)

> 这是本研究的核心证据。每一行 = prism 当前怎么做 → pi 扩展怎么等价实现。

| # | 认知层需求 | prism 现状实现 | pi 扩展对应 hook | 证据 |
|---|-----------|---------------|-----------------|------|
| 1 | **直觉 READ**:每轮把 forest 拼成 search-state 注进 prompt,不可绕过 | `cog_patches.py` 的 `build_messages before` patch(`inject_search_state`)重写 messages | **`context` 事件**(每轮 LLM 调用前,`event.messages` 深拷贝,`return {messages}` 替换) | extensions.md:648 + lifecycle:290 |
| 2 | **树接管历史**:forest 是 source of truth,每轮重组 messages(system + search-state + user) | 同上 patch,去掉累计 history | `context` 事件 wholesale replace(返回全新 messages 数组) | extensions.md:648 |
| 3 | **自动挂树**(WRITE):观察 thought/action/result 挂 causes 节点 | `AutoAttachHook.on_cognitive_event` 监听 emit | `message_end`(thought)+ `tool_call`/`tool_result`/`tool_execution_end`(action/result) | extensions.md:588,751,814 |
| 4 | **reflect 工具**(自指入口,沿 based_on,可套娃) | `cog_tools.py` 的 `reflect` Tool | `pi.registerTool({name:"reflect",...})`(可运行时注册) | dynamic-tools.ts |
| 5 | **剪枝/压缩**:结构阈值触发,小模型把老子树压成摘要节点 | `Forest.prune()` + Phase C 未做 | **`session_before_compact`** + custom-compaction.ts(示例已用 Gemini Flash 小模型) | extensions.md:451 + 示例 |
| 6 | **持久化 Forest**(SQLite 跨会话) | `forest.py` SQLiteForest(Agent 持对象) | 扩展模块级 state + `session_start`/`session_shutdown` 管连接;`better-sqlite3` | extensions.md:220 |
| 7 | **认知树自指意识 prompt**(告诉 agent 它有 forest + 怎么 raw 自指) | `_cognitive_awareness_prompt` add_extra | `before_agent_start`(改 systemPrompt)或 `context`(注入);对齐 pi appendSystemPrompt | extensions.md:521 |
| 8 | **改 loop 控制流**(线性 → 搜索循环 backtrack) | route.md A1 标 ✅ 但 `agent_loop.py` 实际仍线性,patch 模拟 | `context` 每轮重写 + `ctx.abort()` 中断 + 重注入;**非原生 tree-walk** | 见 §3 |

**每一个点都有对应。** 第 1/2/5 三个最关键的点(直觉/接管历史/剪枝),pi 的 hook 甚至比 prism 的 patch 更直接。

---

## 3 · 唯一的硬 gap —— 以及为什么不算倒退

**gap:pi 的 loop 是线性 turn-based,没有「原生树遍历 / 跳到兄弟支」的控制流原语。**

prism 的设计(plan/rlm/route.md A1)原本想「把 `agent_loop.py` 从线性重写为搜索循环 explore/evaluate/backtrack」。但实读 `prism/agent_loop.py` 发现:**它至今仍是线性 function-calling loop**,「搜索循环」是通过 patch 在 messages 层模拟的(patch-first,git log:`rlm A1-patch: 搜索循环 patch 先行`)。所以——

> **prism 自己当前也没做原生 tree-walk loop;两边都在 messages 层模拟搜索。** 选 pi 扩展在这点上不是倒退,是平手。

在 pi 里模拟 backtrack 的手段:
- **标 failed**:扩展在自己持的 Forest 里标(纯本地 state)。
- **显现 + 引导**:下一轮 `context` 注入「你上一条思路(#X)failed,从 #Y 重新想」。
- **强制重置**:`ctx.abort()` 中断当前 run,再用新 context 重启。
- 这与 prism patch 模拟是同一套思路,只是宿主从 Python patch 换成 TS event handler。

---

## 4 · 得失(pi 扩展 vs prism Python 路线)

### ✅ 选 pi 扩展会**得到**

| 红利 | 说明 |
|------|------|
| **D1–D5 对齐全免费** | prism 花数轮补的事件命名/state/system-prompt/steer/compact,在 pi 上天然就是 pi 语义(alignment-pi.md 全表闭合) |
| **成熟 loop / TUI / 工具 / provider** | 直接用 pi 的流式 / abort / retry / 并行工具 / subagent / 子进程隔离,不用自造 |
| **`custom-compaction.ts` 现成原型** | scribe 小模型模式几乎可直接搬,省 Phase C 一半 |
| **少维护一个 runtime** | 不用维护 prism 的 model.py / agent_loop.py / shell.py,只维护认知层逻辑 |
| **跨进程 subagent 共享 Forest** | pi subagent = 独立进程,但都能挂同一个 SQLite Forest 文件(天然跨进程) |

### ⚠️ 选 pi 扩展会**失去**

| 代价 | 说明 | 严重度 |
|------|------|:----:|
| **IPython 共享命名空间(原则 8)** | prism 灵魂:agent 能 `name.forest.get(id)` raw 持对象自指。pi 无此能力,raw 自指降级为 forest-query 工具 | 中(但 reflect 工具路径够用,prism 本就有 tool + raw 双路) |
| **同进程多 agent actor(原则 15)** | prism 线程+inbox+inject;pi subagent=独立进程 | 低(与认知层正交,是外壳层差异) |
| **core 硬不可变 / guard 护栏(原则 10)** | prism 用 guard.py 拦 agent 写 core 实现「不可绕过」;pi 扩展靠「LLM 运行时无法 unload 扩展」实现 | 低(agent 无法 bypass 自身扩展;只有人类 operator 能禁用,符合需求) |
| **语言**:Python → TypeScript | Forest/SQL/intuition 逻辑要移植 | 中(逻辑量不大,ABC 契约清晰) |

> **关键洞察**:失去的全是**外壳层**差异(原则 8/15 多 agent + IPython);**认知层本身**(Forest ABC + 两轴 + 直觉 READ/WRITE + reflect)与语言、与外壳正交,移植零语义损失。

---

## 5 · 如果做:扩展长什么样(草图)

```
.pi/extensions/rlm-cognitive/        # 或 ~/.pi/agent/extensions/
├── index.ts                         # factory: pi.on(...) + registerTool
├── forest.ts                        # SQLiteForest(prism/forest.py 移植)
├── intuition.ts                     # 直觉:select_context → search-state(prism/cog_intuition.py)
├── nodes.ts                         # 节点/边常量 + 树操作(prism/cognitive.py ABC)
└── reflect-tool.ts                  # reflect 工具注册(prism/cog_tools.py)
```

`index.ts` 骨架(对应映射表 1–7):

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { openForest } from "./forest";
import { selectContext } from "./intuition";

export default function (pi: ExtensionAPI) {
  let forest = null;                 // 模块级长生命周期 state(§映射 6)

  pi.on("session_start", (_e, _ctx) => {           // §6 启动 Forest
    forest = openForest(".prism/forest.db");
  });
  pi.on("session_shutdown", () => { forest?.close(); });

  // §1+2 直觉 READ:每轮重写 messages = system + search-state + user
  pi.on("context", async (event, ctx) => {
    if (!forest) return;
    const searchState = await selectContext(forest);   // 选/排/临时压(不写回)
    const sys = event.messages.filter(m => m.role === "system");
    const lastUser = event.messages.filter(m => m.role === "user").at(-1);
    return { messages: [...sys, ...searchState, ...(lastUser ? [lastUser] : [])] };
  });

  // §3 自动挂树:thought/action/result → causes 节点
  pi.on("message_end", e => forest?.addThinking(e.text));          // thought
  pi.on("tool_execution_end", e => forest?.addContext(e.result));  // result

  // §4 reflect 工具 = 自指入口(沿 based_on,可套娃)
  pi.registerTool({
    name: "reflect", label: "Reflect",
    description: "反思自己的某 subtree,产 reflection 节点,沿 based_on 连回(可套娃)",
    parameters: ReflectParams,
    async execute(_id, { content, basedOn }) {
      const r = forest.addThinking(content, { type: "reflection" });
      if (basedOn) forest.addEdge(r, "based_on", basedOn);   // 自指链
      return { content: [{ type: "text", text: `reflected #${r} based_on #${basedOn}` }] };
    },
  });

  // §5 剪枝:小模型把老子树压成摘要节点(搬 custom-compaction.ts 思路)
  pi.on("session_before_compact", async (event, ctx) => {
    const summaryNode = forest.pruneByThreshold();            // 结构阈值触发
    if (!summaryNode) return;                                  // 不达标 → 默认压缩
    return { compaction: { summary: summaryNode.content, ...event.preparation } };
  });

  // §7 认知树自指意识 prompt
  pi.on("before_agent_start", e => ({ systemPrompt: e.systemPrompt + AWARENESS }));
}
```

> 注:这是**草图**,省略错误处理 / 消息类型适配 / abort 信号。但勾出了「认知层逻辑 ~300 行 TS」的量级,
> 与 prism 当前认知层代码量(`cognitive.py` 144 + `cog_*.py` ~170 + `forest.py` 172 ≈ 500 行)同量级。

---

## 6 · 落地阶段(对齐 prism route.md Phase A–C)

| 阶段 | prism route.md | pi 扩展等价 | 验收 |
|------|---------------|------------|------|
| A Core 契约 | Forest ABC + NullForest(190 测试不破) | `forest.ts` + 空实现(无扩展 = 现 pi 行为) | 空 hook 逐字节现状 |
| B 树 | SQLiteForest 两轴 + auto-attach + reflect + backtrack | `session_start` 开库 + `context`/`tool_*` 挂树 + reflect 工具 | 树跨 session 恢复;reflect 造 based_on |
| C 直觉 | IntuitionBackend 小模型 select_context | `context` handler 里调小模型拼 search-state(搬 custom-compaction 小模型调用法) | 延迟账过关 |
| D 实验 | spawn N 小白鼠对比 | pi subagent 多进程跑,共享 Forest 文件 | 涌现签名有/无 |

**关键**:Phase A 的「190 测试不破」在 pi 里等价于「不装扩展 = 现 pi 行为逐字节不变」—— 空扩展天然满足。

---

## 7 · 决策建议

**如果你最终目标是"让思维树这个能力跑起来、验证自指涌现是否成立"(route.md Phase D 的判官)**:
→ **pi 扩展路线更划算**。省掉维护一个 Python runtime + 一轮轮对齐 pi 的工作,直接站在 pi 成熟 loop 上,
认知层逻辑同量级(~500 行),且有 `custom-compaction.ts` 现成原型。

**如果你最终目标是"探索同进程多 agent + IPython 共享命名空间这种 shell 范式"(原则 8/15)**:
→ **prism Python 路线不可替代**,pi 扩展拿不到 IPython namespace。但注意:这部分与认知层正交,
可以"prism 当外壳 + 认知层逻辑两边共享设计/文档"。

**折中(推荐)**:认知层(Forest ABC / 两轴 / 直觉 / reflect)保持**语言无关的契约文档**(plan/rlm/ 已经是),
prism Python 和 pi 扩展 TS **各做一个实现**作为 A/B 对照 —— Phase D 实验里正好可以当两个 condition 对比。

---

## 附:证据索引(pi 扩展文档)

| hook | 位置 | 能力 |
|------|------|------|
| `context` | extensions.md:648 | 每轮 LLM 调用前改 messages(深拷贝,return 替换)= 直觉 READ |
| `before_agent_start` | extensions.md:521 | 改 systemPrompt + 注入 message = 自指意识 prompt |
| `tool_call` / `tool_result` | extensions.md:751 / 814 | 观察改工具入参/结果 = 挂 action/result 节点 |
| `tool_execution_start/end` | extensions.md:624 | 工具生命周期 |
| `message_start/update/end` | extensions.md:588 | assistant 文本/thinking = 挂 thought 节点 |
| `session_before_compact` | extensions.md:451 | 自定义压缩 = 剪枝/小模型摘要 |
| `registerTool` | dynamic-tools.ts | 运行时注册工具 = reflect |
| 长生命周期 state | extensions.md:220 | 模块级 + session_start/shutdown = 持久化 Forest |
| `ctx.abort()` / `ctx.signal` | extensions.md:1014 | 中断 loop = backtrack 模拟 |
