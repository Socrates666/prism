"""PatchRegistry 单元测试(阶段 3a, 原则 11)。"""
import pytest
from prism.patch import PatchRegistry, PatchError, VALID_POINTS


def test_before_runs_fn_with_ctx():
    reg = PatchRegistry()
    seen = []
    reg.before("execute_tools", lambda ctx: seen.append(ctx.get("x")))
    reg.run_before("execute_tools", {"x": 1})
    assert seen == [1]                                   # [C1]


def test_after_runs_fn_with_ctx():
    reg = PatchRegistry()
    seen = []
    reg.after("execute_tools", lambda ctx: seen.append("ran"))
    reg.run_after("execute_tools", {})
    assert seen == ["ran"]                               # [C2]


def test_around_wraps_proceed_changes_result():
    reg = PatchRegistry()
    reg.around("execute_tools", lambda ctx, p: p(ctx) * 2)
    out = reg.apply_around("execute_tools", {}, lambda ctx: 21)
    assert out == 42                                     # [C3]


def test_around_chain_order_outer_to_inner():
    reg = PatchRegistry()
    log = []

    def mk(tag):
        def layer(ctx, proceed):
            log.append(f"{tag}-in")
            r = proceed(ctx)
            log.append(f"{tag}-out")
            return r
        return layer

    reg.around("execute_tools", mk("A"))                 # 先注册 = 最外层
    reg.around("execute_tools", mk("B"))
    reg.apply_around("execute_tools", {}, lambda ctx: log.append("core"))
    assert log == ["A-in", "B-in", "core", "B-out", "A-out"]   # [C4]


def test_around_exception_degrades_to_proceed():
    emitted = []
    reg = PatchRegistry(emit=lambda e: emitted.append(e))

    def boom(ctx, proceed):
        raise ValueError("patch broken")

    reg.around("execute_tools", boom)
    out = reg.apply_around("execute_tools", {}, lambda ctx: "ok")
    assert out == "ok"                                   # 降级走 proceed  [C5]
    assert any(e["type"] == "patch_error" and e["phase"] == "around" for e in emitted)


def test_no_patch_apply_around_is_passthrough():
    reg = PatchRegistry()
    out = reg.apply_around("execute_tools", {"v": 5}, lambda ctx: ctx["v"] + 1)
    assert out == 6                                      # [C6]


def test_unknown_point_raises():
    reg = PatchRegistry()
    with pytest.raises(PatchError):
        reg.before("no_such_point", lambda ctx: None)
    with pytest.raises(PatchError):
        reg.around("bogus", lambda ctx, p: p(ctx))      # [C7]


def test_before_exception_does_not_propagate():
    emitted = []
    reg = PatchRegistry(emit=lambda e: emitted.append(e))
    reg.before("execute_tools", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")))
    reg.run_before("execute_tools", {})                  # 不应抛
    assert any(e["phase"] == "before" for e in emitted)


def test_all_points_accept_each_kind():
    reg = PatchRegistry()
    for pt in VALID_POINTS:
        reg.before(pt, lambda ctx: None)
        reg.after(pt, lambda ctx: None)
        reg.around(pt, lambda ctx, proceed: proceed(ctx))
    assert reg.has("emit")
