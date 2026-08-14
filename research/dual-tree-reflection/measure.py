"""research/dual-tree-reflection/measure.py — D2 measurement(反思链条结构化指标)。

用法:
  python measure.py [runs_dir]        # 默认 research/dual-tree-reflection/runs

对每个 run 目录:
  - tree 条件: 读 forest.db(只读) → dump tree.json(全节点+边) + 结构指标
  - 全条件:   读 events.jsonl → 工具行为指标(reflect 调用 / raw forest 操作 / mark failed)
  - 汇总 runs/metrics.json + 打印对照表

核心指标(H1 结构性反思链条):
  reflections        reflection 节点数(总数)
  based_on_edges     based_on 边数(反思连回被反思节点 = 自指链存在)
  refl_linked        有 based_on 出边的 reflection 数(非孤立反思占比的分母)
  based_on_max_chain 最长 based_on 链长(>=2 即"反思的反思"套娃出现)
  failed_marks       mark(failed) 的节点数(搜索轴回溯痕迹)
  reflect_calls      reflect 工具调用次数(events)
  raw_forest_ops     python 工具里直接操作 .forest.* 的次数(events)
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def read_forest(db_path: Path, session: str) -> tuple[list[dict], list[dict]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    nodes = [dict(r) for r in conn.execute(
        "SELECT * FROM nodes WHERE session_id=? ORDER BY id", (session,))]
    edges = [dict(r) for r in conn.execute("SELECT * FROM edges ORDER BY src, relation, dst")]
    conn.close()
    return nodes, edges


def longest_chain(edges: list[dict], relation: str) -> int:
    """relation 边(src→dst)构成的最长链(边数)。迭代松弛; 不收敛(有环)返回 -1 —— based_on 出现环本身即异常信号。"""
    rel = [(e["src"], e["dst"]) for e in edges if e["relation"] == relation]
    if not rel:
        return 0
    dist: dict[int, int] = {}
    converged = False
    for _ in range(len(rel) + 1):            # DAG 收敛上限 = 边数
        changed = False
        for s, d in rel:
            v = dist.get(d, 0) + 1
            if v > dist.get(s, 0):
                dist[s] = v
                changed = True
        if not changed:
            converged = True
            break
    if not converged:
        return -1                            # 有环: based_on 出现环(本身即异常信号)
    return max(dist.values(), default=0)


def tree_metrics(run: Path, session: str) -> dict:
    nodes, edges = read_forest(run / "forest.db", session)
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
    based = [e for e in edges if e["relation"] == "based_on"]
    refl_ids = {n["id"] for n in nodes if n["type"] == "reflection"}
    refl_linked = len({e["src"] for e in based} & refl_ids)
    # causes 分叉度: 有 >=2 个 causes 子节点的节点数(真分叉 = 搜索轴换过路)
    children: dict[int, int] = {}
    for e in edges:
        if e["relation"] == "causes":
            children[e["src"]] = children.get(e["src"], 0) + 1
    branched = sum(1 for c in children.values() if c >= 2)
    # causes 最深链(整树深度)
    max_causes_depth = longest_chain(edges, "causes")
    return {
        "nodes_total": len(nodes), "nodes_by_type": by_type, "nodes_by_status": by_status,
        "edges_by_relation": {r: sum(1 for e in edges if e["relation"] == r)
                              for r in {e["relation"] for e in edges}},
        "reflections": by_type.get("reflection", 0),
        "patterns": by_type.get("pattern", 0),
        "based_on_edges": len(based),
        "refl_linked": refl_linked,
        "based_on_max_chain": longest_chain(edges, "based_on"),
        "failed_marks": by_status.get("failed", 0),
        "causes_branched_nodes": branched,
        "causes_max_depth": max_causes_depth,
        "_tree_dump": {"nodes": nodes, "edges": edges},
    }


def event_metrics(run: Path) -> dict:
    ev_path = run / "events.jsonl"
    calls = reflect_calls = 0
    raw_forest_ops = mark_failed_calls = 0
    python_runs = errors = 0
    if ev_path.exists():
        for line in ev_path.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "tool_execution_start":
                calls += 1
                name = ev.get("tool_name", "")
                args = str(ev.get("args", ""))
                if name == "reflect":
                    reflect_calls += 1
                elif name == "python":
                    python_runs += 1
                    if ".forest." in args:
                        raw_forest_ops += 1
                    if ".forest.mark" in args:
                        mark_failed_calls += 1
            elif ev.get("type") == "tool_execution_end" and ev.get("is_error"):
                errors += 1
    return {"tool_calls": calls, "reflect_calls": reflect_calls,
            "python_runs": python_runs, "raw_forest_ops": raw_forest_ops,
            "mark_failed_calls": mark_failed_calls, "tool_errors": errors}


def main() -> None:
    runs = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS_DIR
    if not runs.exists():
        sys.exit(f"runs 目录不存在: {runs}")
    all_metrics: dict[str, dict] = {}
    for run in sorted(p for p in runs.iterdir() if p.is_dir() and not p.name.startswith("_")):
        meta_path = run / "meta.json"
        if not meta_path.exists():
            all_metrics[run.name] = {"status": "no meta(未完成或崩溃)"}
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        m: dict = {"condition": meta.get("condition"), "duration_s": meta.get("duration_s"),
                   "game_html_bytes": meta.get("game_html_bytes", 0)}
        m.update(event_metrics(run))
        if (run / "forest.db").exists():
            tm = tree_metrics(run, meta.get("name", run.name))
            dump = tm.pop("_tree_dump")
            (run / "tree.json").write_text(json.dumps(dump, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
            m.update(tm)
        all_metrics[run.name] = m
    (runs / "metrics.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=1),
                                       encoding="utf-8")

    # 对照表(关键列)
    hdr = ["run", "cond", "nodes", "refl", "based_on", "refl_link", "bo_chain",
           "failed", "branch", "reflect_calls", "raw_ops", "mark_calls", "game_kb", "dur_s"]
    print(("{:<22}" + "{:>7}" * (len(hdr) - 2)).format(*hdr))
    for name, m in all_metrics.items():
        if "condition" not in m:
            print(f"{name:<22}  {m.get('status', '?')}")
            continue
        print(("{:<22}" + "{:>7}" * (len(hdr) - 2)).format(
            name[:22], m["condition"][:4], m.get("nodes_total", 0),
            m.get("reflections", 0), m.get("based_on_edges", 0), m.get("refl_linked", 0),
            m.get("based_on_max_chain", 0), m.get("failed_marks", 0),
            m.get("causes_branched_nodes", 0), m["reflect_calls"], m["raw_forest_ops"],
            m["mark_failed_calls"], round(m["game_html_bytes"] / 1024), m["duration_s"]))
    print(f"\n-> {runs / 'metrics.json'}")


if __name__ == "__main__":
    main()
