"""护栏(原则 2/10) —— 可变 base + 自动回退(阶段 14)。

原则 10 演进: base 可写(agent 自我演进), 但三层安全网:
  ① 写 prism/ 前自动备份(.prism/backups/<file>.<ts>.bak)
  ② verify_and_revert: 改后 importlib.reload 改动模块, 语法/import 错 → 自动还原
  ③ /revert 第一公民指令(base, 不在 ext/)手动回退

注: reload 只抓语法/import 错; 运行时逻辑错靠 /revert。改完提示重启(已运行实例引用旧类)。
"""
from __future__ import annotations
import builtins
import shutil
import sys
import time
from pathlib import Path

_REAL_OPEN = builtins.open
_PRISM_CORE = Path(__file__).resolve().parent   # prism/ 包目录(可写, 改前备份)

_backups: list[tuple[Path, Path]] = []           # (original, bak) 改动栈


def is_under(path, base=None) -> bool:
    b = _PRISM_CORE if base is None else base
    try:
        Path(path).resolve().relative_to(b.resolve())
        return True
    except (ValueError, OSError):
        return False


def _backup_dir() -> Path:
    d = _PRISM_CORE.parent / ".prism" / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_to_module(p: Path) -> str | None:
    """prism/agent.py → prism.agent; prism/__init__.py → prism; 非 prism/ → None。"""
    try:
        rel = p.resolve().relative_to(_PRISM_CORE.resolve())
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__.py":
        return "prism" + (("." + ".".join(parts[:-1])) if len(parts) > 1 else "")
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
        return "prism." + ".".join(parts)
    return None


def _backup(p: Path) -> Path | None:
    if p.exists():
        bak = _backup_dir() / f"{p.name}.{int(time.time() * 1000)}.bak"
        shutil.copy2(p, bak)
        _backups.append((p, bak))
        return bak
    return None


def guarded_open(file, mode="r", *args, **kwargs):
    """写 prism/ 核心 → 自动备份 + 放行(阶段14, 不再 PermissionError)。"""
    if any(c in str(mode) for c in "wax+") and is_under(file):
        _backup(Path(file).resolve())
    return _REAL_OPEN(file, mode, *args, **kwargs)


def restricted_builtins() -> dict:
    """受限 builtins: open 换 guarded_open(写 prism/ 备份), 其余原样。"""
    sb = dict(vars(builtins))
    sb["open"] = guarded_open
    return sb


# ── 自动回退 / 手动 revert API ──────────────────────
def changed_files() -> list[tuple[Path, Path]]:
    """当前未验证的改动列表。"""
    return list(_backups)


def verify_and_revert(emit) -> bool:
    """reload 改动的 prism 模块; 语法/import 错 → 还原备份。返回是否全 OK。

    reload 只抓加载期错误(语法/导入); 运行时逻辑错不在范围(靠 /revert)。
    """
    import importlib
    if not _backups:
        return True
    to_check = list(_backups)
    _backups.clear()
    all_ok = True
    for orig, bak in to_check:
        mod_name = _file_to_module(orig)
        if not mod_name or mod_name not in sys.modules:
            continue
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception as e:
            shutil.copy2(bak, orig)
            emit({"type": "error",
                  "error": f"自动回退 {orig.name}: {type(e).__name__}: {e}"})
            all_ok = False
    return all_ok


def revert_latest(emit) -> str | None:
    """/revert: 回退到最近一次改动, 还原原文件, 返回文件名。"""
    if not _backups:
        return None
    orig, bak = _backups.pop()
    shutil.copy2(bak, orig)
    return orig.name


def list_backups() -> list[tuple[str, str]]:
    """列出改动栈: [(orig_name, bak_name), ...]。"""
    return [(o.name, b.name) for o, b in _backups]
