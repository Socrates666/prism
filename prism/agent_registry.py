"""ext/agents/ 注册表 — 声明式 agent 配置, 重启自动恢复。

每个 .yaml 文件描述一个 agent:

  ext/agents/coder.yaml:
    name: coder
    kind: sub
    file_tools: true
    project_tools: true
    extra_prompt: |
      你是 coder, 编码子 agent。
      文件锁规则: 编辑前先 edit_file...
    skills: []           # 可选, 启动时加载的 skill
    max_turns: 20

  ext/agents/prism.yaml:
    name: Prism
    kind: main
    max_turns: 20
    thinking_level: off

shell.py on_mount 扫 ext/agents/*.yaml, 按配置 spawn + apply prompt + load skills。
"""
from __future__ import annotations
import os
from pathlib import Path


def load_agent_configs(agents_dir: str = "ext/agents") -> list[dict]:
    """加载所有 agent 配置。返回 dict 列表(排序: main 先, sub 后)。"""
    import yaml as _yaml
    configs = []
    p = Path(agents_dir)
    if not p.is_dir():
        return configs
    for f in sorted(p.glob("*.yaml")):
        try:
            cfg = _yaml.safe_load(f.read_text(encoding="utf-8"))
            if cfg and "name" in cfg:
                configs.append(cfg)
        except Exception:
            pass
    # main 先
    configs.sort(key=lambda c: (0 if c.get("kind") == "main" else 1, c["name"]))
    return configs


def restore_agents(app, emit):
    """从 ext/agents/ 配置恢复所有 agent。返回 (main_agent, sub_agents)。
    
    app: PrismApp 实例
    emit: emit 函数
    """
    from .model import OpenAIModel
    from .spawn import spawn
    from .registry import default_registry
    from .memory import FileMemory
    
    configs = load_agent_configs()
    main_agent = None
    subs = []
    
    for cfg in configs:
        name = cfg["name"]
        kind = cfg.get("kind", "sub")
        model_cfg = cfg.get("model", {})
        
        # 创建 model
        model = OpenAIModel(
            model=model_cfg.get("model"),
            base_url=model_cfg.get("base_url"),
            api_key=model_cfg.get("api_key"),
            thinking_level=cfg.get("thinking_level"),
        )
        
        if kind == "main":
            # 主 agent: 不用 spawn, 直接建
            from .agent import Agent
            memory = FileMemory(".prism/memory")
            agent = Agent(name, model, kind="main", 
                         registry=default_registry, memory=memory,
                         max_turns=cfg.get("max_turns", 20),
                         thinking_level=cfg.get("thinking_level", "off"))
            sections = default_registry.get_prompt("prism")
            if sections:
                agent.apply_prompt(sections, name, "main")
            agent.hooks["emit"] = emit
            main_agent = agent
        else:
            # 子 agent: 用 spawn
            file_tools = cfg.get("file_tools", True)
            project_tools = cfg.get("project_tools", False)
            
            # workspace 可能已存在(上次的), 不重建
            ws_path = Path(f"workspaces/{name}")
            if ws_path.exists():
                # 删旧的重建
                import shutil
                shutil.rmtree(ws_path)
            
            agent = spawn(name, model, emit=emit, parent=main_agent,
                         file_tools=file_tools, project_tools=project_tools,
                         workspaces_root="workspaces")
            
            # 应用 prompt
            sections = default_registry.get_prompt("prism")
            if sections:
                agent.apply_prompt(sections, name, "sub")
            
            # 注入额外指令
            extra = cfg.get("extra_prompt", "")
            if extra:
                agent.prompt.add_extra(extra)
            
            # 加载 skill
            for skill_name in cfg.get("skills", []):
                skill_path = Path("ext/skills") / skill_name / "SKILL.md"
                if skill_path.exists():
                    content = skill_path.read_text(encoding="utf-8")
                    agent.prompt.add_skill(skill_name, content)
            
            subs.append(agent)
    
    return main_agent, subs


def save_agent_config(name: str, cfg: dict, agents_dir: str = "ext/agents") -> Path:
    """保存 agent 配置到 ext/agents/<name>.yaml。"""
    import yaml as _yaml
    p = Path(agents_dir)
    p.mkdir(parents=True, exist_ok=True)
    fpath = p / f"{name}.yaml"
    fpath.write_text(
        _yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8")
    return fpath
