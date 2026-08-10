"""指令: 设置/查看 agent 最大轮数(max_turns)。

/maxturns           查看当前
/maxturns <n>       设置(如 /maxturns 50)
"""
NAME = "maxturns"
DESC = "最大轮数: /maxturns [n]  (默认 1000, PRISM_MAX_TURNS 可配)"


def run(args, ctx):
    a = args.strip()
    agent = ctx["agent"]
    if not a:
        return f"当前 max_turns: {agent.max_turns}"
    try:
        n = int(a)
    except ValueError:
        return f"✗ 无效数字: {a}"
    if n < 1:
        return f"✗ 须 >= 1"
    agent.max_turns = n
    return f"✓ max_turns → {n}"
