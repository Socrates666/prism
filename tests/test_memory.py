"""阶段10 持久化测试: MemoryBackend + NullMemory + FileMemory + agent dump/restore。"""
from prism.memory import MemoryBackend, NullMemory, FileMemory
from prism.agent import Agent


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "delta", "text": "reply"}
        yield {"type": "done", "tool_calls": []}


def test_null_memory_is_noop():
    m = NullMemory()
    m.save("x", [{"role": "user", "content": "hi"}])
    assert m.load("x") == []
    m.clear("x")


def test_file_memory_save_load_roundtrip(tmp_path):
    m = FileMemory(tmp_path)
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    m.save("alice", msgs)
    assert m.load("alice") == msgs


def test_file_memory_load_missing_returns_empty(tmp_path):
    assert FileMemory(tmp_path).load("nope") == []


def test_file_memory_clear_and_keys(tmp_path):
    m = FileMemory(tmp_path)
    m.save("a", [])
    m.save("b", [])
    assert m.keys() == ["a", "b"]
    m.clear("a")
    assert m.keys() == ["b"]


def test_agent_default_null_memory():
    a = Agent("a", model=_M(), actor=False)
    assert isinstance(a.memory, NullMemory)
    a.run("x")                                  # dump 不崩(NullMemory)


def test_agent_restores_messages_on_init(tmp_path):
    """强杀重启恢复: 新 agent 同名从 memory load 历史(原则6)。"""
    mem = FileMemory(tmp_path)
    a = Agent("alice", model=_M(), memory=mem, actor=False)
    a.run("你好")
    a.dump()
    # 模拟重启: 新 agent 同名, 启动 restore
    b = Agent("alice", model=_M(), memory=mem, actor=False)
    assert len(b.messages) >= 2                 # 恢复了历史
    assert any(m.get("content") == "你好" for m in b.messages)


def test_agent_run_auto_dumps(tmp_path):
    mem = FileMemory(tmp_path)
    a = Agent("a", model=_M(), memory=mem, actor=False)
    a.run("go")
    assert mem.load("a") == a.messages          # run 后自动 dump


def test_memory_backend_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        MemoryBackend()                         # ABC 不能实例化


def test_cross_session_continuation(tmp_path):
    """阶段11: 跨会话延续(原始痛点 'IPython 跨会话 agent 交互')。
    会话1 对话+dump → 会话2(模拟重启) restore → 记得历史。"""
    mem = FileMemory(tmp_path)
    a1 = Agent("main", model=_M(), memory=mem, actor=False)
    a1.run("我叫张三")
    # 模拟重启: 新 agent 同名, 启动 restore
    a2 = Agent("main", model=_M(), memory=mem, actor=False)
    assert any("张三" in m.get("content", "") for m in a2.messages)   # 记得会话1
    a2.run("我叫什么")
    assert len(a2.messages) >= 4              # 历史 + 新对话延续
