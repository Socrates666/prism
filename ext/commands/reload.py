"""指令: 重新加载 ext/ 插件(prompts/tools/skills) 并应用到当前 agent。

/reload          全部重载
/reload prompts  只重载 prompts
"""
NAME = "reload"
DESC = "重载 ext/ 插件: /reload [prompts|tools|skills|all]"


def run(args, ctx):
    import importlib
    from prism.registry import default_registry, load_ext
    from prism.commands import load_commands
    agent = ctx["agent"]
    app = ctx["app"]
    emit = agent.hooks.get("emit", lambda e: None)
    kind = args.strip().lower() if args.strip() else "all"

    import os
    ext_dir = "ext"
    results = []

    # 1. 重载 ext/ 插件(prompts/tools/skills 进 registry)
    if kind in ("all", "prompts", "tools", "skills"):
        # 清除 sys.modules 中旧的 ext 模块(强制重新 import)
        import sys
        to_remove = [k for k in sys.modules if k.startswith("prism_ext_")]
        for k in to_remove:
            del sys.modules[k]

        # 清除 registry 中对应的注册(只清要重载的部分)
        if kind in ("all", "prompts"):
            default_registry._prompts.clear()
        if kind in ("all", "tools"):
            default_registry._tools.clear()

        loaded = load_ext(ext_dir, default_registry, emit=emit)
        results.append(f"ext 插件: {', '.join(loaded) if loaded else '(无)'}")

    # 2. 重新加载 slash 指令
    if kind in ("all",):
        import sys as _sys
        to_remove = [k for k in _sys.modules if k.startswith("prism_cmd_")]
        for k in to_remove:
            del _sys.modules[k]
        app.commands = load_commands(ext_dir, emit=emit)
        results.append(f"指令: {', '.join('/'+c for c in sorted(app.commands))}")

    # 3. 重新 apply prompt 到当前 agent
    sections = default_registry.get_prompt("prism")
    if sections:
        agent.apply_prompt(sections, agent.name, agent.kind)
        results.append(f"prompt 已重新应用到 {agent.name}")
    else:
        results.append("⚠ 未找到 prism prompt 段")

    # 4. 清理: 移除 agent 已结束的子 agent workspace 变量(可选)
    agent.namespace.pop("b", None)  # 防止引用旧的

    return "✓ 重载完成\n  " + "\n  ".join(results)
