# ext/skills

`/skill <name>` 读这里的 `<name>.md`，append 到 agent 的 system prompt。

放一个 `.md` 文件（如 `code-review.md`），内容就是 skill 指令。例：

```
/skill code-review
```

→ `ext/skills/code-review.md` 的内容注入 main agent system prompt。
