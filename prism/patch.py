"""PatchRegistry — agent_loop 扩展点 patch 系统(原则 11)。

五扩展点(原则 11): build_messages / stream_response / execute_tools / should_stop / emit
每点支持 before / after / around 三类 patch。

约定:
  before(point, ctx)           副作用, 无返回; 在原逻辑前跑
  after(point, ctx)            副作用, 无返回; 在原逻辑后跑
  around(point, ctx, proceed)  包裹原逻辑; proceed(ctx) 进内层/原逻辑; 返回值透传

around 链顺序: 注册顺序 = 外→内(先注册的最外层包裹)。

异常降级(原则 11): 任何 patch 抛异常 → 捕获 + emit patch_error + 跳过该 patch,
不向上抛(around 降级 = 跳过该层走 proceed)。patch 是装饰, 不该炸主逻辑。

线程安全: 注册用 append(主线程加载期), 运行期只读遍历。多 agent 并发各自持有
registry 实例(原则 12 非单例), 不共享, 无锁需求。
"""
from __future__ import annotations
from typing import Any, Callable

VALID_POINTS = ("build_messages", "stream_response", "execute_tools", "should_stop", "emit")


class PatchError(Exception):
    """扩展点/patch 相关错误(未知点等)。"""


class PatchRegistry:
    """五扩展点 × (before/after/around) 的注册表。

    emit 回调用于 patch 异常时发 patch_error 事件(走 agent 事件流, 跟其他 emit 一致)。
    """

    def __init__(self, emit: Callable[[dict], None] | None = None):
        self._emit = emit or (lambda e: None)
        self._before: dict[str, list[Callable]] = {p: [] for p in VALID_POINTS}
        self._after: dict[str, list[Callable]] = {p: [] for p in VALID_POINTS}
        self._around: dict[str, list[Callable]] = {p: [] for p in VALID_POINTS}

    # ── 注册 ──────────────────────────────────────────
    def _check_point(self, point: str) -> None:
        if point not in VALID_POINTS:
            raise PatchError(f"未知扩展点 '{point}'。合法: {VALID_POINTS}")

    def before(self, point: str, fn: Callable[[dict], None]) -> None:
        self._check_point(point)
        self._before[point].append(fn)

    def after(self, point: str, fn: Callable[[dict], None]) -> None:
        self._check_point(point)
        self._after[point].append(fn)

    def around(self, point: str, fn: Callable[[dict, Callable], Any]) -> None:
        self._check_point(point)
        self._around[point].append(fn)

    def has(self, point: str) -> bool:
        """该点是否有任何 patch(用于 agent_loop 决定要不要走 patch 路径)。"""
        return bool(self._before[point] or self._after[point] or self._around[point])

    # ── 执行 ──────────────────────────────────────────
    def run_before(self, point: str, ctx: dict) -> None:
        for fn in self._before[point]:
            try:
                fn(ctx)
            except Exception as e:
                self._emit({"type": "patch_error", "phase": "before", "point": point,
                            "error": f"{type(e).__name__}: {e}"})

    def run_after(self, point: str, ctx: dict) -> None:
        for fn in self._after[point]:
            try:
                fn(ctx)
            except Exception as e:
                self._emit({"type": "patch_error", "phase": "after", "point": point,
                            "error": f"{type(e).__name__}: {e}"})

    def apply_around(self, point: str, ctx: dict, proceed: Callable[[dict], Any]) -> Any:
        """串 around 链(注册顺序 = 外→内), 逐层包裹 proceed。异常降级跳过该层。"""
        chain = self._around[point]
        if not chain:
            return proceed(ctx)

        def make_layer(i: int) -> Callable[[dict], Any]:
            if i >= len(chain):
                return proceed                      # 最内层 = 原逻辑
            fn = chain[i]
            inner = make_layer(i + 1)

            def layer(c: dict) -> Any:
                try:
                    return fn(c, inner)
                except Exception as e:
                    self._emit({"type": "patch_error", "phase": "around", "point": point,
                                "error": f"{type(e).__name__}: {e}"})
                    return inner(c)                 # 降级: 跳过本层, 走内层
            return layer

        return make_layer(0)(ctx)
