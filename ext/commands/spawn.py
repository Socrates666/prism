"""指令: spawn 子 agent(emit 汇入主 transcript)。

/spawn <name>           spawn 基础子 agent (file_tools)
/spawn <name> coder     spawn coder 子 agent (file_tools + project_tools)
"""
NAME = "spawn"
DESC = "spawn 子 agent: /spawn <name> [coder]"


def run(args, ctx):
    name = args.strip()
    if not name:
        return "用法: /spawn <name> [coder]"
    parts = name.split(None, 1)
    name = parts[0]
    role = parts[1] if len(parts) > 1 else ""
    
    from prism.spawn import spawn
    from prism.model import OpenAIModel
    from prism.agent_registry import save_agent_config
    app = ctx["app"]
    
    try:
        emit = app.make_subagent_emit(name)
        from prism.registry import default_registry
        
        project_tools = (role == "coder")
        bob = spawn(name, OpenAIModel(), emit=emit, parent=ctx["agent"],
                    file_tools=True, project_tools=project_tools)
        
        sections = default_registry.get_prompt("prism")
        if sections:
            bob.apply_prompt(sections, name, "sub")
        
        # 持久化配置
        cfg = {"name": name, "kind": "sub", "file_tools": True,
               "project_tools": project_tools}
        save_agent_config(name, cfg)
        
        return (f"✓ 子 agent {name} 已 spawn\n"
                f"  workspace = workspaces/{name}/\n"
                f"  project_tools = {project_tools}\n"
                f"  配置已保存到 ext/agents/{name}.yaml\n"
                f"  用 @{name} 消息 对话")
    except Exception as e:
        return f"✗ spawn 失败: {type(e).__name__}: {e}"
