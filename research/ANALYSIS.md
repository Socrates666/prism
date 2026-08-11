# 思维树搜索 / 增加节点 —— 算法复杂度研究与优化

> 分支: `research/forest-search-complexity` (隔离 worktree)
> 对象: `prism/forest.py` (SQLiteForest) + `prism/cog_intuition.py` (直觉搜索热路径)
> 方法: `research/complexity_bench.py` 实证 (μs, 中位数)

---

## 1. 系统模型

认知树 = **一树两轴** 的图结构 (`plan/rlm/tree.md`):

- **causes 轴** (搜索/回溯): `thinking→thinking`, 树形(单父)。`add_node(parent=)` 自动建 causes 边。撞瓶颈 → `mark(FAILED)` → 沿父边回溯。
- **based_on 轴** (自指/套娃): `thinking→thinking` 任意(图)。`add_edge(src, BASED_ON, dst)`。反思连回被反思节点, 可套娃。
- 任务隔离: 同 session 多棵树 (`tree_id`); `parent=None` 开新树。

**两类核心操作** (本研究对象):
1. **增加节点** — `add_node` (+ 内部 `add_edge` 建 causes 边)
2. **搜索** — `subtree(root)` (causes 子树) / `walk(node, relation)` (沿边走) / `trees()` / `nodes_in_tree()` / 直觉组合 `select_context()`

存储: SQLite。`nodes` 表 (id 主键 / session_id / tree_id / parent_id / category / type / status / content / created_at) + `edges` 表 (src, relation, dst) + `meta` 表 (单调计数器)。递归 CTE 做树遍历。

---

## 2. 复杂度分析 (理论)

设 N = session 总节点数, K = 单棵树节点数, K' = 一次搜索的**可达**节点数, T = 树数, L = limit。

| 操作 | 原实现 | 优化后 | 备注 |
|------|--------|--------|------|
| `add_node` | O(log N) **但 fsync ~12ms** | O(log N), 常数 ~μs | WAL 消除 per-commit fsync |
| `add_edge` / `mark` | O(log N) | O(log N) | 同上, 常数降 |
| `trees()` | O(N) 全表 DISTINCT | O(T) (索引有序前缀) | 非热路径, 进一步可 meta 集合 |
| `nodes_in_tree` | O(K) + filesort | O(K) 走 `created_at` 索引 | K 是信息下界, 无 filesort |
| `subtree(root)` | O(K') 递归 CTE | O(K') 不变 | **信息论下界**: 必访问每个可达节点 |
| `walk(node, rel)` | O(K') 递归 CTE | O(K') 不变 | 同上; 短链时 K'≪K 已很快 |
| `last_tree_id` (新) | — | **O(1)** | id 倒序 LIMIT 1 |
| `recent_in_tree` (新) | (原靠 nodes_in_tree+过滤 O(K)) | **O(L)** | 覆盖索引 top-N 倒序 |
| **直觉热路径 `select_context`** | **O(N)** | **~O(L)** (常数级) | last_tree_id + 3× recent_in_tree(limit) |

> **关键洞察**: 递归 CTE 本身已是最优 (O(可达数), benchmark 中 `walk_based_on` 短链仅 16-185μs 证实)。问题不在 CTE, 而在 **(a) 写路径 fsync 常数** 和 **(b) 直觉热路径用 O(N) 的 trees()+nodes_in_tree() 组合**。

---

## 3. 实证数据 (benchmark, μs 中位数)

### Before (原始实现)

| N | add_node | add_edge | trees | nodes_in_tree | subtree | walk_causes | walk_based_on | **直觉热路径** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 12207 | 57 | 26 | 369 | 440 | 445 | 29 | **404** |
| 1000 | 15705 | 66 | 72 | 2792 | 4114 | 3912 | 48 | **3096** |
| 6000 | 15924 | 27 | 313 | 18163 | 22208 | 22888 | 138 | **20948** |

### After (优化实现)

| N | add_node | add_edge | trees | nodes_in_tree | subtree | walk_causes | walk_based_on | **直觉热路径** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 57 | 6 | 11 | 331 | 499 | 513 | 17 | **122** |
| 1000 | 58 | 6 | 54 | 2438 | 3682 | 3554 | 41 | **439** |
| 6000 | 58 | 6 | 299 | 16102 | 22479 | 22382 | 185 | **1956** |

### 加速比 (N=6000)

| 操作 | before | after | **加速** |
|------|-------:|------:|--------:|
| `add_node` (增加节点) | 15924μs | 58μs | **274×** |
| `add_edge` | 27μs | 6μs | 4.5× |
| 直觉热路径 (每轮认知循环) | 20948μs | 1956μs | **10.7×** |

> 一轮认知循环 (3 个认知事件 thought/action/result) 的写开销: 原 ~36ms 纯 fsync → 现 ~170μs。直觉 search-state 拼装: 原 21ms (随树膨胀) → 现 2ms (近常数)。

---

## 4. 优化点详解

### O1. 写路径: WAL + synchronous=NORMAL (add_node 274×)

**病灶**: 原默认 `journal_mode=DELETE` + `synchronous=FULL`, 每次 `commit()` 触发 fsync 刷盘 (~12ms)。`add_node` 每次 commit, 认知循环每轮 3 次 commit = 36ms 纯 I/O 等待。

**修复**:
```python
self._conn.execute("PRAGMA journal_mode=WAL")      # 写不阻塞读
self._conn.execute("PRAGMA synchronous=NORMAL")    # 不每 commit fsync (崩溃仅丢最近事务)
self._conn.execute("PRAGMA temp_store=MEMORY")
```
WAL 模式下 commit 只写 WAL 文件 (顺序写, 不强制 fsync), 常规 commit 降到 μs 级。`synchronous=NORMAL` 在 WAL 下仍保证事务持久性 (仅 OS 崩溃可能丢最后几个未 checkpoint 的事务, 进程崩溃安全)。认知树是 best-effort 状态, 此 trade-off 可接受。

> 语义不变: `test_persistence_reopen` 仍验证重启后数据存活。持久化保证符合需求。

### O2. meta 表: tree_id 分配 O(1) 恢复

**病灶**: `__init__` 里 `SELECT MAX(tree_id) FROM nodes` 全表扫 O(N), 且 `_tree_seq` 仅内存态 (重开可能错)。

**修复**: `meta(key, value)` 表存 `next_tree_id`。`_alloc_tree_id()` 分配 + `ON CONFLICT ... DO UPDATE` 同事务持久化。init/reopen 均 O(1)。

### O3. 覆盖索引 + `recent_in_tree`: 直觉 O(N)→O(L)

**病灶**: 原直觉 `trees()` (O(N) DISTINCT) + `nodes_in_tree()` (O(K) 全树扫) + 3× list comprehension (O(K))。每轮认知循环都跑, N=6000 时 21ms。

**修复**:
1. **覆盖索引** `(session_id, tree_id, type, status, id)` —— 让按 type/status 过滤走索引而非全扫, id 末列支持倒序 top-N。
2. **`last_tree_id()`** O(1) (id 倒序 LIMIT 1) 替代 `trees()` 全扫取最新树。
3. **`recent_in_tree(tid, type=, status=, limit=)`** —— 走覆盖索引 `ORDER BY id DESC LIMIT L`, 复杂度 O(L) 而非 O(K)。
4. **failed/reflection 加 limit** —— search-state 不该随树规模无限膨胀。`max_failed=20` 让直觉真常数级。

新增的两个方法进了 `Forest` ABC (带默认实现 = 走 `trees()`/`nodes_in_tree`), `NullForest` 自动降级 (返回 None/[]), 旧子类零改动兼容。

### O4. 顺手修复的 bug

**`add_node` 的 tree_id 分配**: 原 `parent` 查不到时 fallback 到 `self._tree_seq` **但不递增**, 导致多个孤儿节点共享同一 tree_id (破坏任务隔离语义)。修复: parent 查不到 → `_alloc_tree_id()` 分配新树。

### O5. nodes_in_tree 的 ORDER BY 索引

加 `(session_id, tree_id, created_at)` 索引, 让 `ORDER BY created_at` 走索引 (避免树内 filesort)。subtree/walk 的 ORDER BY created_at 仍需对可达集排序 (K' log K'), 这是结果集本身的固有成本。

---

## 5. 不优化 (YAGNI) 的项

| 项 | 理由 |
|----|------|
| `subtree`/`walk` 整树 O(K') | **信息论下界**: 必须访问每个可达节点返回它们。benchmark 中 `walk_based_on` 短链仅 17-185μs 证明 CTE 本身已最优。 |
| `trees()` DISTINCT O(T) | 已退出直觉热路径 (用 `last_tree_id` O(1))。仅显式调用时触发, 用 meta 存 tree_id 集合维护成本高 (剪枝要同步删), 不值得。 |
| walk/subtree 结果缓存 | 树在持续增长 (认知循环每轮加节点), 缓存失效频繁; `walk_based_on` 已 O(K') 很快。 |
| 批量 commit API | WAL 已把单 commit 降到 μs 级, 批量 API 增加调用方复杂度, 当前无瓶颈。 |

---

## 6. 验证

- **认知层测试 33/33 全绿**: `test_forest` (16, 含 6 个 prune) + `test_cog_cycle` + `test_cog_hooks` + `test_cog_tools` + `test_cog_transparency`。ABC 兼容、NullForest 降级、持久化、两轴隔离、回溯、**剪枝**全验证。
- 全套 217 测试中 18 个失败均为 `openai.OpenAIError` (worktree 缺 `.env` API key), 与算法改动无关。
- benchmark 可复现: `python research/complexity_bench.py`。

---

## 7. 结论

思维树「增加节点」与「搜索」的复杂度瓶颈已实证消除:

- **增加节点** (`add_node`): 12ms → 58μs (**274×**), 根因是 per-commit fsync, WAL 一招治愈。
- **搜索** 热路径 (直觉 `select_context`): 21ms (O(N)) → 2ms (~O(L)) (**10.7×**), 根因是 `trees()`+`nodes_in_tree()` 全扫, 改覆盖索引 + top-N + last_tree_id 治愈。
- **递归 CTE 搜索本身** (`subtree`/`walk`) 本就 O(可达数) 最优, 无需改动。

写入常数级、读取热路径近常数级, 认知循环不再被数据库拖累。

---

## 8. 补充: prune 实现 (剪枝, 补全 ABC 声明)

初版研究聚焦"搜索/增加节点", 漏了 ABC 声明但 SQLiteForest 未实现的 `prune` (原继承 ABC 的 `return -1`, 从不工作)。本节补全。

### 语义 (cycle.md 第三触发器)

结构阈值触发 (树超规模 / 任务边界), 把 root 的 causes 子树压成一个摘要节点存回, 控膨胀。

```
剪枝前:                              剪枝后:
  P (root 的父)                       P
  │ causes                            │ causes
  ├─ ROOT ─┐                         └─ [SUMMARY] summary(调用方传入) type="summary"
  │   ├─ c1                              占 ROOT 的 causes 位置
  │   ├─ c2 (failed)
  │   └─ c3                           子树内部节点+边: 物理删除
                                      单事务原子(all-or-nothing)
外部 X ──based_on──▶ c2              外部 X ──based_on──▶ SUMMARY (重连, 保外部认知关联)
```

### 决策

1. 摘要文本由调用方传入 (`summary: str`) —— forest 不依赖 LLM (机制/策略分离)。
2. 物理删除旧节点 (真剪枝释放空间)。
3. SUMMARY 占 ROOT 的 causes 位置 (`parent=root.parent`) —— 保搜索树连续。
4. 外部入边 (src 在子树外, dst 在子树内) 重连到 SUMMARY —— 保外部认知关联 (based_on/references) 不丢。
5. 子树内部边连同节点删除。
6. 单事务原子 (失败 rollback, 不留半截树)。
7. 临时表存子树 id —— 绕开 SQLite IN 列表上限 + hash join 找外部入边高效。

### 复杂度 O(K' + E_affected) (信息论下界)

| K (子树节点数) | prune 耗时 (μs, median of 5) |
|---:|---:|
| 100 | 737 |
| 1000 | 4339 |
| 3000 | 12721 |
| 6000 | 24036 |

线性于子树规模 (K 涨 60×, 耗时涨 33×): 必须访问+删除每个子树节点, 无法更优。属结构阈值触发的偶发 WRITE, 24ms (K=6000) 可接受。

### 验证

`test_forest.py` 加 6 个 prune 测试全绿: 子树压扁、causes 位置继承、外部 based_on 重连、空 summary 守门、root 不存在、NullForest 降级。认知层 33/33。
