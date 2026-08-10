# prism · plan(已结构化)

> ⚠️ 本文件已退役为薄壳指针。**完整设计文档已拆分到 [`plan/`](plan/) 目录。**

## 去 plan/ 读

| 入口 | 内容 |
|------|------|
| [plan/README.md](plan/README.md) | **索引 / 导航 / 阅读顺序** ← 从这开始 |
| [plan/principles.md](plan/principles.md) | 核心原则 1-16(+ RLM 修正方向) |
| [plan/rlm/](plan/rlm/) | **RLM 认知层**(提案 + 9 轮 werden 结论) |

## 一句话

prism = 一个 IPython 内核分出多个 agent / 长任务会话(被 PrimeAgent 启发,致敬 pi)。
向 **RLM(Recursive Language Model)认知 harness** 演进:不可变 core + 认知树 + 直觉 + 自指递归。

## 两层状态

- **外壳**(多 agent 外壳):阶段 0–13 全 ✓(190 测试)—— 见 [plan/status.md](plan/status.md)
- **认知 harness**(RLM):提案 / 未实现 —— 见 [plan/rlm/](plan/rlm/)
