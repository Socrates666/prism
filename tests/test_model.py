"""OpenAIModel.chat_stream 单元测试(白盒, 补 model.py 累积逻辑)。

mock OpenAI client, 不联网。验证 tool_calls 分片累积拼回完整。
"""


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
    events = list(m.chat_stream([{"role": "user", "content": "x"}]))
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "hi there"
    assert events[-1]["tool_calls"] == []
