"""对齐 pi 阶段验收(阶段1): D2 state 命名 / D3 prompt 机制 / D4 steer+subscribe。"""
import json
import pytest
from prism.agent import Agent
from prism.agent_loop import Tool


class FakeModel:
    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def chat_stream(self, messages, tools=None):
        text, tcs = self.script[self.i]
        self.i += 1
        if text:
            yield {"type": "delta", "text": text}
        yield {"type": "done", "tool_calls": tcs or []}


def tc(name, arg=None, cid="1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(arg or {})}}


# ── D2: state 命名对齐 pi ──────────────────────────────
def test_state_uses_messages_and_pi_fields():
    a = Agent("a", model=FakeModel([]))
    assert hasattr(a, "messages") and not hasattr(a, "history")    # history→messages
    assert a.streaming_message is None                             # 对齐 pi
    assert a.error_message == ""


def test_streaming_message_tracked_then_cleared():
    a = Agent("a", model=FakeModel([("hello", [])]))
    mid = []

    def hook(e):
        if e.get("type") == "message_update":
            mid.append(a.streaming_message)
    a.hooks["emit"] = hook
    a.run("go")
    assert mid and mid[-1] == "hello"                              # 流式中累积
    assert a.streaming_message is None                             # message_end 清空


def test_error_message_tracked_on_tool_error():
    a = Agent("a", model=FakeModel([("", [tc("boom", {})]), ("done", [])]),
              tools=[Tool("boom", "", {"type": "object", "properties": {}}, lambda a: ("kaboom", True))])
    a.run("go")
    assert "kaboom" in a.error_message


# ── D3: system prompt override/append ──────────────────
def test_system_prompt_override_replaces_base():
    a = Agent("a", model=FakeModel([]), system_prompt_override="OVERRIDE ONLY")
    assert a.system_prompt == "OVERRIDE ONLY"


def test_append_system_prompt_extends():
    a = Agent("a", model=FakeModel([]), append_system_prompt=["Extra 1", "Extra 2"])
    sp = a.system_prompt
    assert "Extra 1" in sp and "Extra 2" in sp            # 默认段空(base 不硬编码), append 进 extra


def test_append_to_system_prompt_runtime():
    a = Agent("a", model=FakeModel([]))
    a.append_to_system_prompt("LATE RULE")
    assert "LATE RULE" in a.system_prompt


def test_apply_prompt_fills_sections():
    """配置外部化(原则 12): ext/agents/ YAML 声明 prompt 段。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    prism_cfg = next((c for c in configs if c["name"] == "Prism"), None)
    assert prism_cfg is not None
    sections = prism_cfg.get("prompt_sections")
    assert sections is not None
    a = Agent("Prism", model=FakeModel([]))
    assert a.system_prompt == ""                       # base 不硬编码(空)
    from prism.agent_registry import _apply_prompt_from_config
    _apply_prompt_from_config(a, prism_cfg)
    assert "Prism" in a.system_prompt and "## 角色" in a.system_prompt
    assert "python" in a.system_prompt            # capabilities
    assert "RLM" in a.system_prompt               # instructions(RLM 理念)


# ── D4: inject steer/followUp + subscribe ──────────────
def test_inject_steer_precedes_followup_in_queue():
    a = Agent("a", model=FakeModel([]), actor=False)               # 不起线程, 静态验队列
    a.inject({"type": "run", "input": "late"}, kind="followUp")
    a.inject({"type": "run", "input": "urgent"}, kind="steer")
    items = []
    while not a.inbox.empty():
        items.append(a.inbox.get_nowait())
    assert items[0][0] == 0 and items[0][2]["input"] == "urgent"   # steer 优先
    assert items[1][0] == 10 and items[1][2]["input"] == "late"


def test_subscribe_receives_events_and_unsubscribe():
    a = Agent("a", model=FakeModel([("hi", []), ("again", [])]))
    seen = []
    unsub = a.subscribe(lambda e: seen.append(e.get("type")))
    a.run("go")
    assert "agent_start" in seen and "message_update" in seen
    unsub()
    seen_before = len(seen)
    a.run("again")
    assert len(seen) == seen_before                                # 取消后不再收


# ── D5: retry / thinking / compaction ──────────────────
class FlakyModel:
    """第一次 chat_stream 抛异常, 第二次成功。"""
    def __init__(self):
        self.calls = 0
    def chat_stream(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        yield {"type": "delta", "text": "recovered"}
        yield {"type": "done", "tool_calls": []}


class SummaryModel:
    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}
    def chat(self, messages):
        return "SUMMARY"


def test_retry_recovers_after_transient_error():
    retries = []
    a = Agent("a", model=FlakyModel(), max_retries=2)
    a.subscribe(lambda e: retries.append(e.get("type")))
    a.run("go")
    assert a.last_result == "recovered"                            # 重试后成功
    assert "auto_retry_start" in retries                          # 对齐 pi auto_retry 事件


def test_retry_gives_up_after_max():
    a = Agent("a", model=FlakyModel(), max_retries=0)             # 不重试
    with pytest.raises(RuntimeError):
        a.run("go")


def test_thinking_level_settable():
    a = Agent("a", model=FakeModel([]))
    assert a.thinking_level == "off"
    a.set_thinking_level("high")
    assert a.thinking_level == "high"


def test_compact_replaces_messages_with_summary():
    a = Agent("a", model=SummaryModel())
    a.messages = [{"role": "user", "content": "long convo"},
                  {"role": "assistant", "content": "..."}]
    s = a.compact()
    assert s == "SUMMARY"
    assert len(a.messages) == 1                                   # 压成一条
    assert "SUMMARY" in a.messages[0]["content"]
