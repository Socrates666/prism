"""prism/cog_intuition.py — 启发式直觉(RLM Phase A·patch 先行)。

HeuristicIntuition: 无小模型的直觉 MVP。读 forest 拼 search-state:
  最近 thought + 失败的尝试 + 反思 → 注进 prompt(让模型看见自己的认知树 = 可解释路径)。

C 阶段(plan/rlm Phase C): 换成小模型 IntuitionBackend(智能选/排/临时压)。
本类是对照组/降级实现 —— 涌现实验里它是 baseline, 小模型是实验组。

设计(plan/rlm/cycle.md): 直觉 = READ(不写回树), 每次循环, 不可绕过。

复杂度(research/ANALYSIS.md): last_tree_id O(1) + 3× recent_in_tree O(L)。
  不再随总节点数 N / 树规模 K 线性增长 —— 走覆盖索引 top-N。
"""
from __future__ import annotations
from .cognitive import IntuitionBackend


class HeuristicIntuition(IntuitionBackend):
    """启发式直觉: recency + 失败/反思 显现, 无模型。"""

    def __init__(self, forest, max_thoughts: int = 5, max_failed: int = 20):
        self.forest = forest
        self.max_thoughts = max_thoughts
        # failed/reflection 也限上限: search-state 不该随树规模无限膨胀(O(常数))
        self.max_failed = max_failed

    def select_context(self, agent, state: dict) -> list[dict]:
        tid = self.forest.last_tree_id()          # O(1), 替代 trees() 全扫
        if tid is None:
            return []
        thoughts = self.forest.recent_in_tree(
            tid, type="thought", limit=self.max_thoughts)     # O(max_thoughts)
        failed = self.forest.recent_in_tree(
            tid, status="failed", limit=self.max_failed)        # O(max_failed)
        reflections = self.forest.recent_in_tree(
            tid, type="reflection", limit=self.max_failed)     # O(max_failed)
        if not (thoughts or failed or reflections):
            return []
        lines = ["[认知树·直觉 search-state]"]
        if thoughts:
            lines.append("最近思路:")
            for t in thoughts:
                lines.append(f"  - (#{t['id']}) {t['content']}")
        if failed:
            lines.append("失败的尝试(别重复同样的路):")
            for f in failed:
                lines.append(f"  ✗ (#{f['id']}) {f['content']}")
        if reflections:
            lines.append("你的反思:")
            for r in reflections:
                lines.append(f"  ↻ (#{r['id']}) {r['content']}")
        content = "\n".join(lines)
        # 白盒化: 发"直觉"认知事件让 TUI 显示(思维树白盒的重要组成)
        try:
            agent.emit({"type": "cognitive", "stage": "intuition", "content": content})
        except Exception:
            pass
        return [{"role": "system", "content": content}]
