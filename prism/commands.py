"""slash 指令加载(ext/commands/*.py)。

每个指令是一个 .py, 暴露:
  NAME  str       指令名(/NAME)
  DESC  str       描述
  run(args: str, ctx: dict) -> str | None
    ctx = {"agent": 主agent, "app": PrismApp, "write": 写transcript, "commands": 所有指令}
    返回字符串 → 写 transcript; None → 不写

容错: 单个指令坏(import/run 缺失) → 跳过 + emit ext_error, 不炸其他。
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from typing import Callable


def load_commands(ext_dir, emit: Callable[[dict], None] | None = None) -> dict:
    """扫 ext_dir/commands/*.py, 返回 {NAME: module}。"""
    emit = emit or (lambda e: None)
    cdir = Path(ext_dir) / "commands"
    cmds: dict[str, object] = {}
    if not cdir.is_dir():
        return cmds
    for py in sorted(cdir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        modname = f"prism_cmd_{py.stem}"
        try:
            spec = importlib.util.spec_from_file_location(modname, py)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法建模块规格: {py}")  # pragma: no cover
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
            if hasattr(mod, "NAME") and callable(getattr(mod, "run", None)):
                cmds[mod.NAME] = mod
            else:
                emit({"type": "ext_error", "file": str(py), "error": "缺 NAME/run 入口"})
        except Exception as e:
            emit({"type": "ext_error", "file": str(py), "error": f"{type(e).__name__}: {e}"})
    return cmds
