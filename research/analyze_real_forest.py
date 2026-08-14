"""research/analyze_real_forest.py — 分析主工作区真实运行 forest.db, 验证设计是否生效。"""
import sqlite3
import sys
from pathlib import Path
from collections import Counter

# Windows 控制台默认 GBK, 强制 UTF-8 输出中文/符号
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../.prism/forest.db")
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def sep(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)


sep("0. 总览")
print("tables:", [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
print(f"nodes: {c.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]}")
print(f"edges: {c.execute('SELECT COUNT(*) FROM edges').fetchone()[0]}")
print("sessions:", [r[0] for r in c.execute("SELECT DISTINCT session_id FROM nodes")])

sep("1. 任务隔离: 每 session 几棵树?")
for r in c.execute("SELECT session_id, COUNT(DISTINCT tree_id) t, COUNT(*) n "
                   "FROM nodes GROUP BY session_id ORDER BY n DESC"):
    print(f"  {r['session_id']}: {r['t']} 棵树, {r['n']} 节点")

sep("2. 边 relation 分布 (验证两轴: causes 搜索 / based_on 自指)")
for r in c.execute("SELECT relation, COUNT(*) c FROM edges GROUP BY relation ORDER BY c DESC"):
    print(f"  {r['relation']:12}: {r['c']}")

sep("3. 节点 type 分布 (思维类: thought/action/reflection / 上下文: result)")
for r in c.execute("SELECT type, COUNT(*) c FROM nodes GROUP BY type ORDER BY c DESC"):
    print(f"  {r['type']:12}: {r['c']}")

sep("4. 节点 status 分布 (active/failed/success —— 回溯是否生效)")
for r in c.execute("SELECT status, COUNT(*) c FROM nodes GROUP BY status ORDER BY c DESC"):
    print(f"  {r['status']:12}: {r['c']}")

sep("5. causes 轴: 是否真成树? (每节点最多 1 个 causes 父)")
multi = c.execute("SELECT COUNT(*) FROM (SELECT dst FROM edges WHERE relation='causes' "
                  "GROUP BY dst HAVING COUNT(*) > 1)").fetchone()[0]
print(f"  有多个 causes 父的节点数: {multi}  (应为 0 = 严格树)")
roots = c.execute("SELECT COUNT(*) FROM nodes n WHERE NOT EXISTS "
                  "(SELECT 1 FROM edges e WHERE e.relation='causes' AND e.dst=n.id)").fetchone()[0]
print(f"  causes 树根数(无 causes 入边): {roots}  (应≈树数)")

sep("6. based_on 轴: 有没有自指链? (套娃 = RLM 核心)")
bo = c.execute("SELECT COUNT(*) FROM edges WHERE relation='based_on'").fetchone()[0]
print(f"  based_on 边总数: {bo}")
if bo:
    for r in c.execute("SELECT s.type st, substr(s.content,1,40) sc, d.type dt, substr(d.content,1,40) dc "
                       "FROM edges e JOIN nodes s ON e.src=s.id JOIN nodes d ON e.dst=d.id "
                       "WHERE e.relation='based_on' LIMIT 8"):
        print(f"    [{r['st']}] {r['sc']}  ->based_on->  [{r['dt']}] {r['dc']}")

sep("7. causes 分叉度: 真在搜索(另开支)还是纯线性日志?")
branch = Counter()
for r in c.execute("SELECT src, COUNT(*) c FROM edges WHERE relation='causes' GROUP BY src"):
    branch[r["c"]] += 1
print("  causes 子节点数 -> 这样的父节点数:")
for k in sorted(branch):
    tag = "  <-- 纯线性(每节点1子)" if k == 1 else "  <-- 分叉(搜索另开支/回溯)"
    print(f"    {k} 子: {branch[k]} 个父{tag}")
linear = branch.get(1, 0)
branched = sum(v for k, v in branch.items() if k > 1)
print(f"\n  纯线性父(1子): {linear} | 分叉父(>1子): {branched}")
print("  分叉父=0 => 树退化为线性事件日志, 无搜索分叉/回溯")

sep("8. thought 节点内容抽样(验证是不是真在'思考')")
rows = c.execute("SELECT id, substr(content,1,62) c FROM nodes WHERE type='thought' "
                 "ORDER BY RANDOM() LIMIT 8").fetchall()
for r in rows:
    print(f"    #{r['id']}: {r['c']}")

sep("9. reflection 节点(自指入口, design 说这是 RLM 核心)")
rows = c.execute("SELECT id, substr(content,1,70) c FROM nodes WHERE type='reflection'").fetchall()
print(f"  reflection 节点数: {len(rows)}")
for r in rows:
    print(f"    #{r['id']}: {r['c']}")

sep("10. 最大树前 18 节点(看实际生长形态)")
top = c.execute("SELECT tree_id, session_id, COUNT(*) n FROM nodes "
                "GROUP BY tree_id, session_id ORDER BY n DESC LIMIT 1").fetchone()
if top:
    tid, sid = top["tree_id"], top["session_id"]
    print(f"  树 tree_id={tid} ({top['n']} 节点):")
    for x in c.execute("SELECT id, type, status, substr(content,1,48) content FROM nodes "
                       "WHERE session_id=? AND tree_id=? ORDER BY id LIMIT 18", (sid, tid)):
        print(f"    #{x['id']:>3} [{x['type']:9}] {x['content']}")

c.close()
