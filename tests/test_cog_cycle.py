"""tests/test_cog_cycle.py — 搜索循环 patch 测试(RLM Phase A·patch 先行)。"""
import pytest
from prism.agent import Agent
from prism.forest import SQLiteForest
from prism.cognitive import THINKING, FAILED
from prism.cog_patches import enable_cognitive_cycle


class _RecordingModel:
    """记录收到的 messages, 单轮返回文本(无工具调用→停)。"""
    def __init__(self):
        self.seen = None
        self.thinking_level = "off"

    def chat_stream(self, messages, tools=None):
        self.seen = "\n".join((m.get("content") or "") for m in messages)
        yield {"type": "delta", "text": "收到"}
        yield {"type": "done", "text": "收到", "tool_calls": []}


def test_enable_cycle_injects_search_state(tmp_path):
    """预置树(thought/failed/reflection)→ run → 模型 prompt 含 search-state。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    t1 = forest.add_node(category=THINKING, type="thought", content="想用方法A")
    forest.add_node(category=THINKING, type="thought", content="方法A", parent=t1, status=FAILED)
    forest.add_node(category=THINKING, type="reflection", content="该换思路", parent=t1)

    model = _RecordingModel()
    agent = Agent("t", model=model, actor=False, forest=forest)
    enable_cognitive_cycle(agent)
    agent.run("继续")

    assert model.seen is not None
    assert "认知树" in model.seen        # search-state 注入了
    assert "方法A" in model.seen
    assert "失败" in model.seen or "该换思路" in model.seen
    forest.close()


def test_enable_cycle_idempotent(tmp_path):
    """重复 enable 不重复装 hook/patch。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = Agent("t", model=_RecordingModel(), actor=False, forest=forest)
    enable_cognitive_cycle(agent)
    n_hooks = len(agent.cognitive_hooks)
    n_patches = len(agent.patches._before["build_messages"])
    enable_cognitive_cycle(agent)   # 再装一次
    assert len(agent.cognitive_hooks) == n_hooks
    assert len(agent.patches._before["build_messages"]) == n_patches
    forest.close()


def test_cycle_noop_on_empty_forest(tmp_path):
    """空树(forest 刚建无节点)→ select_context 返空 → 不注入, 不崩。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    model = _RecordingModel()
    agent = Agent("t", model=model, actor=False, forest=forest)
    enable_cognitive_cycle(agent)
    agent.run("开始")
    assert model.seen is not None
    assert "认知树" not in model.seen   # 空树不注入
    forest.close()


def test_cycle_records_run_cognition_to_tree(tmp_path):
    """跑一轮 → AutoAttachHook 把模型的 thought 挂进树。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    model = _RecordingModel()
    agent = Agent("t", model=model, actor=False, forest=forest)
    enable_cognitive_cycle(agent)
    agent.run("干活")
    trees = forest.trees()
    assert len(trees) == 1
    nodes = forest.nodes_in_tree(trees[0])
    # 至少有一个 thought 节点(模型说的"收到"被挂)
    assert any(n["type"] == "thought" and "收到" in n["content"] for n in nodes)
    forest.close()
