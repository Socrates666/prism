"""ext/ 集成测试: shell 加载 ext/ → main agent 接 registry → tool/persona 可用。

注: prism 会自我演进 ext/(如 web_search → search 体系), 测机制不锁死 tool 名。
"""
from prism.registry import Registry, load_ext
from prism.agent import Agent


class _M:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


def test_load_ext_loads_tools_and_prompts():
    r = Registry()
    loaded = load_ext("ext", r)
    assert any(l.startswith("tools/") for l in loaded)      # 有 tool
    # prompts/ 已合并到 agents/ — 不再单独加载
    assert "tools/search" in loaded                           # search 工具
    assert len(r.tools()) >= 1


def test_main_agent_gets_ext_tools_via_registry():
    """模拟 shell 集成: load_ext + Agent(registry)。"""
    r = Registry()
    load_ext("ext", r)
    a = Agent("Prism", model=_M(), registry=r, actor=False)
    names = [t.name for t in a._tools()]
    assert "python" in names                                 # main 有 python 工具
    assert len([n for n in names if n != "python"]) >= 1     # 至少一个 ext tool


def test_search_tool_registered():
    """prism 自我演进: 搜索 tool(无论叫 web_search / search / github_search)。"""
    r = Registry()
    load_ext("ext", r)
    search_tools = [t for t in r.tools() if "search" in t.name.lower()]
    assert len(search_tools) >= 1                            # 至少一个搜索 tool


def test_prism_agent_config_loaded():
    """ext/agents/prism/ 配置(含 prompt 段)正确加载。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    prism_cfg = next((c for c in configs if c["name"] == "Prism"), None)
    assert prism_cfg is not None
    assert prism_cfg.get("prompt_sections") is not None
    assert "role" in prism_cfg["prompt_sections"]
