# 种子 · 项目命名 · werden 元数据

## 种子(用户原话)

> "使用 ipython 实现跨会话的 agent 交互可不可行"
> "我想用 primeagent 的那种 agent 调用方式,会话间的信息传递很低效,想探索一种方案"

---

## 项目命名

- **名字**:prism(棱镜分光)
- **寓意**:棱镜把一束光分成多束 —— 核心机制是一个 IPython 内核分出多个 agent / 多个长任务会话
- **被谁启发**:PrimeAgent
- **致敬**:pi(简洁)
- **项目历史**:superharness 分支 → 独立仓库 prism

---

## Werden 流程元数据

- **种子**:用户抛"ipython 跨会话 agent 交互"
- **诘问轮数**:20+ 轮(外壳设计)+ 9 轮(RLM 认知层诘问,2026-08-10)
- **设计修正链(外壳)**:daemon/mem0 可插拔 → 后端全可插拔 → 前端 IPython REPL → **textual TUI 套壳** → 显示自举 → 增量扩建 → 扩展点 patch → 可变区人格插件 → **能力分层(主完整/子工厂受限)** → **工作区分层+文件闭包** → **actor 并发** → **通讯分层(读 eventual/写 inbox)**
- **设计修正链(RLM, 9 轮 werden)**:不可变 core 冲动(为何?)→ 递归对象 = 认知树 data 非实现 → core = 单一 step + ABC → loop 一等公民 → Forest 契约同级(loop 不可变,树实例可变)→ 直觉 READ/WRITE 必须拆 → 树是搜索树(causes 轴)非被动仓库 → **搜索 ≠ 自指**(based_on 轴才是自指)→ 一树两轴

### 9 轮 werden 关键结论速查

| 轮 | 逼出的维度 |
|----|-----------|
| 1 | 【递归对象 = 认知树(data),非实现(code);core = 不可变算子】 |
| 2 | 【core = 单一 step + ABC;零递归 in core;递归 = reflect 工具(可套娃)】 |
| 3 | 【认知树 ≈ loop 同级基础设施,非 ext/ 人格层;Forest 契约进 core,树实例是 data】 |
| 4 | 【直觉 READ 每次 loop 不可绕过;搜索 session 隔离+遍历进 core,"最合理上下文"判断 = 默认笨 core + 智能 ext 升级】 |
| 5 | 【不可变 core = "直觉不被绕过"的物理实现;认知周期 直觉→思考→行动→观察】 |
| 6 | 【READ(直觉)≠ WRITE(改树);压=READ vs 压=WRITE 是 master switch】 |
| 7 | 【assembly 三件:选/排/压;压=READ 不膨胀,但大树逼出结构剪枝(第三触发器)】 |
| 8 | 【认知树 = 主动推理搜索树(思维节点+上下文节点不同边,失败回溯),非被动仓库】 |
| 9 | 【搜索(causes 轴)≠ 自指递归(based_on 轴);一树两轴;reflect 工具才是自指入口】 |

> 详见 [rlm/](rlm/) 各篇。
