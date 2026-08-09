"""指令: 设定当前会话目标(注入 system prompt)。

/goal <描述>      把目标 append 到 agent system prompt, agent 围绕它工作
/goal             查看已设目标(最后一个 append 的 goal 段)
"""
NAME = "goal"
DESC = "设定目标: /goal <描述>  (注入 system prompt)"


def run(args, ctx):
    goal = args.strip()
    if not goal:
        return "用法: /goal <描述>"
    ctx["agent"].prompt.set_goal(goal)
    return f"✓ 目标已设(→ ## 当前目标 段): {goal}"
