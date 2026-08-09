"""护栏(原则 2/10) —— 拦主 agent 写 prism/ 核心。

原则 2: 硬护栏只护 agent 自身运作(客观/硬编码/不靠 LLM 揣测)。
原则 10: 默认实现 immutable + 扩展层隔离 —— 不允许 overwrite prism/, 允许增量扩建。

实现: 包装主 agent exec 命名空间的 open, 写 prism/ 目录 → PermissionError。
已知绕过路径(os / subprocess / pathlib.write 等)记为开放问题 —— 不可能 100% 拦 exec 任意代码,
但拦最常见路径(原则 2 精神: 客观硬编码, 不靠揣测), 其余走 add_patch/add_tool 正道。
"""
from __future__ import annotations
import builtins
from pathlib import Path

_REAL_OPEN = builtins.open
_PRISM_CORE = Path(__file__).resolve().parent   # prism/ 包目录(不可 overwrite)


def is_under(path, base: Path = _PRISM_CORE) -> bool:
    try:
        Path(path).resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def guarded_open(file, mode="r", *args, **kwargs):
    """写 prism/ 核心 → PermissionError; 其余透传真实 open。"""
    if any(c in str(mode) for c in "wax+") and is_under(file):
        raise PermissionError(
            f"护栏(原则 2/10): 不允许写 prism/ 核心 '{file}'。"
            f" 用 ext/ 扩展或 agent.add_patch/add_tool 增量扩建。")
    return _REAL_OPEN(file, mode, *args, **kwargs)


def restricted_builtins() -> dict:
    """受限 builtins: open 换 guarded_open, 其余原样(agent 正常 python 不受影响)。"""
    sb = dict(vars(builtins))
    sb["open"] = guarded_open
    return sb
