"""prism/forest.py — SQLiteForest(认知树存储, RLM Phase B)。

实现 prism/cognitive.py 的 Forest ABC。选 SQLite(见 plan/rlm/persistence.md):
  - 递归 CTE 天生做树搜索(causes / based_on 两轴遍历)
  - 增量 INSERT / stdlib 零依赖 / 事务安全 / 可插拔(与 MemoryBackend 一致)

一树两轴(plan/rlm/tree.md):
  - causes 轴: thinking↔thinking, 树(单父), 搜索/失败回溯 —— add_node(parent=) 自动建 causes 边
  - based_on 轴: thinking→thinking(任意), 图, 自指/套娃 —— add_edge(src, BASED_ON, dst)
  - bridge: produces/evidences(thinking↔context)
任务隔离: 同 session 多棵树(tree_id); 新树根(parent=None)自动分配 tree_id。

==============================================================================
复杂度(research/complexity_bench.py 实证):
  写 add_node        : O(log N) INSERT + O(1) meta 维护; 常数由 WAL 降到 ~μs
  写 add_edge / mark : O(log N)
  读 trees()         : O(T)  (T=树数, 不是节点数 N) ← meta 表, 不全表扫
  读 nodes_in_tree   : O(K)  K=该树节点数, 走覆盖索引
  读 subtree/walk    : O(K') K'=可达节点数(递归 CTE, 必访问最优)
  读 recent_in_tree  : O(L)  L=limit, 走 (sid,tid,type,status,id) 索引倒序 top-N
关键: trees()/nodes_in_tree 不再随总节点数 N 线性增长(research/ANALYSIS.md)。
==============================================================================
"""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

from .cognitive import Forest, ACTIVE, CAUSES


class SQLiteForest(Forest):
    """认知树存储(SQLite + 递归 CTE + WAL)。一个实例绑一个 session_id。"""

    def __init__(self, db_path, session_id: str = "default"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        # WAL: 写不阻塞读, synchronous=NORMAL 把 per-commit fsync 降级
        # (默认 DELETE+FULL 每次 commit 同步刷盘 ~12ms; NORMAL 下 <1ms)。
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._init_schema()
        # tree_id 分配器: meta 表存, init/reopen O(1) 恢复(不再 SELECT MAX 全表扫)
        self._next_tree_id = self._load_meta("next_tree_id", 0) + 1

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
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src, relation);
            CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst, relation);
            -- 树定位(原有)
            CREATE INDEX IF NOT EXISTS idx_nodes_tree ON nodes(session_id, tree_id);
            -- 覆盖索引: 直觉 search-state 按 (type,status) 过滤 + id 倒序 top-N
            CREATE INDEX IF NOT EXISTS idx_nodes_tree_filter
                ON nodes(session_id, tree_id, type, status, id);
            -- nodes_in_tree 的 ORDER BY created_at 走索引(避免树内 filesort)
            CREATE INDEX IF NOT EXISTS idx_nodes_tree_created
                ON nodes(session_id, tree_id, created_at);
        """)
        self._conn.commit()

    # ── meta(单调计数器, O(1) 恢复; 替代 SELECT MAX 全表扫) ──
    def _load_meta(self, key: str, default: int = 0) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return int(row["value"]) if row else default

    def _save_meta(self, key: str, value: int) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))

    def _alloc_tree_id(self) -> int:
        """分配一棵新树的 id 并持久化(崩溃安全: 与节点同一事务 commit)。"""
        tid = self._next_tree_id
        self._next_tree_id += 1
        self._save_meta("next_tree_id", self._next_tree_id)
        return tid

    # ── Forest ABC ──────────────────────────────────────
    def add_node(self, *, category: str, type: str, content: str,
                 parent: int | None = None, status: str = ACTIVE,
                 tree_id: int | None = None) -> int:
        """加节点。parent → 自动建 causes 边(parent→child)。parent=None → 新树根。"""
        if tree_id is None:
            if parent is not None:
                prow = self._conn.execute(
                    "SELECT tree_id FROM nodes WHERE id=?", (parent,)).fetchone()
                # parent 存在 → 继承其树; parent 查不到(孤儿)→ 分配新树(非共享, 修复旧 bug)
                tree_id = int(prow["tree_id"]) if prow else self._alloc_tree_id()
            else:
                tree_id = self._alloc_tree_id()
        cur = self._conn.execute(
            "INSERT INTO nodes(session_id, tree_id, parent_id, category, type, status, content, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (self.session_id, tree_id, parent, category, type, status, content, time.time()))
        nid = cur.lastrowid
        if parent is not None:
            # causes 边与节点同一事务, 一次 commit(WAL 下 ~μs)
            self._conn.execute(
                "INSERT OR IGNORE INTO edges(src, relation, dst) VALUES (?,?,?)",
                (parent, CAUSES, nid))
        self._conn.commit()
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
        复杂度 O(K'), K'=可达节点数(递归 CTE 最优: 只访问实际可达的节点/边)。
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
        """本 session 所有 tree_id(任务隔离:一棵树=一个任务)。
        O(T) 走 idx_nodes_tree 的有序前缀, 非全表 DISTINCT 扫所有节点。
        """
        rows = self._conn.execute(
            "SELECT DISTINCT tree_id FROM nodes WHERE session_id=? ORDER BY tree_id",
            (self.session_id,)).fetchall()
        return [int(r["tree_id"]) for r in rows]

    def nodes_in_tree(self, tree_id: int) -> list[dict]:
        """某棵树全部节点(按时间序)。实验/观测用。走 idx_nodes_tree_created 索引。"""
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE session_id=? AND tree_id=? ORDER BY created_at",
            (self.session_id, tree_id)).fetchall()
        return [dict(r) for r in rows]

    def recent_in_tree(self, tree_id: int, *, type: str | None = None,
                       status: str | None = None, limit: int | None = None) -> list[dict]:
        """索引友好查询: 在某树内按 (type,status) 过滤, 取最近 limit 个(id 倒序≈时间倒序)。

        直觉 search-state 的热路径用这个: O(L) 而非 O(K), K=该树总节点数。
        走 idx_nodes_tree_filter(session_id, tree_id, type, status, id) 倒序 top-N。
        id 是自增主键 = 插入序 = created_at 序(单链创建下严格对应)。
        """
        sql = ("SELECT * FROM nodes WHERE session_id=? AND tree_id=?")
        args: list = [self.session_id, tree_id]
        if type is not None:
            sql += " AND type=?"; args.append(type)
        if status is not None:
            sql += " AND status=?"; args.append(status)
        sql += " ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"; args.append(limit)
        rows = self._conn.execute(sql, args).fetchall()
        # 调用方(直觉)期望时间正序展示, 翻转回正序
        return [dict(r) for r in reversed(rows)]

    def last_tree_id(self) -> int | None:
        """最新树的 tree_id(直觉直接用, 不再 trees() 全扫)。None=空。O(1)。"""
        row = self._conn.execute(
            "SELECT tree_id FROM nodes WHERE session_id=? "
            "ORDER BY id DESC LIMIT 1",
            (self.session_id,)).fetchone()
        return int(row["tree_id"]) if row else None

    def close(self) -> None:
        self._conn.close()
