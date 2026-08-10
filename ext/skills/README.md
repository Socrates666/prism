# ext/skills

每个 skill 是一个目录, 包含 `SKILL.md`:

```
skills/
├── werden/
│   └── SKILL.md
├── code-review/
│   └── SKILL.md
└── ...
```

`/skill <name>` 读 `skills/<name>/SKILL.md`, 注入 main agent system prompt。
`/skill list` 列出所有可用 skill。
`/skill-create <name>` 创建新 skill 骨架。

## SKILL.md 格式

```markdown
---
name: skill-name
description: "触发条件和用途描述"
version: 1.0.0
---

# Skill Name

## 何时使用
...

## 执行步骤
...
```
