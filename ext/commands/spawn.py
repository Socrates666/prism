"""指令: spawn 子 agent(emit 汇入主 transcript, 阶段12)。

/spawn <name>   spawn 一个子 agent, emit 自动汇入主 transcript(带 [name] 前缀),
                注册进 main agent 命名空间。之后用 @<name> 对话。
"""
NAME = "spawn"
DESC = "spawn 子 agent(emit 汇入主 transcript): /spawn <name>"


def run(args, ctx):
    name = args.strip()
    if not name:
        return "用法: /spawn <name>"
    from prism.spawn import spawn
    from prism.model import OpenAIModel
    app = ctx["app"]
    try:
        emit = app.make_subagent_emit(name)
        from prism.registry import default_registry
        bob = spawn(name, OpenAIModel(), emit=emit, parent=ctx["agent"])
        sections = default_registry.get_prompt("prism")
        if sections:
            bob.apply_prompt(sections, name, "sub")
        return (f"✓ 子 agent {name} 已 spawn\n"
                f"  workspace = workspaces/{name}/\n"
                f"  emit 汇入主 transcript(带 [{name}] 前缀)\n"
                f"  用 [cyan]@{name} 消息[/] 对话")
    except Exception as e:
        return f"✗ spawn 失败: {type(e).__name__}: {e}"
