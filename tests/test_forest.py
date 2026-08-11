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


def test_cross_thread_access(tmp_path):
    """跨线程访问 forest(actor 线程用 TUI 线程建的连接)—— check_same_thread=False + Lock 不炸。
    复现截图 bug: SQLite objects created in a thread can only be used in that same thread。"""
    import threading
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    root = forest.add_node(category=THINKING, type="thought", content="根")  # 主线程建
    errors = []

    def worker():
        try:
            trees = forest.trees()                              # 另一线程读
            nodes = forest.nodes_in_tree(trees[0])
            forest.add_node(category=THINKING, type="thought",  # 另一线程写
                            content="子", parent=root)
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert not errors, f"跨线程访问出错: {errors}"
    forest.close()
