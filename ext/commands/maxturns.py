"""指令: 设置/查看 agent 最大轮数(max_turns)。

/maxturns           查看
/maxturns none      无上限(信任 LLM 自停, 对齐 pi, 默认)
/maxturns <n>       设上限(如 /maxturns 50)
"""
NAME = "maxturns"
DESC = "最大轮数: /maxturns [n|none]  (默认 none=无限信任LLM)"


def run(args, ctx):
    a = args.strip().lower()
    agent = ctx["agent"]
    cur = agent.max_turns
    cur_s = f"{cur}" if cur is not None else "无上限(信任LLM自停)"
    if not a:
        return f"当前 max_turns: {cur_s}"
    if a in ("none", "0", "无限"):
        agent.max_turns = None
        return "✓ max_turns → 无上限(信任 LLM 自停, 对齐 pi)"
    try:
        n = int(a)
    except ValueError:
        return f"✗ 无效: {a}(数字 / none)"
    if n < 1:
        return f"✗ 须 >= 1 或 none"
    agent.max_turns = n
    return f"✓ max_turns → {n}"
