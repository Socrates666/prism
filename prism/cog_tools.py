"""prism/cog_tools.py — 认知层工具(RLM Phase B)。

reflect 工具 = 自指递归入口(plan/rlm/tree.md):
  agent 调 reflect → 产 reflection 节点 + based_on 边(连回被反思的节点)。
  reflection 本身还能被再 reflect(套娃)—— 这才是自指递归(区别于搜索)。

设计:工具操作 agent.forest(data),core 不可变。NullForest 时退化为 no-op 提示。
"""
from __future__ import annotations
from .agent_loop import Tool
from .cognitive import THINKING, BASED_ON


def make_reflect_tool(agent) -> Tool:
    """造 reflect 工具(闭包绑 agent.forest)。"""
    def execute(args):
        content = (args.get("content") or "").strip()
        based_on = args.get("based_on") or []
        if not content:
            return ("reflect 需要内容:你在反思什么?", True)
        # reflection 节点(parent=None:反思是新观察, 搜索位置由调用上下文定)
        nid = agent.forest.add_node(category=THINKING, type="reflection", content=content)
        if nid == -1:
            return ("[forest 未配置(NullForest), 反思未记录]", True)
        linked = []
        for target in based_on:
            try:
                tid = int(target)
            except (TypeError, ValueError):
                continue
            if agent.forest.get(tid) is not None:
                agent.forest.add_edge(nid, BASED_ON, tid)
                linked.append(tid)
        suffix = f", based_on={linked}" if linked else ", based_on=[]"
        # 白盒化: 发"反思"认知事件让 TUI 显示
        try:
            agent.emit({"type": "cognitive", "stage": "reflect",
                        "content": content, "based_on": linked})
        except Exception:
            pass
        return f"[反思已记] node={nid}{suffix}。这能被再次 reflect(套娃)= 自指递归。"

    return Tool(
        name="reflect",
        description=(
            "反思自己的推理/决策/认知模式, 记入认知树(沿 based_on 连回被反思的节点)。"
            "用于:撞瓶颈后重组思路、抽象可迁移的模式、或审视自己推理方式本身。"
            "reflection 节点可被再次 reflect(套娃)—— 这是自指递归。"
            "参数:content=反思内容;based_on=被反思的节点 id 列表(可选)。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "反思内容(你意识到了什么)"},
                "based_on": {
                    "type": "array", "items": {"type": "integer"},
                    "description": "被反思的节点 id 列表(可选;反思基于哪些已有认知)",
                },
            },
            "required": ["content"],
        },
        execute=execute,
    )
