"""MemoryBackend — 跨会话状态持久化(原则 6/7, 阶段 10)。

原则 6: 持久化是核心地基(强杀重启恢复)。
原则 7: 后端全可插拔 —— MemoryBackend ABC, NullMemory/FileMemory/... 可换。

agent.messages 通过 memory dump/load 跨会话延续(原始痛点: 跨会话 agent 交互)。
"""
from __future__ import annotations
import json
from abc import ABC, abstractmethod
from pathlib import Path


class MemoryBackend(ABC):
    """跨会话状态后端(可插拔, 原则 7)。"""

    @abstractmethod
    def save(self, key: str, messages: list[dict]) -> None: ...

    @abstractmethod
    def load(self, key: str) -> list[dict]: ...

    @abstractmethod
    def clear(self, key: str) -> None: ...

    def keys(self) -> list[str]:
        return []  # pragma: no cover  (default, 子类 override)


class NullMemory(MemoryBackend):
    """空实现(不持久化, 开发/测试默认)。"""

    def save(self, key, messages): pass
    def load(self, key): return []
    def clear(self, key): pass


class FileMemory(MemoryBackend):
    """文件持久化: 每个 key 一个 <root>/<key>.json。"""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def save(self, key, messages):
        self._path(key).write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, key):
        p = self._path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def clear(self, key):
        p = self._path(key)
        if p.exists():
            p.unlink()

    def keys(self):
        return sorted(p.stem for p in self.root.glob("*.json"))
