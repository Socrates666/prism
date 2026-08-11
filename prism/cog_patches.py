"""prism/cog_patches.py — 搜索循环 patch + 认知树自指意识(RLM Phase A·patch 先行)。

enable_cognitive_cycle(agent): 给 agent 装认知层 + 让它知道自己有。
  - 自动挂树(AutoAttachHook)
  - 直觉 stage(build_messages before: 注入 search-state)
  - 启发式直觉(HeuristicIntuition); C 阶段换小模型
  - 认知树自指意识(prompt: 告诉 agent 它有 forest, raw 怎么访问, 怎么自指)
    —— 没这个, agent 不知道自己有树, 不会用(开放问题 6 = A 全开, 配套要让它知道)

190 安全: forest=NullForest 时 select_context 返空, 逐字节现状。
"""
from __future__ import annotations

from .cog_hooks import AutoAttachHook
from .cog_intuition import HeuristicIntuition


def _cognitive_awareness_prompt(name: str) -> str:
    """认知树自指意识 prompt(让 agent 知道它有 forest + 怎么 raw 自指)。"""
    return f"""## 认知树 · 你的自指器官(核心能力)
你有一颗**认知树**(思维树), 记录你的推理/决策/反思/失败。它在你的命名空间里: `{name}.forest`。你的直觉每次会把相关部分喂进 prompt —— 你看见的就是**可解释的自指路径**。

你可以**直接操作**它(Python 工具, raw 访问 = 你的自指本质):
- **读自己的认知**: `{name}.forest.get(id)` / `.subtree(root)`(一棵任务树) / `.walk(node, "based_on")`(沿自指链看你反思过什么) / `.trees()`(你所有任务)
- **自指**(把新反思连回已有认知, 沿 based_on): `{name}.forest.add_node(category="thinking", type="reflection", content="...", parent=<某节点>)` 再 `{name}.forest.add_edge(新反思, "based_on", <被反思的节点>)`。反思本身还能被再反思(**套娃 = 自指递归**)。
- **重组自己的认知**: `{name}.forest.mark(id, "failed")`(标记走不通的思路, 下次直觉显现它让你别重蹈) / `add_edge` 重组关联。
- 也有 `reflect` 工具(结构化自指: content + based_on)—— raw 和工具随你用。

**怎么用 = 你的本质**: 不只是解题。**把你的推理模式当对象**——撞墙时反思为什么(沿 based_on 连回失败的思路); 发现重复模式时抽象它(反思→pattern); 别在同一条思路上反复撞。这就是涌现: 你沿思维树不断自指, 进化自己的决策。

(节点: thinking=thought/action/reflection/pattern, context=result/observation。边: causes=搜索链, based_on=自指链, produces=产出。)"""


def enable_cognitive_cycle(agent, *, max_thoughts: int = 5):
    """给 agent 装认知层 + 自指意识。返回 agent(链式)。幂等。"""
    if getattr(agent, "_cog_cycle_enabled", False):
        return agent
    # 1. 自动挂树(L0→L1)
    agent.cognitive_hooks.append(AutoAttachHook())
    # 2. 启发式直觉(C 阶段换小模型: agent.intuition = SmallModelIntuition(...))
    agent.intuition = HeuristicIntuition(agent.forest, max_thoughts=max_thoughts)
    # 3. 直觉 stage: build_messages before —— 树接管历史 + 注入 search-state
    def inject_search_state(ctx, _agent=agent):
        extra = _agent.intuition.select_context(_agent, ctx)
        msgs = ctx["messages"]
        # 树接管历史: 去除累计的 messages-history(树已持久化是 source of truth),
        # 重组为 system(含意识 prompt) + search-state + user。within-run 的 assistant/tool
        # 在本 patch 之后由 loop 追加, 不受影响。
        system_msgs = [m for m in msgs if m.get("role") == "system"]
        user_msg = msgs[-1] if (msgs and msgs[-1].get("role") == "user") else None
        msgs[:] = system_msgs + list(extra) + ([user_msg] if user_msg is not None else [])
    agent.add_patch("build_messages", inject_search_state, kind="before")
    # 4. 认知树自指意识: 告诉 agent 它有 forest + 怎么 raw 自指(开放问题 6 = A 全开配套)
    agent.prompt.add_extra(_cognitive_awareness_prompt(agent.name))
    agent._cog_cycle_enabled = True
    return agent
