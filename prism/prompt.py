"""SystemPrompt — 结构化 system prompt(阶段 13)。

把 system prompt 拆成独立段, 各段可组合/覆盖(对齐 pi systemPrompt 可组合性):

  role 角色 / environment 环境 / capabilities 能力与工具 / instructions 指令 /
  guidelines 行为准则 / goal 目标 / skills 技能 / extra 自由追加

render() 组合成 markdown(## 段标题); set_override 整体替换。
/goal → set_goal; /skill → add_skill; 旧 append_to_system_prompt → add_extra。
"""
from __future__ import annotations


class SystemPrompt:
    def __init__(self):
        self.role: str = ""
        self.environment: str = ""
        self.capabilities: str = ""
        self.instructions: str = ""
        self.guidelines: str = ""
        self.goal: str = ""
        self.skills: list[str] = []
        self.extra: list[str] = []
        self._override: str | None = None

    def render(self) -> str:
        """组合各段为 markdown(## 标题分隔)。override 时整体返回。"""
        if self._override is not None:
            return self._override
        parts: list[str] = []
        if self.role:
            parts.append(f"## 角色\n{self.role}")
        if self.environment:
            parts.append(f"## 环境\n{self.environment}")
        if self.capabilities:
            parts.append(f"## 能力与工具\n{self.capabilities}")
        if self.instructions:
            parts.append(f"## 指令\n{self.instructions}")
        if self.guidelines:
            parts.append(f"## 行为准则\n{self.guidelines}")
        if self.goal:
            parts.append(f"## 当前目标\n{self.goal}")
        if self.skills:
            parts.append("## Skills\n" + "\n\n".join(self.skills))
        if self.extra:
            parts.append("\n\n".join(self.extra))
        return "\n\n".join(parts).strip()

    def set_override(self, text: str) -> None:
        """整体替换(对齐 pi systemPromptOverride)。"""
        self._override = text

    def set_goal(self, goal: str) -> None:
        self.goal = goal

    def add_skill(self, name: str, content: str) -> None:
        self.skills.append(f"### {name}\n{content}")

    def add_extra(self, text: str) -> None:
        """自由追加(兼容旧 append_to_system_prompt)。"""
        self.extra.append(text)
