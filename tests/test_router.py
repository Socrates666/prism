"""@ 路由单元测试(白盒, 补 router.py 0% 覆盖)。"""
import pytest
from prism.router import _transform, at_error, at_route


def test_passthrough_non_at():                      # 非 @ 原样
    assert _transform(["x = 1\n"]) == ["x = 1\n"]


def test_passthrough_multiline_decorator():         # 多行(含 @decorator)不碰
    lines = ["@deco\ndef f():\n    pass\n"]
    assert _transform(lines) == lines


def test_bare_at_errors():                          # 裸 @ 报错
    out = _transform(["@"])
    assert "at_error" in out[0] and "裸" in out[0]


def test_multi_at_errors():                         # 多 @ 群发报错
    out = _transform(["@a @b hi"])
    assert "at_error" in out[0] and "群发" in out[0]


def test_empty_message_errors():                    # @name 空消息报错
    out = _transform(["@alice"])
    assert "at_error" in out[0] and "空" in out[0]


def test_routes_single_at():                        # @name msg → at_route
    out = _transform(["@alice hello world"])
    assert "at_route('alice', 'hello world')" in out[0]


def test_at_error_raises_syntax_error():
    with pytest.raises(SyntaxError):
        at_error("bad")


def test_at_route_missing_agent_raises():           # 无 IPython → 找不到 agent
    import prism.router as R
    orig = R.get_ipython if hasattr(R, "get_ipython") else None
    # at_route 内部 from IPython import get_ipython; patch 该 import
    import sys
    import types
    fake = types.ModuleType("IPython")
    fake.get_ipython = lambda: None
    real = sys.modules.get("IPython")
    sys.modules["IPython"] = fake
    try:
        with pytest.raises(NameError):
            at_route("ghost", "hi")
    finally:
        if real:
            sys.modules["IPython"] = real
        else:
            sys.modules.pop("IPython", None)
