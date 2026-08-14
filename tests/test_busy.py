"""REQ-E 固化: agent 运行期异常后 busy 归位 + 并发 agent 引用计数。

E1: error 事件兜底重置 busy(防网络错误后 spinner 永转、Esc 失灵)。
E2: 子 agent_end 不抹仍在跑的主 agent busy(引用计数, PROBLEM-2)。
E5: 重复 agent_end(run_agent_loop finally + _actor_loop 兜底)不去双扣计数。
"""
from prism.shell import PrismApp


def test_error_resets_busy():
    """E1: agent_start 后直发 error → busy 必须归 False。"""
    app = PrismApp()
    app.run(headless=True)
    emit = app.agent.hooks["emit"]
    emit({"type": "agent_start"})
    app._drain()
    assert app._agent_busy is True
    emit({"type": "error", "error": "boom: APIConnectionError"})
    app._drain()
    assert app._agent_busy is False, "busy stuck True after error"


def test_subagent_end_does_not_clear_main_busy():
    """E2: 子 agent_end 不应把仍在跑的主 agent 抹成 idle。"""
    app = PrismApp()
    app.run(headless=True)
    emit = app.agent.hooks["emit"]
    sub_emit = app.make_subagent_emit("sub1")
    emit({"type": "agent_start"})
    sub_emit({"type": "agent_start"})
    app._drain()
    assert app._agent_busy is True
    sub_emit({"type": "agent_end"})
    app._drain()
    assert app._agent_busy is True, "sub agent_end cleared busy while main still running"
    emit({"type": "agent_end"})
    app._drain()
    assert app._agent_busy is False


def test_duplicate_agent_end_does_not_over_decrement():
    """E5: finally 的 agent_end + _actor_loop 兜底的重复 agent_end 只扣一次。"""
    app = PrismApp()
    app.run(headless=True)
    emit = app.agent.hooks["emit"]
    emit({"type": "agent_start"})
    app._drain()
    assert app._agent_busy is True
    emit({"type": "agent_end"})      # run_agent_loop finally
    emit({"type": "agent_end"})      # _actor_loop 兜底(重复, 应被 started 去重)
    app._drain()
    assert app._agent_busy is False, "duplicate agent_end over-decremented into stuck-busy or negative"
    assert app._busy_depth == 0
