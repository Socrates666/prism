"""OpenAIModel.chat_stream 单元测试(白盒, 补 model.py 累积逻辑 + fallback/reasoning/thinking)。

mock OpenAI client, 不联网。
"""
import pytest
from prism.model import OpenAIModel


def _make_chunk(content=None, tool_calls=None):
    """造一个 openai 流式 chunk(fake)。"""
    class Fn:
        def __init__(self, name="", arguments=""):
            self.name = name
            self.arguments = arguments
    class TC:
        def __init__(self, index, id=None, function=None):
            self.index = index
            self.id = id
            self.function = function
    class Delta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
    class Choice:
        def __init__(self, delta):
            self.delta = delta
    class Chunk:
        def __init__(self, choices):
            self.choices = choices
    return Chunk([Choice(Delta(content=content, tool_calls=tool_calls))])


def test_chat_stream_accumulates_tool_call_fragments():
    """tool_call arguments 分片跨多 chunk → 拼回完整 JSON。"""
    from prism.model import OpenAIModel

    class Fn:
        def __init__(self, name="", arguments=""):
            self.name = name
            self.arguments = arguments
    class TC:
        def __init__(self, index, id=None, function=None):
            self.index = index
            self.id = id
            self.function = function

    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(tool_calls=[TC(0, id="call_1", function=Fn(name="echo"))]),
        _make_chunk(tool_calls=[TC(0, function=Fn(arguments='{"x":'))]),
        _make_chunk(tool_calls=[TC(0, function=Fn(arguments='"a"}'))]),
        _make_chunk(),                                      # 空 choices 收尾
    ]

    class FakeCompletions:
        def create(self, **kw):
            return iter(chunks)
    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()
    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    m = OpenAIModel.__new__(OpenAIModel)                   # 跳过 __init__(不连网)
    m.client = FakeClient()
    m.model = "test"
    m._first_timeout = 5.0

    events = list(m.chat_stream([{"role": "user", "content": "x"}], tools=[]))
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    done = [e for e in events if e["type"] == "done"][0]
    assert deltas == ["Hello"]
    tcs = done["tool_calls"]
    assert len(tcs) == 1
    assert tcs[0]["id"] == "call_1"
    assert tcs[0]["function"]["name"] == "echo"
    assert tcs[0]["function"]["arguments"] == '{"x":"a"}'  # 分片拼回


def test_chat_plain_text_no_tools():
    from prism.model import OpenAIModel
    chunks = [_make_chunk(content="hi"), _make_chunk(content=" there"), _make_chunk()]

    class FakeClient:
        chat = type("C", (), {"completions": type("P", (), {"create": staticmethod(lambda **k: iter(chunks))})()})()
    m = OpenAIModel.__new__(OpenAIModel)
    m.client = FakeClient()
    m.model = "t"
    m._first_timeout = 5.0
    events = list(m.chat_stream([{"role": "user", "content": "x"}]))
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "hi there"
    assert events[-1]["tool_calls"] == []


# ── 补: fallback / reasoning / thinking / non_stream tool_calls ──
class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls
class _Resp:
    def __init__(self, msg): self.choices = [type("C", (), {"message": msg})()]
class _Fn:
    def __init__(self, name="", arguments=""): self.name = name; self.arguments = arguments
class _TC:
    def __init__(self, id, fn): self.id = id; self.function = fn
class _Delta:
    def __init__(self, content=None, reasoning_content=None):
        self.content = content; self.reasoning_content = reasoning_content; self.tool_calls = None
class _Chunk:
    def __init__(self, delta=None):
        self.choices = [type("C", (), {"delta": delta})()] if delta else []


def _fake_client(stream_chunks=None, nonstream_resp=None, hang_stream=False):
    calls = []
    def create(**kw):
        calls.append(kw)
        if kw.get("stream"):
            if hang_stream:
                import time; time.sleep(2)   # 模拟挂起(超 first_timeout → fallback)
            return iter(stream_chunks or [])
        return nonstream_resp
    client = type("Client", (), {})()
    client.chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(create)})()})()
    return client, calls


def _model_with(client, thinking_level=None, first_timeout=0.4):
    m = OpenAIModel.__new__(OpenAIModel)
    m.client = client
    m.model = "t"
    m.thinking_level = thinking_level
    m._first_timeout = first_timeout
    return m


def test_chat_stream_fallback_when_stream_hangs():           # 流式空→首超时→非流式
    resp = _Resp(_Msg(content="fallback-ok"))
    client, calls = _fake_client(nonstream_resp=resp, hang_stream=True)
    events = list(_model_with(client).chat_stream([{"role": "user", "content": "x"}]))
    assert [e["text"] for e in events if e["type"] == "delta"] == ["fallback-ok"]
    assert len(calls) == 2 and calls[0]["stream"] is True and calls[1]["stream"] is False


def test_chat_stream_yields_reasoning_content():              # reasoning_content→reasoning 事件
    chunk = _Chunk(_Delta(content="ans", reasoning_content="thinking..."))
    client, _ = _fake_client(stream_chunks=[chunk])
    events = list(_model_with(client, first_timeout=5).chat_stream([{"role": "user", "content": "x"}]))
    assert [e["text"] for e in events if e["type"] == "reasoning"] == ["thinking..."]
    assert [e["text"] for e in events if e["type"] == "delta"] == ["ans"]


def test_thinking_off_sends_enable_thinking_false():          # thinking_level=off→extra_body
    client, calls = _fake_client(stream_chunks=[_Chunk(_Delta(content="x"))])
    list(_model_with(client, thinking_level="off", first_timeout=5)
         .chat_stream([{"role": "user", "content": "x"}]))
    assert calls[0].get("extra_body") == {"enable_thinking": False}


def test_non_stream_tool_calls_parsed():                      # fallback 非流式 tool_calls
    tc = _TC("id1", _Fn(name="echo", arguments='{"x":1}'))
    resp = _Resp(_Msg(content=None, tool_calls=[tc]))
    client, _ = _fake_client(nonstream_resp=resp, hang_stream=True)
    events = list(_model_with(client).chat_stream([{"role": "user", "content": "x"}]))
    done = next(e for e in events if e["type"] == "done")
    assert done["tool_calls"] == [{"id": "id1", "type": "function",
                                    "function": {"name": "echo", "arguments": '{"x":1}'}}]


def test_producer_error_propagates():                         # producer 抛→raise
    def boom(**kw): raise RuntimeError("api down")
    client = type("Client", (), {})()
    client.chat = type("Chat", (), {"completions": type("Comp", (), {"create": staticmethod(boom)})()})()
    with pytest.raises(RuntimeError):
        list(_model_with(client, first_timeout=5).chat_stream([{"role": "user", "content": "x"}]))
