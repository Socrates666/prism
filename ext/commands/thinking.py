"""指令: 设置思考深度(对齐 pi thinkingLevel)。

/thinking off     关思考(enable_thinking=False, 快且简洁)
/thinking on      开思考(默认, reasoning 可见)
"""
NAME = "thinking"
DESC = "思考深度: /thinking <off|on>  (off=关快, on=开默认)"


def run(args, ctx):
    a = args.strip().lower()
    agent = ctx["agent"]
    if a == "off":
        agent.set_thinking_level("off")
        return "✓ 思考: off (关, 快)"
    agent.set_thinking_level("on")
    return "✓ 思考: on (开, 默认, reasoning 可见)"
