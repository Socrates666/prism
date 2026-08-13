"""SmallModelIntuition 测试(Phase C · C1+C2+C4): scribe / 缓存 / 降级。"""
from prism.forest import SQLiteForest
from prism.cognitive import THINKING, FAILED
from prism.cog_intuition import SmallModelIntuition


class _FakeSmall:
    """小模型桩: 记调用次数, 可控抛异常。"""
    def __init__(self, reply="直觉: 当前在写地图, 别重复连通性失败", throw=False):
        self.reply = reply
        self.throw = throw
        self.calls = 0

    def chat(self, msgs):
        self.calls += 1
        if self.throw:
            raise RuntimeError("small model down")
        return self.reply


class _AgentStub:
    """select_context 只用 agent.emit; 桩掉。"""
    def __init__(self):
        self.emitted = []

    def emit(self, ev):
        self.emitted.append(ev)


def _forest_with_nodes(tmp_path):
    f = SQLiteForest(tmp_path / "f.db", "s")
    t = f.add_node(category=THINKING, type="thought", content="想用方法A")
    f.add_node(category=THINKING, type="thought", content="方法A失败", parent=t, status=FAILED)
    f.add_node(category=THINKING, type="reflection", content="该换思路", parent=t)
    return f


def test_small_model_intuition_scribe(tmp_path):
    """C1: 有节点 → 小模型拼 search-state → [system] msg。"""
    f = _forest_with_nodes(tmp_path)
    m = _FakeSmall()
    intu = SmallModelIntuition(f, m)
    ctx = intu.select_context(_AgentStub(), {})
    assert ctx and ctx[0]["role"] == "system"
    assert "直觉" in ctx[0]["content"]
    assert m.calls == 1                          # 调了一次小模型
    f.close()


def test_small_model_intuition_cache(tmp_path):
    """C2: 同签名(无新节点)第二次复用缓存, 不重调小模型。"""
    f = _forest_with_nodes(tmp_path)
    m = _FakeSmall()
    intu = SmallModelIntuition(f, m)
    intu.select_context(_AgentStub(), {})        # 首次
    intu.select_context(_AgentStub(), {})        # 同签名 → 缓存
    assert m.calls == 1                           # 没重调
    f.close()


def test_small_model_intuition_cache_invalidates_on_new_node(tmp_path):
    """C2: 新节点加入 → 签名变 → 重调小模型(缓存失效)。"""
    f = _forest_with_nodes(tmp_path)
    m = _FakeSmall()
    intu = SmallModelIntuition(f, m)
    intu.select_context(_AgentStub(), {})
    f.add_node(category=THINKING, type="thought", content="新思路B")  # 新节点
    intu.select_context(_AgentStub(), {})
    assert m.calls == 2                           # 签名变 → 重调
    f.close()


def test_small_model_intuition_fallback(tmp_path):
    """C4: 小模型抛异常 → 退 HeuristicIntuition 启发式(不崩, 格式对)。"""
    f = _forest_with_nodes(tmp_path)
    m = _FakeSmall(throw=True)
    intu = SmallModelIntuition(f, m)
    ctx = intu.select_context(_AgentStub(), {})
    assert ctx                                    # 启发式兜底, 不崩
    assert "[认知树·直觉 search-state]" in ctx[0]["content"]   # Heuristic 格式
    f.close()


def test_small_model_intuition_empty_forest(tmp_path):
    """空树 → 返空, 不调小模型。"""
    f = SQLiteForest(tmp_path / "f.db", "s")
    m = _FakeSmall()
    intu = SmallModelIntuition(f, m)
    ctx = intu.select_context(_AgentStub(), {})
    assert ctx == []
    assert m.calls == 0
    f.close()
