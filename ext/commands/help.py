"""指令: 列出所有可用 / 指令。"""
NAME = "help"
DESC = "列出指令"


def run(args, ctx):
    cmds = ctx.get("commands", {})
    if not cmds:
        return "(无可用指令)"
    lines = ["指令:"]
    for n in sorted(cmds):
        desc = getattr(cmds[n], "DESC", "")
        lines.append(f"  /{n:<10} {desc}")
    return "\n".join(lines)
