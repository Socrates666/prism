# 思维树运行时审计：设计生效度

> 对象: 主工作区 `.prism/forest.db` (supergoal/rlm-core-tree 分支真实运行数据)
> 数据: **555 节点 / 537 边 / 1 session(Prism) / 17 棵树**
> 工具: `research/analyze_real_forest.py`

## 一句话

**挂树 + 直觉注入生效了；但设计核心——失败回溯(搜索) + 自指套娃(RLM 灵魂)——在 555 节点的真实运行里从未触发。当前是「线性认知事件日志」, 不是「带回溯的搜索树」。**

## 实证对比（设计意图 vs 实际数据）

| 设计意图 (tree.md / cycle.md) | 实际数据 | 生效? |
|---|---|:---:|
| causes 轴严格成树(单父) | 0 个多父节点, 18 个树根 | ✅ |
| 任务隔离(多棵树) | 17 棵树 | ✅ |
| AutoAttachHook 自动挂认知事件 | 555 事件全挂上 | ✅ |
| 直觉注入 search-state | HeuristicIntuition 能读树(机制在) | ✅ |
| **失败回溯** (mark FAILED → 回父另开支) | **status 全 active (555/555), 0 failed, 0 success** | ❌ |
| **搜索分叉** (撞瓶颈另开一支) | **535/536 父只有 1 个子 → 纯线性流水线** | ❌ |
| **based_on 自指轴** (套娃) | **0 条 based_on 边** | ❌ |
| **reflect 自指递归** (RLM 核心) | **2 个孤立 reflection, 0 条 based_on; reflect 工具定义了但从未装配进 agent** | ❌ |

## 真实树形态（最大树 tree_id=7, 122 节点前 18 个）

```
#218 [action ] python(...)      ┐
#219 [result ] [ok] Phase 1...  ┘ 线性
#220 [action ] python(...)      ┐
#221 [result ] [ok] Phase 1 PASSED ┘ 线性
#222 [thought] 阶段1通过, 进入阶段2
#223 [action ] python(...)      ┐
#224 [result ] [ok] Phase 2...  ┘ 线性
... (一路 action→result→thought 循环, 无分叉, 无 failed, 无回溯)
```

这是**流水线**, 不是搜索树。撞瓶颈没标 failed, 没回父另开支, 也没 reflect 自指。

## 三个根因（代码级确证）

### 根因 1: 没有任何业务代码调 `forest.mark()` —— 回溯永不发生

```
grep -rn "forest.mark\|FAILED" prism/ ext/  →  只有:
  cognitive.py: 常量定义 + docstring
  cog_patches.py: prompt 文本提示("你可以用 .mark(id,'failed')")
  (没有任何执行 mark 的代码路径)
```

设计 tree.md 把"谁标 failed"列为 **open(α 主模型 / β 小模型)**, 实现里**两边都没做**。
→ 555 节点全 active, causes 树退化为线性流水线。

### 根因 2: `make_reflect_tool` 定义了但**从未被调用** —— reflect 工具没装配

```
grep -rn "make_reflect_tool(" → 只有定义, 0 个调用点
```

自指递归入口**实际不存在**。那 2 个 reflection 节点(#151 parent=None / #499 parent=467)是历史遗留, 且都 **0 条 based_on 边**(孤立反思, 没连回被反思节点 —— 违背 reflect 工具的设计语义)。

### 根因 3: AutoAttachHook 只有线性挂载语义

`cog_hooks.py` 注释自承: *"MVP 语义: 线性 causes 链(每节点 parent=上一节点)"*。
它只追加, **不标 failed, 不建 based_on**。即使前两个根因修了, 这个 hook 也不会主动产生搜索/自指结构 —— 它只是"把事件记下来"。

## 一个关键反讽：性能优化对当前数据是「空跑」

我之前优化的直觉热路径 `recent_in_tree(status="failed")`, 在当前运行数据下 **永远返回空集** —— 因为根本没有任何 failed 节点。同理 reflection 查询也近乎空(只有 2 个, 且没连 based_on)。

**性能优化 ≠ 设计生效**。优化让"将来有 failed/reflection 时"查得快, 但现在没有数据可查。真正的问题是**机制未被触发**, 不是查得慢不慢。两者正交, 都得做。

## 当前思维树的真实角色

| 角色 | 状态 |
|---|---|
| ✅ 可观测的认知事件流水线 (白盒化 + 直觉注入) | 工作 |
| ❌ 带回溯的主动推理搜索树 | 没工作 (无 failed, 无分叉) |
| ❌ 自指递归认知树 (RLM 灵魂) | 没工作 (无 based_on, reflect 未装配) |

## 要让设计生效（最小修复, 按优先级 / ROI）

1. **装配 reflect 工具** — agent 默认 tools 加 `make_reflect_tool(agent)`。一行改动, 让自指入口可用。
2. **引导主模型用 reflect + based_on** — prompt 里明确"撞墙/完成大任务后, 调 reflect(content=…, based_on=[相关节点 id])"。没有引导, 主模型不会主动用。
3. **回溯触发器(最小方案)** — 工具报错时自动 `mark(该 action, FAILED)` + 引导另开支。这是 tree.md open(α) 的最小落地: 不需要小模型, 工具 is_error 就够。
4. **(可选) AutoAttachHook 升级** — 工具失败时不再无脑线性追加, 而是挂到更合理的父 / 标 failed。

> 1+2 让自指轴活过来; 3 让搜索回溯轴活过来。三者加起来 < 50 行, 但能把"线性日志"变成 tree.md 设计的"搜索 + 自指树"。
