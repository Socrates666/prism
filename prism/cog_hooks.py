"""prism/cog_hooks.py — 认知层 hook(RLM Phase B)。

AutoAttachHook: L0→L1 自动挂树(plan/rlm/tree.md)。
  监听 Agent 广播的认知事件(thought/action/result)→ 自动挂 forest 节点(causes 链)。
  零门槛: 接上 cognitive_hooks=[AutoAttachHook()] 即用, agent 不用主动调任何东西。

MVP 语义: 线性 causes 链(每节点 parent=上一节点)。
  回溯/bridge 边(produces)由 search-cycle loop(A1/B5)升级时细化。
"""
from __future__ import annotations
from .cognitive import CognitiveHook, THINKING, CONTEXT


class AutoAttachHook(CognitiveHook):
    """emit 认知事件 → forest 节点(causes 链)。每 agent 实例一个(持 _last 状态)。"""

    def __init__(self):
        self._last: int | None = None   # 上一节点 id(causes 链尾)

    def on_cognitive_event(self, agent, event: dict) -> None:
        t = event.get("type")
        if t == "thought":
            nid = agent.forest.add_node(
                category=THINKING, type="thought",
                content=event.get("content", ""), parent=self._last)
        elif t == "action":
            name = event.get("name", "?")
            nid = agent.forest.add_node(
                category=THINKING, type="action",
                content=f"{name}({event.get('args')})", parent=self._last)
        elif t == "result":
            nid = agent.forest.add_node(
                category=CONTEXT, type="result",
                content=event.get("content", ""), parent=self._last)
        else:
            return
        if nid != -1:
            self._last = nid
