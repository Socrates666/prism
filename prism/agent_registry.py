"""ext/agents/ 注册表 — 声明式 agent 配置, 重启自动恢复。

每个 agent 一个二级目录:
  ext/agents/
    prism/
      agent.yaml     # 元配置(kind/model/tools/max_turns)
      prompt.yaml    # system prompt 各段
    coder/
      agent.yaml
      prompt.yaml
"""
from __future__ import annotations
import os
from pathlib import Path


def load_agent_config(agent_dir: Path) -> dict | None:
    """加载单个 agent 配置(agent.yaml + prompt.yaml 合并)。"""
    import yaml as _yaml
    agent_yaml = agent_dir / "agent.yaml"
    prompt_yaml = agent_dir / "prompt.yaml"
    if not agent_yaml.exists():
        return None
    cfg = _yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
    if prompt_yaml.exists():
        cfg["prompt_sections"] = _yaml.safe_load(prompt_yaml.read_text(encoding="utf-8")) or {}
    return cfg


def load_agent_configs(agents_dir: str = "ext/agents") -> list[dict]:
    """加载所有 agent 配置。"""
    configs = []
    p = Path(agents_dir)
    if not p.is_dir():
        return configs
    for d in sorted(p.iterdir()):
        if d.is_dir() and (d / "agent.yaml").exists():
            cfg = load_agent_config(d)
            if cfg and "name" in cfg:
                configs.append(cfg)
        elif d.is_file() and d.suffix == ".yaml":
            import yaml as _yaml
            try:
                cfg = _yaml.safe_load(d.read_text(encoding="utf-8"))
                if cfg and "name" in cfg:
                    configs.append(cfg)
            except Exception:
                pass
    configs.sort(key=lambda c: (0 if c.get("kind") == "main" else 1, c["name"]))
    return configs


def _apply_prompt_from_config(agent, cfg):
    """从配置的 prompt_sections 设置 agent 的 system prompt。"""
    sections = cfg.get("prompt_sections")
    if not sections:
        return
    p = agent.prompt
    name = agent.name
    for key in ("role", "environment", "capabilities", "instructions", "guidelines"):
        val = sections.get(key)
        if val:
            if key == "role" and "{name}" in val:
                val = val.format(name=name)
            setattr(p, key, val)
    extra = cfg.get("extra_prompt")
    if extra:
        p.add_extra(extra)


def restore_agents(app, emit):
    """从 ext/agents/ 配置恢复所有 agent。"""
    from .model import OpenAIModel
    from .spawn import spawn
    from .registry import default_registry
    from .memory import FileMemory
    from .agent import Agent

    configs = load_agent_configs()
    main_agent = None
    subs = []

    for cfg in configs:
        name = cfg["name"]
        kind = cfg.get("kind", "sub")
        model_cfg = cfg.get("model", {})

        model = OpenAIModel(
            model=model_cfg.get("model"),
            base_url=model_cfg.get("base_url"),
            api_key=model_cfg.get("api_key"),
            thinking_level=cfg.get("thinking_level"),
        )

        if kind == "main":
            memory = FileMemory(".prism/memory")
            agent = Agent(name, model, kind="main",
                         registry=default_registry, memory=memory,
                         max_turns=cfg.get("max_turns", 20),
                         thinking_level=cfg.get("thinking_level", "medium"))
            _apply_prompt_from_config(agent, cfg)
            agent.hooks["emit"] = emit
            main_agent = agent
        else:
            tool_names = cfg.get("tools")  # 声明式工具列表
            ws_path = Path(f"workspaces/{name}")
            if ws_path.exists():
                import shutil
                shutil.rmtree(ws_path)
            agent = spawn(name, model, emit=emit, parent=main_agent,
                         tool_names=tool_names)
            _apply_prompt_from_config(agent, cfg)
            for skill_name in cfg.get("skills", []):
                skill_path = Path("ext/skills") / skill_name / "SKILL.md"
                if skill_path.exists():
                    content = skill_path.read_text(encoding="utf-8")
                    agent.prompt.add_skill(skill_name, content)
            subs.append(agent)

    return main_agent, subs


def save_agent_config(name: str, cfg: dict, agents_dir: str = "ext/agents") -> Path:
    """保存 agent 配置到 ext/agents/<name>/agent.yaml。"""
    import yaml as _yaml
    agent_dir = Path(agents_dir) / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    fpath = agent_dir / "agent.yaml"
    fpath.write_text(
        _yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8")
    return fpath
