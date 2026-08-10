# SQLite Forest · 持久化

> 本篇回答:**认知树怎么存、为什么 SQLite。**

## 选型对比

| 方案 | 增量写 | 树搜索 | 零依赖 | 事务安全 | 内存友好 | 可插拔 |
|------|:------:|:------:|:------:|:--------:|:--------:|:------:|
| JSON/JSONL(现 memory.py) | △(全量重写) | ✗(全扫) | ✓ | ✗ | △ | ✓ |
| **SQLite** | **✓**(INSERT) | **✓**(递归 CTE) | **✓**(stdlib) | **✓**(WAL) | **✓** | **✓** |
| Mem0(向量库) | ✓ | △(相似度非树) | ✗(依赖) | △ | ✗ | ✓ |
| 纯内存 | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |

**选 SQLite**。决定性理由:
1. **递归 CTE 天生做树搜索**——"沿 causes 深入 N 层""沿 based_on 反溯根因"是一条 SQL。
2. **增量 INSERT**——认知事件频繁,不能每次全量重写 JSON。
3. **stdlib 零依赖**(`sqlite3`),跟 memory.py 的"NullMemory 默认能跑"精神一致。
4. **与 MemoryBackend 可插拔一致**(原则 7)——Forest 是 CognitiveBackend,默认 SQLiteForest,可换 NullForest(R0 退化)。

## schema(含 round 8 的节点状态 + 两类节点)

```sql
CREATE TABLE nodes (
    id          INTEGER PRIMARY KEY,
    session_id  TEXT NOT NULL,
    tree_id     INTEGER NOT NULL,        -- 同 session 多棵树(任务隔离)
    parent_id   INTEGER,                 -- temporal 父边
    category    TEXT NOT NULL,           -- thought(思维) / context(上下文)
    type        TEXT NOT NULL,           -- thought/action/result/reflection/pattern
    status      TEXT DEFAULT 'active',   -- active / failed / success(round 8 回溯)
    content     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE edges (
    src      INTEGER REFERENCES nodes(id),
    dst      INTEGER REFERENCES nodes(id),
    relation TEXT NOT NULL               -- causes / based_on / temporal / references
);

-- 沿 causes 深入横向分治: 一条递归 CTE
WITH RECURSIVE chain AS (
    SELECT id FROM nodes WHERE id = :root
    UNION ALL
    SELECT e.dst FROM edges e JOIN chain c ON e.src = c.id WHERE e.relation='causes'
) SELECT * FROM nodes WHERE id IN chain;

-- 沿 based_on 反溯自指链(自指递归路径)
WITH RECURSIVE selfref AS (
    SELECT id FROM nodes WHERE id = :node
    UNION ALL
    SELECT e.dst FROM edges e JOIN selfref s ON e.src = s.id WHERE e.relation='based_on'
) SELECT * FROM nodes WHERE id IN selfref;
```

## Forest API

```python
class Forest(ABC):                          # CognitiveBackend, core 契约(不可变)
    def add_node(self, ...) -> int: ...     # 返回 node id
    def add_edge(self, src, relation, dst): ...
    def mark(self, node_id, status): ...    # active/failed/success(round 8 回溯)
    def subtree(self, root) -> list: ...    # causes 子树
    def walk(self, node, relation, depth) -> list: ...   # 沿指定边走(递归 CTE)
    def prune(self, root) -> int: ...       # 剪枝:老子树压成摘要节点(round 7 第三触发器)

class NullForest(Forest): ...               # R0 退化:全 no-op
class SQLiteForest(Forest): ...             # R1 实现
```

## 确定 vs open

- ✅ SQLite(递归 CTE / 增量 INSERT / 零依赖 / 事务 / 可插拔)
- ✅ schema 含 category(两类节点)+ status(回溯)
- ✅ Forest = CognitiveBackend(NullForest / SQLiteForest 可换)
- 🟡 剪枝阈值具体值(N 节点?任务边界?)
- 🟡 剪枝后摘要节点的内容格式
