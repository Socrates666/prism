"""Registry — tool/prompt/skill 注册表 + ext/ 容错加载(原则 12)。

原则 12: ext/ 人格插件 —— 全局共享(注册表池), 每 agent 各自实例(非单例), 热插拔, 容错降级。

ext/ 约定:
  ext/<kind>/<name>.py  暴露 `def register(registry): ...`
  kind ∈ {tools, prompts, patches, skills}
  容错: 单个 ext 抛异常(import 错 / register 错) → 跳过该 ext + emit ext_error, 不炸其他。
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from typing import Callable

from .agent_loop import Tool

EXT_KINDS = ("tools", "prompts", "patches", "skills")


class Registry:
    """tool/prompt/skill 注册表(全局共享池)。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._prompts: dict[str, str] = {}
        self._skills: dict[str, object] = {}

    # ── tools ──
    def tool(self, t: Tool) -> Tool:
        """注册一个 tool(装饰器或直调)。返回 t。"""
        self._tools[t.name] = t
        return t

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    # ── prompts ──
    def prompt(self, name: str, text: str) -> None:
        self._prompts[name] = text

    def get_prompt(self, name: str) -> str | None:
        return self._prompts.get(name)

    # ── skills ──
    def skill(self, name: str, obj: object) -> None:
        self._skills[name] = obj

    def get_skill(self, name: str):
        return self._skills.get(name)


def load_ext(ext_dir, registry: Registry,
             emit: Callable[[dict], None] | None = None) -> list[str]:
    """扫 ext_dir/<kind>/*.py, 每个暴露 register(registry), per-file 容错。

    坏的 ext(import 错 / register 抛异常 / 缺 register) → 跳过 + emit ext_error, 不炸其他。
    返回成功加载的模块名列表(形如 'tools/foo')。
    """
    emit = emit or (lambda e: None)
    ext_dir = Path(ext_dir)
    loaded: list[str] = []
    if not ext_dir.is_dir():
        return loaded
    for kind in EXT_KINDS:
        kdir = ext_dir / kind
        if not kdir.is_dir():
            continue
        for py in sorted(kdir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            modname = f"prism_ext_{kind}_{py.stem}"
            try:
                spec = importlib.util.spec_from_file_location(modname, py)
                if spec is None or spec.loader is None:
                    raise ImportError(f"无法为 {py} 建模块规格")  # pragma: no cover
                mod = importlib.util.module_from_spec(spec)
                sys.modules[modname] = mod
                spec.loader.exec_module(mod)
                register = getattr(mod, "register", None)
                if not callable(register):
                    emit({"type": "ext_error", "file": str(py),
                          "error": "缺 register(registry) 入口"})
                    continue
                register(registry)
                loaded.append(f"{kind}/{py.stem}")
            except Exception as e:
                emit({"type": "ext_error", "file": str(py),
                      "error": f"{type(e).__name__}: {e}"})
    return loaded


# 全局共享池(原则 12: 注册表池, 全局共享)。agent 默认引用它, ext/ 加载进它。
default_registry = Registry()
