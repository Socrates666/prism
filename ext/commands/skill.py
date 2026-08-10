"""指令: 加载/列出 skill。

/skill <name>     读 skills/<name>/SKILL.md, append 到 agent system prompt
/skill list       列出所有可用 skill
"""
NAME = "skill"
DESC = "加载或列出 skill: /skill <name> | /skill list"


def _find_skill(name):
    """查找 skill 文件, 兼容新旧格式。"""
    from pathlib import Path
    skill_dir = Path("ext/skills")
    # 新格式: skills/<name>/SKILL.md
    p = skill_dir / name / "SKILL.md"
    if p.exists():
        return p
    # 旧格式: skills/<name>.md (兼容)
    p = skill_dir / f"{name}.md"
    if p.exists():
        return p
    return None


def run(args, ctx):
    from pathlib import Path
    name = args.strip()
    if not name:
        return "用法: /skill <name>  或  /skill list"

    skill_dir = Path("ext/skills")

    if name == "list":
        if not skill_dir.is_dir():
            return "(无 skill 目录)"
        skills = []
        # 新格式: 目录含 SKILL.md
        for d in sorted(skill_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                skill_file = d / "SKILL.md"
                desc = ""
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    # 读 YAML frontmatter 的 description
                    if content.startswith("---"):
                        import re
                        m = re.search(r'description:\s*["\']?(.+?)["\']?\s*\n', content[:500])
                        if m:
                            desc = m.group(1).strip()[:80]
                    # 或者读第一行标题
                    if not desc:
                        for line in content.split("\n"):
                            line = line.strip()
                            if line.startswith("# ") and not line.startswith("## "):
                                desc = line.lstrip("# ").strip()
                                break
                except:
                    pass
                skills.append(f"  /skill {d.name:25s} — {desc}")
        # 旧格式: 直接 .md
        for f in sorted(skill_dir.glob("*.md")):
            if f.name in ("README.md",) or f.name.startswith("_"):
                continue
            skills.append(f"  /skill {f.stem:25s} — (旧格式)")
        if not skills:
            return "(无可用 skill)"
        return "可用 skill:\n" + "\n".join(skills)

    p = _find_skill(name)
    if p is None:
        return f"✗ skill 不存在: {name}\n  用 /skill list 查看可用 skill, 或 /skill-create {name} 创建"

    content = p.read_text(encoding="utf-8")
    ctx["agent"].prompt.add_skill(name, content)
    return f"✓ skill 已注入(→ ## Skills 段): {name} ({len(content)} 字)"
