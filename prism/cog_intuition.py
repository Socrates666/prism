"""prism/cog_intuition.py — 启发式直觉(RLM Phase A·patch 先行)。

HeuristicIntuition: 无小模型的直觉 MVP。读 forest 拼 search-state:
  最近 thought + 失败的尝试 + 反思 → 注进 prompt(让模型看见自己的认知树 = 可解释路径)。

C 阶段(plan/rlm Phase C): 换成小模型 IntuitionBackend(智能选/排/临时压)。
本类是对照组/降级实现 —— 涌现实验里它是 baseline, 小模型是实验组。

设计(plan/rlm/cycle.md): 直觉 = READ(不写回树), 每次循环, 不可绕过。
"""
from __future__ import annotations
from .cognitive import IntuitionBackend


class HeuristicIntuition(IntuitionBackend):
    """启发式直觉: recency + 失败/反思 显现, 无模型。"""

    def __init__(self, forest, max_thoughts: int = 5):
        self.forest = forest
        self.max_thoughts = max_thoughts

    def select_context(self, agent, state: dict) -> list[dict]:
        trees = self.forest.trees()
        if not trees:
            return []
        nodes = self.forest.nodes_in_tree(trees[-1])   # 最新一棵树
        thoughts = [n for n in nodes if n["type"] == "thought"][-self.max_thoughts:]
        failed = [n for n in nodes if n["status"] == "failed"]
        reflections = [n for n in nodes if n["type"] == "reflection"]
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
        return [{"role": "system", "content": "\n".join(lines)}]
