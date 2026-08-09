"""指令: 加载 skill 注入 system prompt。

/skill <name>     读 ext/skills/<name>.md, append 到 agent system prompt
"""
NAME = "skill"
DESC = "加载 skill: /skill <name>  (从 ext/skills/<name>.md)"


def run(args, ctx):
    from pathlib import Path
    name = args.strip()
    if not name:
        return "用法: /skill <name>"
    p = Path("ext/skills") / f"{name}.md"
    if not p.exists():
        return f"✗ skill 不存在: {p}"
    content = p.read_text(encoding="utf-8")
    ctx["agent"].prompt.add_skill(name, content)
    return f"✓ skill 已注入(→ ## Skills 段): {name} ({len(content)} 字)"
