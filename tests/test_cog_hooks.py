"""tests/test_cog_hooks.py — AutoAttachHook + 认知事件广播测试(RLM Phase B)。"""
import pytest
from prism.agent import Agent
from prism.forest import SQLiteForest
from prism.cog_hooks import AutoAttachHook


class _FakeAgent:
    """最小 agent 替身(只持 forest)。"""
    def __init__(self, forest):
        self.forest = forest


def test_auto_attach_unit_builds_causes_chain(tmp_path):
    """单元: 直接喂认知事件, forest 形成 causes 链。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = _FakeAgent(forest)
    hook = AutoAttachHook()
    hook.on_cognitive_event(agent, {"type": "thought", "content": "想"})
    hook.on_cognitive_event(agent, {"type": "action", "name": "read", "args": {}})
    hook.on_cognitive_event(agent, {"type": "result", "content": "ok"})
    trees = forest.trees()
    assert len(trees) == 1
    nodes = forest.nodes_in_tree(trees[0])
    assert [n["type"] for n in nodes] == ["thought", "action", "result"]
    assert [n["category"] for n in nodes] == ["thinking", "thinking", "context"]
    # causes 链: 从根 thought 走到全部
    assert len(forest.subtree(nodes[0]["id"])) == 3


def test_agent_emit_broadcasts_to_cognitive_hook(tmp_path):
    """集成: Agent.emit → 翻译 → AutoAttachHook → forest。不需 model/run。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = Agent("t", model=None, actor=False,
                  forest=forest, cognitive_hooks=[AutoAttachHook()])
    agent.emit({"type": "message_end", "text": "我打算先读代码"})
    agent.emit({"type": "tool_execution_start", "tool_name": "read", "args": {"path": "x"}})
    agent.emit({"type": "tool_execution_end", "tool_name": "read",
                "result": "200 行", "is_error": False})
    trees = forest.trees()
    assert len(trees) == 1
    nodes = forest.nodes_in_tree(trees[0])
    assert len(nodes) == 3
    assert nodes[0]["content"] == "我打算先读代码"
    assert nodes[2]["content"] == "200 行"


def test_empty_cognitive_hooks_is_noop(tmp_path):
    """默认(无 hook) → emit 不崩, forest 空(逐字节现状退化)。"""
    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = Agent("t", model=None, actor=False, forest=forest)   # 无 cognitive_hooks
    agent.emit({"type": "message_end", "text": "x"})
    agent.emit({"type": "tool_execution_end", "tool_name": "r", "result": "y", "is_error": False})
    assert forest.trees() == []   # 没挂任何节点


def test_hook_exception_does_not_crash_emit(tmp_path):
    """坏 hook 抛异常 → emit 不炸(容错降级)。"""
    from prism.cognitive import CognitiveHook

    class BadHook(CognitiveHook):
        def on_cognitive_event(self, agent, event):
            raise RuntimeError("炸了")

    forest = SQLiteForest(tmp_path / "f.db", "s1")
    agent = Agent("t", model=None, actor=False,
                  forest=forest, cognitive_hooks=[BadHook()])
    agent.emit({"type": "message_end", "text": "x"})   # 不抛
