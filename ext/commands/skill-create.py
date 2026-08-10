"""指令: 创建新 skill。

/skill-create <name> <描述>    创建 skills/<name>/SKILL.md 骨架
/skill-create <name>            交互式(提示输入描述和步骤)
"""
NAME = "skill-create"
DESC = "创建新 skill: /skill-create <name> [描述]"


def run(args, ctx):
    from pathlib import Path

    parts = args.strip().split(None, 1)
    if not parts or not parts[0]:
        return "用法: /skill-create <name> [描述]"

    name = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else "(待填充)"

    import re
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9\-]*$', name):
        return f"✗ 无效 skill 名: '{name}'。只允许字母数字和连字符。"

    skill_dir = Path("ext/skills") / name
    skill_path = skill_dir / "SKILL.md"

    if skill_path.exists():
        return f"⚠ skill 已存在: {skill_path}\n  用 /skill {name} 加载, 或改个名字。"

    skill_dir.mkdir(parents=True, exist_ok=True)

    template = f"""---
name: {name}
description: "{desc}"
version: 1.0.0
---

# {name}

{desc}

## 何时使用
- (描述触发条件)

## 执行步骤
1. (步骤1)
2. (步骤2)

## 输出格式
- (期望的输出格式)

## 示例
(具体的输入输出示例)
"""

    skill_path.write_text(template, encoding="utf-8")
    return (
        f"✓ skill 骨架已创建: {skill_path} ({len(template)} 字)\n"
        f"  编辑文件补充内容, 然后:\n"
        f"  /skill {name}"
    )
