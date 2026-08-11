"""prism/cognitive.py — 认知层核心契约(RLM 认知层 Phase A)。

不可变 core 的认知层 ABC(plan/rlm/core.md):
  - Forest:           认知树存储契约(一树两轴: causes 搜索 / based_on 自指)
  - CognitiveHook:    认知自举 hook(第 4 套自举, 与 emit/memory/patch 同构)
  - IntuitionBackend: 直觉(scribe)契约 —— 小模型导航树拼 search-state

设计铁律:
  - 机制进 core(契约), 策略进 ext/(实现)
  - 空实现(NullForest/NULL_HOOK/NullIntuition)= agent 退化为现状(无认知层)
  - Phase A 验收: 现有测试全绿(空实现 = 逐字节现状)

认知周期(plan/rlm/cycle.md): 直觉→思考→行动→观察。
  - 直觉 = READ(选/排/临时压), 每次循环, 不可绕过(焊进 core)
  - 改树 = WRITE(加节点/标 failed/剪枝), 结构阈值触发
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


# ── 节点类别(plan/rlm/tree.md: 思维 / 上下文, 用不同边) ──
THINKING = "thinking"   # 思维节点: thought / action / reflection / pattern
CONTEXT = "context"     # 上下文节点: result / observation / fact

# ── 节点状态(round 8 回溯) ──
ACTIVE = "active"
FAILED = "failed"
SUCCESS = "success"

# ── 边关系(两轴 + bridge) ──
CAUSES = "causes"           # thinking→thinking, 树, 搜索/回溯(横向分治)
BASED_ON = "based_on"       # thinking→thinking(任意), 图, 自指/套娃(纵向)
PRODUCES = "produces"       # thinking→context, 挂载(思维产出上下文)
EVIDENCES = "evidences"     # context→thinking, 接地(上下文支撑思维)
TEMPORAL = "temporal"       # 时间先后(默认边)
REFERENCES = "references"   # 跨树引用(森林内检索)


class Forest(ABC):
    """认知树存储契约(CognitiveBackend)。core 只定义接口, 实现在 ext/。

    一树两轴(plan/rlm/tree.md):
      - causes 轴: thinking↔thinking, 树结构(单父), 搜索/失败回溯
      - based_on 轴: thinking→thinking(任意), 图(多链/跨树), 自指/套娃
      - bridge 边: thinking↔context(produces/evidences)
    两轴在同一批节点上交织 —— 节点有 1 个 causes 父(搜索位置) + 任意多 based_on 链。
    """

    @abstractmethod
    def add_node(self, *, category: str, type: str, content: str,
                 parent: int | None = None, status: str = ACTIVE) -> int:
        """加节点。parent = causes 父(搜索树位置); 无 parent = 树根。返回 node id。"""

    @abstractmethod
    def add_edge(self, src: int, relation: str, dst: int) -> None:
        """加边。relation ∈ causes/based_on/produces/evidences/temporal/references。"""

    @abstractmethod
    def mark(self, node_id: int, status: str) -> None:
        """标节点状态(active/failed/success)。失败回溯: mark(node, FAILED)。"""

    @abstractmethod
    def get(self, node_id: int) -> dict | None:
        """取节点(含 category/type/status/content/parent/created_at)。"""

    @abstractmethod
    def subtree(self, root: int) -> list[dict]:
        """causes 子树(横向分治 / spawn 子树)。"""

    @abstractmethod
    def walk(self, node: int, relation: str, depth: int | None = None) -> list[dict]:
        """沿指定边递归走。causes→搜索链; based_on→自指链(套娃路径)。"""

    # ── 搜索辅助(带默认实现, SQLiteForest override 成索引友好) ──
    def last_tree_id(self) -> int | None:
        """最新树的 tree_id; None=本 session 无节点。
        直觉 search-state 的入口(O(1) 优于 trees() 全扫)。
        默认实现走 trees()[-1]; SQLiteForest override 用 id 倒序 LIMIT 1。
        """
        ts = self.trees()
        return ts[-1] if ts else None

    def recent_in_tree(self, tree_id: int, *, type: str | None = None,
                       status: str | None = None, limit: int | None = None) -> list[dict]:
        """某树内按 (type, status) 过滤的最近 limit 个节点(时间正序)。
        直觉热路径用这个: 期望 O(limit), 不随树规模线性增长。
        默认实现走 nodes_in_tree + 内存过滤(O(K)); SQLiteForest override 走覆盖索引 O(L)。
        """
        nodes = self.nodes_in_tree(tree_id)
        if type is not None:
            nodes = [n for n in nodes if n.get("type") == type]
        if status is not None:
            nodes = [n for n in nodes if n.get("status") == status]
        if limit is not None:
            nodes = nodes[-limit:]
        return nodes

    def prune(self, root: int) -> int:
        """剪枝: 老子树压成摘要节点存回(plan/rlm/cycle.md 第三触发器)。
        默认 no-op(子类 override)。返回摘要节点 id, 未实现返回 -1。"""
        return -1


class NullForest(Forest):
    """空实现: 全 no-op, add_node 返回 -1。agent 退化为无认知树(= 现状)。"""

    def add_node(self, *, category, type, content, parent=None, status=ACTIVE) -> int:
        return -1

    def add_edge(self, src, relation, dst) -> None:
        return None

    def mark(self, node_id, status) -> None:
        return None

    def get(self, node_id) -> dict | None:
        return None

    def subtree(self, root) -> list:
        return []

    def walk(self, node, relation, depth=None) -> list:
        return []


class CognitiveHook(ABC):
    """认知自举 hook(第 4 套自举, plan/rlm/core.md)。

    与 hooks["emit"](显示自举)/ memory(状态自举)/ patch(行为自举)同构。
    空实现(NULL_HOOK)= agent 退化为普通 agent(无认知层)。
    比 patch 松(广播 fire-and-forget, 非拦截)/ 比硬编码紧(固定广播点)。
    """

    def on_cognitive_event(self, agent, event: dict) -> None:
        """观察认知事件(thought/action/result/reflection/promote)。默认 no-op。"""
        return None

    def select_context(self, agent, state: dict) -> list[dict]:
        """返回额外上下文(注进 prompt 的 search-state)。默认空(不注入)。"""
        return []

    def on_promote(self, agent, node_id: int) -> str | None:
        """把节点固化为实体(skill)。默认 no-op, 返回 None。"""
        return None


# 空钩子: 全 no-op。Agent 默认持 [NULL_HOOK] → 行为 = 现状。
NULL_HOOK = CognitiveHook()


class IntuitionBackend(ABC):
    """直觉(scribe)契约 —— 小模型导航树拼 search-state(plan/rlm/cycle.md)。

    READ 操作(选/排/临时压), 不写回树。空实现(NullIntuition)= 无直觉注入。
    α(默认): 小模型当评估器/导航(真在搜), 主模型当驱动器(做回溯决策)。
    """

    @abstractmethod
    def select_context(self, agent, state: dict) -> list[dict]:
        """读树 → 选/排/压 → search-state(根→frontier 路径 + failed 兄弟 + 近期 reflection)。"""


class NullIntuition(IntuitionBackend):
    """空直觉: 不注入任何上下文。agent 用现状 context。"""

    def select_context(self, agent, state) -> list:
        return []
