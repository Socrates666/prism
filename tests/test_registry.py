"""Registry + ext/ 容错加载测试(阶段 4, 原则 12)。"""
import pytest
from prism.registry import Registry, load_ext
from prism.agent_loop import Tool


def test_registry_register_get_tool():                       # [C1]
    reg = Registry()
    t = Tool("echo", "", {"type": "object", "properties": {}}, lambda a: "x")
    assert reg.tool(t) is t                                  # 装饰器/直调都返回 t
    assert reg.get_tool("echo") is t
    assert reg.get_tool("nope") is None
    assert reg.tools() == [t]


def test_load_ext_loads_good_module(tmp_path):               # [C2]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "good.py").write_text(
        "from prism.agent_loop import Tool\n"
        "def register(reg):\n"
        "    reg.tool(Tool('exttool','', {'type':'object','properties':{}}, lambda a: 'ext-ok'))\n")
    reg = Registry()
    loaded = load_ext(tmp_path, reg)
    assert "tools/good" in loaded
    assert reg.get_tool("exttool") is not None
    assert reg.get_tool("exttool").execute({}) == "ext-ok"


def test_load_ext_skips_bad_modules(tmp_path):               # [C3]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "good.py").write_text(
        "from prism.agent_loop import Tool\n"
        "def register(r): r.tool(Tool('g','', {'type':'object','properties':{}}, lambda a:'g'))\n")
    (tmp_path / "tools" / "bad.py").write_text("raise RuntimeError('boom')\n")        # import 错
    (tmp_path / "tools" / "norfn.py").write_text("X = 1\n")                            # 缺 register
    errs = []
    reg = Registry()
    loaded = load_ext(tmp_path, reg, emit=lambda e: errs.append(e))
    assert "tools/good" in loaded
    assert "tools/bad" not in loaded
    assert "tools/norfn" not in loaded
    assert len(errs) == 2                                     # bad + norfn 各一警告
    assert reg.get_tool("g") is not None                      # good 仍加载(容错)


def test_load_ext_missing_dir_is_noop(tmp_path):             # 空 ext 不炸
    reg = Registry()
    assert load_ext(tmp_path / "nope", reg) == []


def test_agent_uses_registry_tools(tmp_path):                # [C4] ext tool 给 agent 用
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "g.py").write_text(
        "from prism.agent_loop import Tool\n"
        "def register(r): r.tool(Tool('rg','', {'type':'object','properties':{}}, lambda a:'rg-ok'))\n")
    reg = Registry()
    load_ext(tmp_path, reg)
    from prism.agent import Agent
    class _M:  # 不需要真跑, 只验 _tools()
        def chat_stream(self, m, tools=None):
            yield {"type": "done", "tool_calls": []}
    agent = Agent("a", model=_M(), registry=reg)
    names = [t.name for t in agent._tools()]
    assert "rg" in names                                      # ext tool 进了 agent 工具集
