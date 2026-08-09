"""指令: 切换/查看模型。

/model            查看当前模型
/model <name>     切换模型(重建 OpenAIModel)
"""
NAME = "model"
DESC = "切换/查看模型: /model [name]"


def run(args, ctx):
    agent = ctx["agent"]
    if not args.strip():
        cur = getattr(agent.model, "model", agent.model)
        return f"当前模型: {cur}"
    name = args.strip()
    from prism.model import OpenAIModel
    agent.model = OpenAIModel(name)
    return f"✓ 模型切换 → {name}"
