"""指令: spawn 子 agent。

/spawn <name>              spawn 基础子 agent
/spawn <name> coder        spawn coder (项目文件工具 + 锁)
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
        
        if role == "coder":
            tool_names = ["read", "write", "ls", "read_file", "edit_file", "write_file", "list_dir"]
        else:
            tool_names = ["read", "write", "ls"]
        
        bob = spawn(name, OpenAIModel(), emit=emit, parent=ctx["agent"],
                    tool_names=tool_names)
        
        sections = None
        from prism.registry import default_registry
        from prism.agent_registry import _apply_prompt_from_config
        bob.apply_prompt({}, bob.name, "sub")  # 基础 sub prompt
        
        # 持久化
        cfg = {"name": name, "kind": "sub", "tools": tool_names}
        save_agent_config(name, cfg)
        
        return (f"✓ 子 agent {name} 已 spawn\n"
                f"  tools = {tool_names}\n"
                f"  配置已保存到 ext/agents/{name}/agent.yaml\n"
                f"  用 @{name} 消息 对话")
    except Exception as e:
        return f"✗ spawn 失败: {type(e).__name__}: {e}"
