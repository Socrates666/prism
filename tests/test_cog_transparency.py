"""tests/test_cog_transparency.py — 认知循环白盒化: 直觉/反思认知事件发射(RLM)。

TUI 透明的基础: 认知组件发 cognitive 事件(直觉/反思), TUI 显示五阶段。
"""
import pytest
from prism.cognitive import THINKING, FAILED
from prism.forest import SQLiteForest
from prism.cog_intuition import HeuristicIntuition
from prism.cog_tools import make_reflect_tool


class _RecordingAgent:
    """记录 emit 事件的 agent 替身(只持 forest + emit)。"""
    def __init__(self, forest):
        self.forest = forest
        self.events = []

    def emit(self, event):
        self.events.append(event)


def test_intuition_emits_cognitive_event(tmp_path):
    """HeuristicIntuition 注入 search-state 时, 发 cognitive/intuition 事件(TUI 显示用)。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    forest.add_node(category=THINKING, type="thought", content="想用方法A")
    forest.add_node(category=THINKING, type="thought", content="方法A失败", status=FAILED)
    agent = _RecordingAgent(forest)

    extra = HeuristicIntuition(forest).select_context(agent, {})
    assert extra   # 注入了 search-state
    cog = [e for e in agent.events if e.get("type") == "cognitive"]
    assert len(cog) == 1
    assert cog[0]["stage"] == "intuition"
    assert "方法A" in cog[0]["content"]


def test_intuition_no_event_on_empty_tree(tmp_path):
    """空树 → 不注入 → 不发直觉事件。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = _RecordingAgent(forest)
    extra = HeuristicIntuition(forest).select_context(agent, {})
    assert extra == []
    assert not [e for e in agent.events if e.get("type") == "cognitive"]


def test_reflect_emits_cognitive_event(tmp_path):
    """reflect 工具创建反思时, 发 cognitive/reflect 事件。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    t1 = forest.add_node(category=THINKING, type="thought", content="原想法")
    agent = _RecordingAgent(forest)
    tool = make_reflect_tool(agent)
    tool.execute({"content": "我总是自顶向下", "based_on": [t1]})

    cog = [e for e in agent.events if e.get("type") == "cognitive"]
    assert len(cog) == 1
    assert cog[0]["stage"] == "reflect"
    assert cog[0]["content"] == "我总是自顶向下"
    assert t1 in cog[0]["based_on"]


def test_cognitive_event_has_five_stage_vocabulary(tmp_path):
    """确认认知循环五阶段词汇在事件/TUI 处理范围: 直觉/反思(cognitive)+ 行动/观察(tool)。"""
    # 这里只验认知组件发的 stage; 行动/观察走现有 tool_execution_* 事件(shell 已标)
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    forest.add_node(category=THINKING, type="thought", content="x")
    agent = _RecordingAgent(forest)
    HeuristicIntuition(forest).select_context(agent, {})
    stages = {e.get("stage") for e in agent.events if e.get("type") == "cognitive"}
    assert "intuition" in stages
