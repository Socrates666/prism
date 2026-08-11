"""tests/test_cog_tools.py — reflect 工具测试(RLM Phase B)。"""
import pytest
from prism.cognitive import THINKING, BASED_ON
from prism.forest import SQLiteForest
from prism.cog_tools import make_reflect_tool


class _FakeAgent:
    """最小 agent 替身(只持 forest, 给 reflect 工具用)。"""
    def __init__(self, forest):
        self.forest = forest


def test_reflect_creates_reflection_node_with_based_on(tmp_path):
    forest = SQLiteForest(tmp_path / "f.db", session_id="s1")
    agent = _FakeAgent(forest)
    # 先有两个被反思的节点(失败的思维)
    t1 = forest.add_node(category=THINKING, type="thought", content="方法A")
    t2 = forest.add_node(category=THINKING, type="thought", content="方法B")
    tool = make_reflect_tool(agent)
    out = tool.execute({"content": "我连用 A/B 都自顶向下, 是分解方式的问题",
                        "based_on": [t1, t2]})
    assert "[反思已记]" in out
    # 找到 reflection 节点
    refls = [n for n in [forest.get(i) for i in range(1, 10)] if n and n["type"] == "reflection"]
    assert len(refls) == 1
    refl = refls[0]
    assert refl["category"] == THINKING
    # based_on 连回 t1, t2
    targets = [n["id"] for n in forest.walk(refl["id"], BASED_ON)]
    assert set(targets) == {t1, t2}
    forest.close()


def test_reflect_nesting_self_reference(tmp_path):
    """套娃: reflection2 based_on reflection1(自指递归)。"""
    forest = SQLiteForest(tmp_path / "f.db", session_id="s1")
    agent = _FakeAgent(forest)
    tool = make_reflect_tool(agent)
    thought = forest.add_node(category=THINKING, type="thought", content="原始想法")
    # 第一层反思
    tool.execute({"content": "反思原始想法", "based_on": [thought]})
    r1 = [n for n in [forest.get(i) for i in range(1, 20)]
          if n and n["type"] == "reflection"][0]
    # 第二层反思(套娃): 反思 reflection1
    tool.execute({"content": "反思我的反思方式", "based_on": [r1["id"]]})
    r2 = [n for n in [forest.get(i) for i in range(r1["id"] + 1, 30)]
          if n and n["type"] == "reflection"][0]
    # r2 based_on → r1(套娃链)
    assert r1["id"] in [n["id"] for n in forest.walk(r2["id"], BASED_ON)]
    forest.close()


def test_reflect_empty_content_errors(tmp_path):
    forest = SQLiteForest(tmp_path / "f.db", session_id="s1")
    agent = _FakeAgent(forest)
    tool = make_reflect_tool(agent)
    result = tool.execute({"content": ""})
    assert isinstance(result, tuple) and result[1] is True   # is_error
    forest.close()


def test_reflect_null_forest_degrades():
    """NullForest: reflect 提示未配置, 不崩。"""
    from prism.cognitive import NullForest
    agent = _FakeAgent(NullForest())
    tool = make_reflect_tool(agent)
    out = tool.execute({"content": "x"})
    assert "未配置" in out[0]
