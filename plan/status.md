# 现状总览 + 开放问题

## 现状总览(审计, 需周期校准)

> ⚠️ 测试数需周期校准:2026-08-10 审计记 161 passed,实际已增至 **190 passed**(pytest 实跑确认)。本表数字以最新实跑为准。

- **代码**: prism/ 模块(agent/agent_loop/model/router/shell/patch/registry/spawn/memory/prompt/guard/commands/agent_registry + `__init__`); ext/ 已建(commands/skills/tools/prompts)
- **测试**: **190 passed**(pytest 实跑,2026-08 校准)
- **已完成**: 阶段 0–13 全 ✓(骨架/TUI/actor/patch/registry/spawn/comms/guard/测试/对齐pi/结构化prompt/持久化/跨会话/运行时接通)
- **未完成**: 阶段 14(可变 base + 回退,`guard.py` 有 verify_and_revert 脚手架但 PLAN 未勾);daemon(后台进程,开放问题)
- **提案**: RLM 认知层(见 [rlm/](rlm/)),未实现 —— 含对原则 10/8 的修正方向

## 实施状态速查

| 阶段 | 状态 | 详见 |
|------|:----:|------|
| 0 骨架 + function-calling | ✓ | [roadmap.md](roadmap.md) |
| 1 对齐 pi(D1–D5) | ✓ | |
| 2 textual TUI | ✓ | |
| 3 actor 异步 | ✓ | |
| 4 扩展点 patch | ✓ | |
| 5 注册表 + ext/ | ✓ | |
| 6 多 agent 工厂 | ✓ | |
| 7 多 agent 通讯 | ✓ | |
| 8 增量扩建 + 护栏 | ✓ | |
| 9 白盒 + 黑盒测试 | ✓ | |
| 10 持久化 + 后端可插拔 | ✓ | |
| 11 跨会话验证 | ✓ | |
| 12 运行时接通 | ✓ | |
| 13 结构化 system prompt | ✓ | |
| 14 可变 base + 回退 | ☐ 脚手架在 | **将被 RLM 方向(硬不可变 core)取代** |
| RLM 认知层 | 🟡 提案 | [rlm/](rlm/) |

---

## 开放问题 / 风险

### 外壳层(已基本闭合)
1-8. (前期:mem0共享/文档格式/异步GIL/护栏边界/恢复开销/NullMemory/@边界/流式阻塞)
9. ✓ around patch 异常降级(已实现: 跳过+emit patch_error)
10. ✓ 增量 vs 覆盖边界(guard.py: prism/ 写前备份+放行, ext/ 可改)
11. ✓ patch 注册表并发(各 agent 独立 PatchRegistry 实例, 无共享, 无锁需求)
12. ✓ textual asyncio + agent 线程桥接(call_from_thread, 阶段 2 spike 通过 + 全套测试验证)
13. **子 agent python 工具裸 open**(若未来赋予): 落 cwd=根踩踏。当前子 agent 无 python 工具, 无此问题
14. **inbox 通讯 vs 共享变量**: 通讯主走 inject(安全), 共享变量辅助(eventual + 加锁)
15. **子 agent workspace 清理**: 结束后保留还是清理? 待定
16. **theme namespace gap**(→ 阶段12): namespace 没 app 句柄, agent 改不了主题
17. **子 agent emit 可见性**(→ 阶段12): spawn 的子 agent emit 没桥接 transcript, 输出不可见
18. **持久化并发**(→ 阶段10): 多 agent 同时 dump MemoryBackend 的锁/一致性

### RLM 认知层开放问题(见 [rlm/](rlm/))
- 谁控制搜索?(主模型 α / 小模型 β)—— [rlm/scribe.md](rlm/scribe.md)
- 小模型选型与延迟(必须实测)—— [rlm/scribe.md](rlm/scribe.md)
- 自指递归终止条件 —— [rlm/tree.md](rlm/tree.md)
- 任务边界判定 + 兜底 —— [rlm/scribe.md](rlm/scribe.md)
- 范式定位(外壳 vs 认知 harness)—— [rlm/README.md](rlm/README.md)
