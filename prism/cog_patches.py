"""prism/cog_patches.py — 搜索循环 patch(RLM Phase A·patch 先行, plan/rlm/route.md A1)。

enable_cognitive_cycle(agent): 把搜索循环装到 agent 上(ext/ patch 先行, loop 本体不动)。
  - 自动挂树(AutoAttachHook)
  - 直觉 stage(build_messages before patch: 注入 search-state, 让模型看见认知树)
  - 启发式直觉(HeuristicIntuition); C 阶段换小模型

190 安全: forest=NullForest 时 select_context 返空, patch 注入空, 逐字节现状。
涌现证成后(plan/rlm/route.md), 这套 patch 可 promote 进 core loop(甲方案)。
"""
from __future__ import annotations

from .cog_hooks import AutoAttachHook
from .cog_intuition import HeuristicIntuition


def enable_cognitive_cycle(agent, *, max_thoughts: int = 5):
    """给 agent 装搜索循环 patch。返回 agent(链式)。

    幂等: 重复调用不重复装 hook/patch。
    """
    # 1. 自动挂树(L0→L1)
    if not any(isinstance(h, AutoAttachHook) for h in agent.cognitive_hooks):
        agent.cognitive_hooks.append(AutoAttachHook())
    # 2. 启发式直觉(C 阶段换小模型: agent.intuition = SmallModelIntuition(...))
    if not isinstance(agent.intuition, HeuristicIntuition):
        agent.intuition = HeuristicIntuition(agent.forest, max_thoughts=max_thoughts)
    # 3. 直觉 stage: build_messages before —— 注入 search-state
    if not _has_build_messages_patch(agent):
        def inject_search_state(ctx, _agent=agent):
            extra = _agent.intuition.select_context(_agent, ctx)
            for m in extra:
                ctx["messages"].append(m)
        agent.add_patch("build_messages", inject_search_state, kind="before")
    return agent


def _has_build_messages_patch(agent) -> bool:
    """粗判是否已装 cog patch(查 PatchRegistry 内部 before 列表)。"""
    try:
        return bool(agent.patches._before["build_messages"])
    except Exception:
        return False
