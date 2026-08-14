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


class SmallModelIntuition(IntuitionBackend):
    """小模型直觉(Phase C): 驻场小模型(glm-4.5-air)读树拼 search-state。

    α(默认, route.md): 小模型当导航员(拼 search-state, READ 不写树), 主模型控搜索。
    性能(C2): _tree_signature 检测新节点 + active_context 缓存(同轮不重触发)。
    降级(C4): 小模型异常/超时 → 退 HeuristicIntuition 启发式(不崩)。
    """
    def __init__(self, forest, small_model, max_nodes: int = 15):
        self.forest = forest
        self.small_model = small_model          # OpenAIModel(model='glm-4.5-air', thinking_level='off')
        self.max_nodes = max_nodes
        self._active_context = None             # 缓存的 search-state
        self._last_sig = None                   # 上次签名(检测新认知事件)
        self._fallback = HeuristicIntuition(forest)   # 降级兜底

    def _tree_signature(self):
        """树状态签名(tree_id, 节点数, 末节点 id)。不变 = 无新认知事件 → 复用缓存。"""
        trees = self.forest.trees()
        if not trees:
            return ()
        nodes = self.forest.nodes_in_tree(trees[-1])
        return (trees[-1], len(nodes), nodes[-1]["id"] if nodes else 0)

    def _gather_nodes(self):
        trees = self.forest.trees()
        if not trees:
            return []
        nodes = self.forest.nodes_in_tree(trees[-1])
        thoughts = [n for n in nodes if n["type"] == "thought"][-self.max_nodes:]
        failed = [n for n in nodes if n["status"] == "failed"]
        refls = [n for n in nodes if n["type"] == "reflection"]
        return thoughts + failed + refls

    def _scribe(self, nodes) -> str | None:
        """小模型把节点拼成 search-state(突出 frontier/失败/反思/模式)。失败返 None(降级)。"""
        node_text = "\n".join(
            f"(#{n['id']} {n['type']}/{n['status']}) {n['content'][:120]}" for n in nodes)
        prompt = (
            "你是认知树的直觉(scribe)。下面是 agent 的认知节点(thought/失败/反思)。"
            "拼一段 search-state 注入主模型: 突出当前思路(frontier)、"
            "明确别重复的失败、点出可用的反思或反复出现的模式。"
            "简洁(<=200字), 中文, 只输出 search-state 文本:\n\n" + node_text)
        try:
            return self.small_model.chat([{"role": "user", "content": prompt}])
        except Exception:
            return None

    def select_context(self, agent, state: dict) -> list[dict]:
        sig = self._tree_signature()
        # C2 快速路径: 同轮无新节点 → 复用缓存(不重调小模型)
        if self._active_context is not None and sig == self._last_sig:
            return self._active_context
        self._last_sig = sig

        nodes = self._gather_nodes()
        if not nodes:
            self._active_context = []
            return []

        content = self._scribe(nodes)
        if not content:                            # C4 降级: 小模型挂 → 启发式兜底
            return self._fallback.select_context(agent, state)

        self._active_context = [{"role": "system", "content": content}]
        try:                                       # 白盒: 直觉事件 → TUI
            agent.emit({"type": "cognitive", "stage": "intuition", "content": content})
        except Exception:
            pass
        return self._active_context
