"""research/complexity_bench.py — SQLiteForest 复杂度实证。

测量「增加节点」与「搜索」两类核心操作随规模 N 的耗时, 验证复杂度猜想。

被测操作:
  写: add_node (单次)          ← 增加
  写: add_edge (单次)
  读: trees()                  ← 搜索辅助(直觉热路径)
  读: nodes_in_tree(tid)       ← 搜索辅助(直觉热路径)
  读: subtree(root)            ← 搜索(causes 子树)
  读: walk(node, CAUSES)       ← 搜索(causes 链)
  读: walk(node, BASED_ON)     ← 搜索(自指链)
  组合: HeuristicIntuition.select_context(单次)  ← 认知循环热路径

每档 N 重复 R 次取中位数(微秒)。
"""
from __future__ import annotations
import statistics
import sys
import time
from pathlib import Path

# 强制用 worktree 本地代码
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prism.cognitive import THINKING, CONTEXT, ACTIVE, FAILED, CAUSES, BASED_ON  # noqa: E402
from prism.forest import SQLiteForest  # noqa: E402
from prism.cog_intuition import HeuristicIntuition  # noqa: E402


def _time_us(fn, repeats=200) -> float:
    """重复跑 fn, 返回中位数耗时(μs)。"""
    ts = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(ts)


def build_forest(n: int, tmp: Path) -> SQLiteForest:
    """建一棵 N 节点的 causes 线性链 + 1/10 节点的 based_on 回环。返回 forest。"""
    f = SQLiteForest(tmp / f"f_{n}.db", session_id="bench")
    root = f.add_node(category=THINKING, type="thought", content="root")
    prev = root
    ids = [root]
    # 线性 causes 链(模拟 AutoAttachHook 挂树)
    for i in range(1, n):
        prev = f.add_node(category=THINKING, type="thought",
                          content=f"t{i}", parent=prev)
        ids.append(prev)
    # 10% 节点标 failed(回溯), 5% 标 reflection
    for idx in ids[::10]:
        f.mark(idx, FAILED)
    for idx in ids[::20]:
        # 加 based_on 自指回环(指向上游 5 个)
        target = ids[max(0, ids.index(idx) - 5)]
        if target != idx:
            f.add_edge(idx, BASED_ON, target)
    return f


def bench(n: int, tmp: Path) -> dict:
    f = build_forest(n, tmp)
    root = 1
    tip = n  # 链尾 id
    tree_ids = f.trees()
    tid = tree_ids[0]
    intu = HeuristicIntuition(f, max_thoughts=5)

    class _FakeAgent:
        """select_context 需要 agent.emit; 给个空实现。"""
        def emit(self, ev):
            pass

    a = _FakeAgent()
    res = {"N": n}
    # 写: add_node(挂到 tip)
    res["add_node_us"] = _time_us(
        lambda: f.add_node(category=THINKING, type="thought",
                           content="x", parent=tip), repeats=50)
    # 写: add_edge
    res["add_edge_us"] = _time_us(
        lambda: f.add_edge(tip, BASED_ON, root), repeats=50)
    # 读: trees()  ← 直觉热路径
    res["trees_us"] = _time_us(lambda: f.trees(), repeats=100)
    # 读: nodes_in_tree(tid)
    res["nodes_in_tree_us"] = _time_us(lambda: f.nodes_in_tree(tid), repeats=100)
    # 读: subtree(root)  ← 整树(最坏)
    res["subtree_us"] = _time_us(lambda: f.subtree(root), repeats=50)
    # 读: walk(root, CAUSES) ← 整条 causes 链
    res["walk_causes_us"] = _time_us(lambda: f.walk(root, CAUSES), repeats=50)
    # 读: walk(tip, BASED_ON) ← 自指链(短)
    res["walk_based_on_us"] = _time_us(lambda: f.walk(tip, BASED_ON), repeats=100)
    # 组合: 直觉 search-state(认知循环热路径, 每轮调)
    res["intuition_us"] = _time_us(
        lambda: intu.select_context(a, {}), repeats=50)
    f.close()
    return res


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        print(f"{'N':>6} | {'add_node':>9} {'add_edge':>9} | "
              f"{'trees':>8} {'nodes_in_tree':>14} {'subtree':>9} "
              f"{'walk_causes':>11} {'walk_based_on':>13} | {'intuition':>10}   (μs, median)")
        print("-" * 110)
        for n in (100, 500, 1000, 3000, 6000):
            r = bench(n, tmp)
            print(f"{r['N']:>6} | {r['add_node_us']:>9.1f} {r['add_edge_us']:>9.1f} | "
                  f"{r['trees_us']:>8.1f} {r['nodes_in_tree_us']:>14.1f} {r['subtree_us']:>9.1f} "
                  f"{r['walk_causes_us']:>11.1f} {r['walk_based_on_us']:>13.1f} | "
                  f"{r['intuition_us']:>10.1f}")


if __name__ == "__main__":
    main()
