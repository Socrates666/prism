"""tests/test_forest.py — SQLiteForest 认知树测试(RLM Phase B)。

覆盖(plan/rlm/tree.md + persistence.md):
  - 节点 CRUD + causes 父边自动建
  - subtree(causes 子树, 横向分治)
  - walk 两轴:causes(搜索链)/ based_on(自指链, 套娃)
  - mark(失败回溯)+ 状态保留
  - 任务隔离(多棵树)
  - 持久化(重开 DB 数据存活)
"""
import pytest
from prism.cognitive import (THINKING, CONTEXT, ACTIVE, FAILED, SUCCESS,
                               CAUSES, BASED_ON, PRODUCES)
from prism.forest import SQLiteForest


@pytest.fixture
def forest(tmp_path):
    f = SQLiteForest(tmp_path / "f.db", session_id="s1")
    yield f
    f.close()


def test_add_node_returns_id_and_get(forest):
    nid = forest.add_node(category=THINKING, type="thought", content="解析仓库")
    assert nid > 0
    node = forest.get(nid)
    assert node["category"] == THINKING
    assert node["type"] == "thought"
    assert node["content"] == "解析仓库"
    assert node["status"] == ACTIVE


def test_parent_auto_creates_causes_edge(forest):
    root = forest.add_node(category=THINKING, type="thought", content="根")
    child = forest.add_node(category=THINKING, type="action", content="子", parent=root)
    # causes: parent → child
    walked = forest.walk(root, CAUSES)
    assert len(walked) == 1
    assert walked[0]["id"] == child


def test_subtree_includes_root_and_descendants(forest):
    t1 = forest.add_node(category=THINKING, type="thought", content="T1", parent=None)
    t2 = forest.add_node(category=THINKING, type="thought", content="T2", parent=t1)
    t3 = forest.add_node(category=THINKING, type="thought", content="T3", parent=t2)
    sub = forest.subtree(t1)
    ids = [n["id"] for n in sub]
    assert ids == [t1, t2, t3]   # root + 全部 causes 后代, 按时间序


def test_new_root_starts_new_tree_isolation(forest):
    a = forest.add_node(category=THINKING, type="thought", content="任务A根")
    b = forest.add_node(category=THINKING, type="thought", content="任务B根")
    forest.add_node(category=THINKING, type="thought", content="A子", parent=a)
    trees = forest.trees()
    assert len(trees) == 2   # 两个任务 = 两棵树
    assert forest.get(a)["tree_id"] != forest.get(b)["tree_id"]


def test_based_on_self_reference_chain(forest):
    """based_on 轴: 自指链(套娃)。reflection based_on thought; reflection2 based_on reflection。"""
    thought = forest.add_node(category=THINKING, type="thought", content="失败的方法")
    refl = forest.add_node(category=THINKING, type="reflection", content="我总是自顶向下", parent=thought)
    refl2 = forest.add_node(category=THINKING, type="reflection", content="我反思时倾向X", parent=refl)
    # refl 基于失败的方法; refl2 基于 refl(套娃)
    forest.add_edge(refl, BASED_ON, thought)
    forest.add_edge(refl2, BASED_ON, refl)
    # walk refl 沿 based_on → thought
    assert [n["id"] for n in forest.walk(refl, BASED_ON)] == [thought]
    # walk refl2 沿 based_on → refl(1 跳); 深度限制验证
    assert [n["id"] for n in forest.walk(refl2, BASED_ON, depth=1)] == [refl]


def test_causes_and_based_on_are_independent_axes(forest):
    """两轴独立: causes 走搜索链, based_on 走自指链。同一节点两轴可并存。"""
    t1 = forest.add_node(category=THINKING, type="thought", content="T1")
    t2 = forest.add_node(category=THINKING, type="thought", content="T2", parent=t1)
    refl = forest.add_node(category=THINKING, type="reflection", content="反思T1", parent=t2)
    forest.add_edge(refl, BASED_ON, t1)   # 跨越 causes 树的自指回环
    # refl 在 causes 树里是 t2 的子(t2→refl); 但 based_on 指回 t1
    assert t1 in [n["id"] for n in forest.walk(refl, BASED_ON)]
    assert refl in [n["id"] for n in forest.walk(t1, CAUSES)] or refl in [n["id"] for n in forest.subtree(t1)]


def test_mark_failed_backtrack(forest):
    """失败回溯: 标 failed, frontier 回父。status 保留在节点。"""
    root = forest.add_node(category=THINKING, type="thought", content="根")
    dead = forest.add_node(category=THINKING, type="thought", content="撞墙的支", parent=root)
    forest.mark(dead, FAILED)
    assert forest.get(dead)["status"] == FAILED
    assert forest.get(root)["status"] == ACTIVE   # 父仍是 active(frontier 回到这)


def test_produces_bridge_thinking_to_context(forest):
    """bridge 边: thinking(action) produces context(result)。"""
    action = forest.add_node(category=THINKING, type="action", content="read auth.py")
    result = forest.add_node(category=CONTEXT, type="result", content="200 行", parent=action)
    forest.add_edge(action, PRODUCES, result)
    assert [n["id"] for n in forest.walk(action, PRODUCES)] == [result]
    assert forest.get(result)["category"] == CONTEXT


def test_persistence_reopen(tmp_path):
    """重开 DB, 节点/边/状态存活。"""
    db = tmp_path / "persist.db"
    f1 = SQLiteForest(db, session_id="s1")
    nid = f1.add_node(category=THINKING, type="thought", content="跨会话存活")
    f1.mark(nid, SUCCESS)
    f1.close()
    f2 = SQLiteForest(db, session_id="s1")
    node = f2.get(nid)
    assert node["content"] == "跨会话存活"
    assert node["status"] == SUCCESS
    f2.close()


def test_null_forest_degrades():
    """NullForest 全 no-op(agent 退化为无认知层)。"""
    from prism.cognitive import NullForest
    nf = NullForest()
    assert nf.add_node(category=THINKING, type="thought", content="x") == -1
    assert nf.subtree(1) == []
    assert nf.walk(1, BASED_ON) == []
    assert nf.get(1) is None


# ── prune: 剪枝(子树压成摘要节点, cycle.md 第三触发器) ──
def test_prune_collapses_subtree_to_summary(forest):
    """prune: 子树压成一个 summary 节点, 旧节点物理删除。"""
    root = forest.add_node(category=THINKING, type="thought", content="根")
    c1 = forest.add_node(category=THINKING, type="thought", content="c1", parent=root)
    c2 = forest.add_node(category=CONTEXT, type="result", content="c2", parent=c1)
    sid = forest.prune(root, "子树摘要")
    assert sid > 0
    summary = forest.get(sid)
    assert summary["type"] == "summary"
    assert summary["content"] == "子树摘要"
    assert summary["category"] == THINKING
    # 子树节点已物理删除
    assert forest.get(root) is None
    assert forest.get(c1) is None
    assert forest.get(c2) is None
    # root 无 parent → summary 成为新树根
    assert summary["parent_id"] is None


def test_prune_summary_inherits_causes_position(forest):
    """prune: summary 占 root 的 causes 位置(parent=root 的父)。"""
    top = forest.add_node(category=THINKING, type="thought", content="顶")
    sub_root = forest.add_node(category=THINKING, type="thought", content="子树根", parent=top)
    forest.add_node(category=THINKING, type="thought", content="叶", parent=sub_root)
    sid = forest.prune(sub_root, "摘要")
    summary = forest.get(sid)
    assert summary["parent_id"] == top            # 占 sub_root 的位置
    # top 的 causes 子现在是 summary(不再是 sub_root)
    assert [n["id"] for n in forest.walk(top, CAUSES)] == [sid]


def test_prune_reconnects_external_based_on(forest):
    """prune: 子树外指向子树内的入边重连到 summary(保外部认知关联)。"""
    ext = forest.add_node(category=THINKING, type="reflection", content="外部反思")
    root = forest.add_node(category=THINKING, type="thought", content="根")
    c1 = forest.add_node(category=THINKING, type="thought", content="c1", parent=root)
    forest.add_edge(ext, BASED_ON, c1)            # 外部 based_on 子树内 c1
    sid = forest.prune(root, "压扁")
    # ext 的 based_on 重连到 summary(c1 已删, 但关联不丢)
    assert [n["id"] for n in forest.walk(ext, BASED_ON)] == [sid]


def test_prune_empty_summary_returns_minus1_unchanged(forest):
    """prune: 空 summary 返回 -1 且不改树(原子守门)。"""
    root = forest.add_node(category=THINKING, type="thought", content="根")
    c1 = forest.add_node(category=THINKING, type="thought", content="c1", parent=root)
    assert forest.prune(root, "") == -1
    assert forest.prune(root, "   ") == -1
    # 树原封不动
    assert forest.get(root) is not None
    assert forest.get(c1) is not None


def test_prune_nonexistent_root_returns_minus1(forest):
    """prune: root 不存在 → -1。"""
    assert forest.prune(99999, "x") == -1


def test_null_forest_prune_degrades():
    """NullForest.prune 也 no-op(返回 -1)。"""
    from prism.cognitive import NullForest
    assert NullForest().prune(1, "x") == -1
