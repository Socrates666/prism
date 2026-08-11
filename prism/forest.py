"""prism/forest.py — SQLiteForest(认知树存储, RLM Phase B)。

实现 prism/cognitive.py 的 Forest ABC。选 SQLite(见 plan/rlm/persistence.md):
  - 递归 CTE 天生做树搜索(causes / based_on 两轴遍历)
  - 增量 INSERT / stdlib 零依赖 / 事务安全 / 可插拔(与 MemoryBackend 一致)

一树两轴(plan/rlm/tree.md):
  - causes 轴: thinking↔thinking, 树(单父), 搜索/失败回溯 —— add_node(parent=) 自动建 causes 边
  - based_on 轴: thinking→thinking(任意), 图, 自指/套娃 —— add_edge(src, BASED_ON, dst)
  - bridge: produces/evidences(thinking↔context)
任务隔离: 同 session 多棵树(tree_id); 新树根(parent=None)自动分配 tree_id。
"""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

from .cognitive import Forest, ACTIVE, CAUSES


class SQLiteForest(Forest):
    """认知树存储(SQLite + 递归 CTE)。一个实例绑一个 session_id。"""

    def __init__(self, db_path, session_id: str = "default"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._tree_seq = self._max_tree_id() + 1   # 下一棵新树的 id

    # ── schema ──────────────────────────────────────────
    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tree_id    INTEGER NOT NULL,
                parent_id  INTEGER,
                category   TEXT NOT NULL,
                type       TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'active',
                content    TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                src      INTEGER NOT NULL REFERENCES nodes(id),
                relation TEXT NOT NULL,
                dst      INTEGER NOT NULL REFERENCES nodes(id),
                PRIMARY KEY (src, relation, dst)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src, relation);
            CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst, relation);
            CREATE INDEX IF NOT EXISTS idx_nodes_tree ON nodes(session_id, tree_id);
        """)
        self._conn.commit()

    def _max_tree_id(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(tree_id), 0) FROM nodes WHERE session_id=?",
            (self.session_id,)).fetchone()
        return int(row[0])

    # ── Forest ABC ──────────────────────────────────────
    def add_node(self, *, category: str, type: str, content: str,
                 parent: int | None = None, status: str = ACTIVE,
                 tree_id: int | None = None) -> int:
        """加节点。parent → 自动建 causes 边(parent→child)。parent=None → 新树根。"""
        if tree_id is None:
            if parent is not None:
                prow = self._conn.execute(
                    "SELECT tree_id FROM nodes WHERE id=?", (parent,)).fetchone()
                tree_id = int(prow["tree_id"]) if prow else self._tree_seq
            else:
                tree_id = self._tree_seq
                self._tree_seq += 1
        cur = self._conn.execute(
            "INSERT INTO nodes(session_id, tree_id, parent_id, category, type, status, content, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (self.session_id, tree_id, parent, category, type, status, content, time.time()))
        nid = cur.lastrowid
        self._conn.commit()
        if parent is not None:
            self.add_edge(parent, CAUSES, nid)   # causes: parent → child(搜索树位置)
        return nid

    def add_edge(self, src: int, relation: str, dst: int) -> None:
        """加任意边(based_on 自指 / produces / evidences / temporal / references)。"""
        self._conn.execute(
            "INSERT OR IGNORE INTO edges(src, relation, dst) VALUES (?,?,?)",
            (src, relation, dst))
        self._conn.commit()

    def mark(self, node_id: int, status: str) -> None:
        """标节点状态(active/failed/success)—— 失败回溯用。"""
        self._conn.execute("UPDATE nodes SET status=? WHERE id=?", (status, node_id))
        self._conn.commit()

    def get(self, node_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    def subtree(self, root: int) -> list[dict]:
        """causes 子树(含 root + 全部 causes 后代, 按时间序)。横向分治 / spawn 子树。"""
        rows = self._conn.execute(
            "WITH RECURSIVE desc(id) AS ("
            "  SELECT id FROM nodes WHERE id=?"
            "  UNION ALL"
            "  SELECT e.dst FROM edges e JOIN desc ON e.src=desc.id WHERE e.relation=?"
            ") SELECT n.* FROM nodes n JOIN desc ON n.id=desc.id ORDER BY n.created_at",
            (root, CAUSES)).fetchall()
        return [dict(r) for r in rows]

    def walk(self, node: int, relation: str, depth: int | None = None) -> list[dict]:
        """沿 relation 边递归走(src→dst), 不含 node 自身。
        causes → 搜索链; based_on → 自指链(套娃路径)。depth 限跳数。
        """
        if depth is not None:
            sql = (
                "WITH RECURSIVE reach(id, d) AS ("
                "  SELECT dst, 1 FROM edges WHERE src=? AND relation=?"
                "  UNION ALL"
                "  SELECT e.dst, r.d+1 FROM edges e JOIN reach r ON e.src=r.id "
                "  WHERE e.relation=? AND r.d+1 <= ?"
                ") SELECT n.* FROM nodes n JOIN reach ON n.id=reach.id ORDER BY n.created_at")
            rows = self._conn.execute(sql, (node, relation, relation, depth)).fetchall()
        else:
            sql = (
                "WITH RECURSIVE reach(id) AS ("
                "  SELECT dst FROM edges WHERE src=? AND relation=?"
                "  UNION ALL"
                "  SELECT e.dst FROM edges e JOIN reach r ON e.src=r.id WHERE e.relation=?"
                ") SELECT n.* FROM nodes n JOIN reach ON n.id=reach.id ORDER BY n.created_at")
            rows = self._conn.execute(sql, (node, relation, relation)).fetchall()
        return [dict(r) for r in rows]

    def trees(self) -> list[int]:
        """本 session 所有 tree_id(任务隔离:一棵树=一个任务)。"""
        rows = self._conn.execute(
            "SELECT DISTINCT tree_id FROM nodes WHERE session_id=? ORDER BY tree_id",
            (self.session_id,)).fetchall()
        return [int(r["tree_id"]) for r in rows]

    def nodes_in_tree(self, tree_id: int) -> list[dict]:
        """某棵树全部节点(按时间序)。实验/观测用。"""
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE session_id=? AND tree_id=? ORDER BY created_at",
            (self.session_id, tree_id)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
