"""ext/ 集成测试: shell 加载 ext/ → main agent 接 registry → tool 可用(web_search)。"""
from prism.registry import Registry, load_ext
from prism.agent import Agent


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


def test_load_ext_loads_web_search():
    r = Registry()
    loaded = load_ext("ext", r)
    names = [t.name for t in r.tools()]
    assert "tools/web_search" in loaded
    assert "web_search" in names


def test_main_agent_gets_ext_tools_via_registry():
    """模拟 shell 集成: load_ext + Agent(registry=default_registry)。"""
    r = Registry()
    load_ext("ext", r)
    a = Agent("Prism", model=_M(), registry=r, actor=False)
    names = [t.name for t in a._tools()]
    assert "web_search" in names                        # ext tool 进了 agent
    assert "python" in names                            # main 还有 python 工具


def test_web_search_tool_registered_with_schema():
    r = Registry()
    load_ext("ext", r)
    ws = r.get_tool("web_search")
    assert ws is not None
    assert ws.name == "web_search"
    assert "query" in ws.parameters["properties"]
    assert ws.parameters["required"] == ["query"]
