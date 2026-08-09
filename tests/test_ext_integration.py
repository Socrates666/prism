"""ext/ 集成测试: shell 加载 ext/ → main agent 接 registry → tool 可用。

验证阶段 4/5 集成闭环(web_search + datetime_now)。
"""
from prism.registry import Registry, load_ext
from prism.agent import Agent


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


def test_load_ext_loads_web_search_and_datetime_now():
    r = Registry()
    loaded = load_ext("ext", r)
    names = [t.name for t in r.tools()]
    assert "tools/web_search" in loaded
    assert "tools/datetime_now" in loaded
    assert "web_search" in names
    assert "datetime_now" in names


def test_main_agent_gets_ext_tools_via_registry():
    """模拟 shell 集成: load_ext + Agent(registry=default_registry)。"""
    r = Registry()
    load_ext("ext", r)
    a = Agent("main", model=_M(), registry=r, actor=False)
    names = [t.name for t in a._tools()]
    assert "web_search" in names                        # ext tool 进了 main agent
    assert "datetime_now" in names
    assert "python" in names                            # main 还有 python 工具


def test_datetime_now_default_format():
    r = Registry()
    load_ext("ext", r)
    dt = r.get_tool("datetime_now")
    assert dt is not None
    result = dt.execute({})
    assert "2026" in result                             # 当前年份


def test_datetime_now_custom_format():
    r = Registry()
    load_ext("ext", r)
    dt = r.get_tool("datetime_now")
    assert dt.execute({"format": "%Y-%m-%d"})[:4] == "2026"
    weekday = dt.execute({"format": "%A"})              # 星期几
    assert weekday in {"Monday", "Tuesday", "Wednesday", "Thursday",
                       "Friday", "Saturday", "Sunday"}


def test_web_search_tool_registered_with_schema():
    r = Registry()
    load_ext("ext", r)
    ws = r.get_tool("web_search")
    assert ws is not None
    assert ws.name == "web_search"
    assert "query" in ws.parameters["properties"]
    assert ws.parameters["required"] == ["query"]
