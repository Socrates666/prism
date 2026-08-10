# Agent System Prompt 方法论与实践指南

> 综合整理自 Anthropic (Building Effective Agents)、OpenAI (Practical Guide to Agents)、
> Lilian Weng (LLM Powered Autonomous Agents)、DSPy (Stanford NLP)、
> PromptingGuide.ai 及业界实战经验。2024-2025。

---

## 一、核心原则

### 1. 角色定义要精确，不要泛
- **❌ 坏例子**: "你是一个有用的AI助手"
- **✅ 好例子**: "你是 Prism，跑在 textual TUI 全屏界面里的主 agent。你通过 Python 工具在共享命名空间执行代码，能搜索网络，能 spawn 子 agent。"
- 明确：身份、运行环境、核心能力、工具集

### 2. 指令用祈使句，简洁直接
- 不要解释"为什么"，只说"做什么"和"怎么做"
- 短句优于长句，列表优于段落
- 用 **粗体** 强调关键约束

### 3. 工具描述要精确
- 每个工具：用途、输入格式、输出格式、边界条件
- 用具体例子说明何时用、何时不用
- 避免歧义："如果不确定就搜索" > "考虑是否需要搜索"

### 4. 结构化输出
- 明确要求输出格式（JSON、Markdown、代码块等）
- 多步任务要求先输出计划再执行
- 使用 `<thinking>` / `<answer>` 等标签引导推理

---

## 二、Agent Prompt 架构模式

### Pattern 1: ReAct (Reason + Act)
```
Thought: 我需要先搜索相关信息
Action: web_search("query")
Observation: [搜索结果]
Thought: 基于结果，我可以...
Action: python("...")
Observation: [执行结果]
Thought: 任务完成
Final Answer: ...
```

### Pattern 2: Plan-Execute-Reflect
```
1. Plan: 分解任务为子步骤
2. Execute: 逐步执行，每步用工具
3. Reflect: 检查结果是否正确，是否需要修正
4. Repeat until done
```

### Pattern 3: Tool-First
```
优先使用工具获取信息/执行操作，而不是凭记忆回答。
不确定就搜索，需要计算就写代码。
```

### Pattern 4: Scratchpad / 工作记忆
```
用命名空间变量保存中间状态：
- task_state: 当前任务进度
- intermediate_results: 中间结果
- context_cache: 已获取的信息
```

---

## 三、Anthropic 的关键建议

### Building Effective Agents (2024)
1. **从简单开始**: 先用 prompt + tool use，不要一开始就上复杂框架
2. **Workflow vs Agent**:
   - Workflow = 预定义的 LLM 调用路径（确定性）
   - Agent = LLM 自主决定路径（非确定性）
   - 简单任务用 Workflow，开放任务才用 Agent
3. **常见 Workflow 模式**:
   - **Prompt Chaining**: 串行调用，每步处理一个子任务
   - **Routing**: 分类后分发到不同专用 prompt
   - **Parallelization**: 多个 LLM 调用并行（投票/分段）
   - **Orchestrator-Workers**: 主 agent 分配任务给子 agent
   - **Evaluator-Optimizer**: 生成→评估→改进循环

### Claude System Prompt 最佳实践
1. **"Be direct, clear, and honest"** — 不要谄媚
2. **明确边界**: 说清楚能做什么、不能做什么
3. **安全约束前置**: 危险操作前要确认
4. **XML 标签分隔**: 用 `<instructions>`, `<context>`, `<example>` 结构化

---

## 四、OpenAI 的关键建议

### A Practical Guide to Building Agents (2024)
1. **找到合适的使用场景**: 规则确定、路径多变、需要工具调用的任务
2. **三个核心组件**:
   - Model: 选择有足够推理能力的模型
   - Tools: 明确定义函数签名和描述
   - Instructions: 详细的 system prompt
3. **编排模式**:
   - Single Agent: 一个 agent + 多工具
   - Multi-Agent: manager + workers，按领域分拆
4. **Guardrails**: 输入/输出验证，操作确认，速率限制

---

## 五、DSPy / 程序化 Prompt 优化

### 核心思想
- **不要手写 prompt，要编程生成 prompt**
- 把 prompt 当代码：定义 Signature → 选择 Module → 用 Optimizer 自动优化
- 用评估指标驱动 prompt 迭代，而非人工调试

### 适用场景
- 大规模、可重复的 prompt 工程
- 需要系统比较不同 prompt 变体
- 团队协作中的 prompt 版本管理

---

## 六、Claude Code / Cursor 等 Agent 的 Prompt 设计启示

从已泄露/公开的 agent system prompt 中学到的:

### Claude Code 风格
- **极简、命令式**: "Do X. Don't do Y."
- **明确工具优先级**: 先搜索 → 再推理 → 最后回答
- **错误处理指令**: "如果工具调用失败，分析错误原因，尝试修复"
- **上下文管理**: "及时清理，只保留相关信息"

### Cursor 风格
- **角色 + 规则**: 清晰的角色定义 + 编号规则列表
- **输出格式约束**: 代码用特定格式，解释要简洁
- **多步推理引导**: "先理解需求，再搜索相关代码，最后给出修改"

---

## 七、自反思与自我纠错

### 关键策略
1. **Self-Critique**: 生成后自检"这个答案是否准确？是否有遗漏？"
2. **Error Recovery**: 工具失败时不放弃，分析错误并尝试替代方案
3. **Confidence Calibration**: 不确定时明确说明，而非编造
4. **Progressive Refinement**: 复杂任务分步推进，每步验证

---

## 八、通用 Prompt 检查清单

- [ ] 角色和身份是否精确？
- [ ] 工具描述是否包含输入/输出/边界？
- [ ] 是否有明确的输出格式要求？
- [ ] 是否处理了错误和边界情况？
- [ ] 指令是否简洁、无歧义？
- [ ] 是否有明确的优先级/工作流程？
- [ ] 安全约束是否清晰？
- [ ] 是否过度冗长？（每条指令都应该是必要的）
