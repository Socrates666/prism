"""spawn — 子 agent 工厂 + 文件工具闭包(原则 13/14)。

原则 13: 子 agent 工厂受限 —— 无裸 exec(python 工具), 只有工厂赋予的工具。
原则 14: 工作区分层 —— 子 agent workspace=workspaces/<name>/(独占);
         文件工具闭包绑定 ws(不依赖进程 cwd → 多 agent 防踩踏)。
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from .agent_loop import Tool


def make_file_tools(ws) -> list[Tool]:
    """闭包绑定 ws 的 read/write/ls。不碰进程 cwd → 多 agent 不踩踏(原则 14)。"""
    ws = Path(ws)

    def _resolve(p):
        p = Path(p)
        return p if p.is_absolute() else ws / p

    def read(args):
        p = _resolve(args.get("path", ""))
        if not p.exists():
            return ("error", f"不存在: {p}")
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return ("error", f"{type(e).__name__}: {e}")

    def write(args):
        path = args.get("path", "")
        content = args.get("content", "")
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {path}"

    def ls(args):
        p = _resolve(args.get("path", "."))
        if not p.is_dir():
            return ("error", f"不是目录: {p}")
        return ", ".join(sorted(x.name for x in p.iterdir()))

    return [
        Tool("read", "读文件(绑当前 workspace)", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, read),
        Tool("write", "写文件(绑当前 workspace)", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}, write),
        Tool("ls", "列目录(绑当前 workspace)", {"type": "object", "properties": {"path": {"type": "string"}}}, ls),
    ]


# ── 文件锁: 多 agent 并发改代码的安全网 ──────────────────
import threading as _threading

_file_locks: dict[str, str] = {}       # {abs_path: agent_name}
_locks_mutex = _threading.Lock()


def acquire_lock(path: str, agent_name: str) -> tuple[bool, str]:
    """尝试获取文件写锁。成功返回 (True, ''), 被占返回 (False, holder)。"""
    import os
    abs_path = os.path.abspath(path)
    with _locks_mutex:
        holder = _file_locks.get(abs_path)
        if holder and holder != agent_name:
            return (False, holder)
        _file_locks[abs_path] = agent_name
        return (True, "")


def release_lock(path: str, agent_name: str) -> None:
    """释放文件锁(只释放自己的)。"""
    import os
    abs_path = os.path.abspath(path)
    with _locks_mutex:
        if _file_locks.get(abs_path) == agent_name:
            del _file_locks[abs_path]


def make_project_tools(agent_name: str, project_root: str = ".") -> list[Tool]:
    """项目文件工具: 能读写项目根目录, 带文件锁。

    与 workspace file_tools 的区别:
    - workspace tools 绑定 workspaces/<name>/, 无锁(独占)
    - project tools 绑定项目根, 有锁(共享资源)
    """
    root = Path(project_root).resolve()

    def _resolve(p):
        p = Path(p)
        return p if p.is_absolute() else root / p

    def read_file(args):
        p = _resolve(args.get("path", ""))
        if not p.exists():
            return ("error", f"不存在: {p}")
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return ("error", f"{type(e).__name__}: {e}")

    def edit_file(args):
        """声明编辑意图: 获取文件锁。写之前必须先 edit。"""
        path = args.get("path", "")
        p = _resolve(path)
        ok, holder = acquire_lock(str(p), agent_name)
        if ok:
            return f"✓ 已锁定 {path}"
        return (f"error: {path} 被 {holder} 锁定中, 等它完成或换文件", True)

    def write_file(args):
        """写入文件(需要先 edit_file 获取锁)。写完自动释放锁。"""
        path = args.get("path", "")
        content = args.get("content", "")
        p = _resolve(path)
        # 检查锁
        ok, holder = acquire_lock(str(p), agent_name)
        if not ok and holder != agent_name:
            return (f"error: {path} 被 {holder} 锁定, 先 edit_file 获取锁", True)
        # 写入(走 guarded_open, 写 prism/ 自动备份)
        from .guard import restricted_builtins
        sb = restricted_builtins()
        p.parent.mkdir(parents=True, exist_ok=True)
        sb["open"](p, "w", encoding="utf-8").write(content)
        release_lock(str(p), agent_name)
        return f"wrote {path} ({len(content)} chars)"

    def list_dir(args):
        p = _resolve(args.get("path", "."))
        if not p.is_dir():
            return ("error", f"不是目录: {p}")
        items = []
        for x in sorted(p.iterdir()):
            tag = "D" if x.is_dir() else "F"
            items.append(f"[{tag}] {x.name}")
        return "\n".join(items)

    return [
        Tool("read_file", "读项目文件(任意路径)", 
             {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径(相对项目根)"}}, "required": ["path"]},
             read_file),
        Tool("edit_file", "锁定文件准备编辑(获取写锁, 防止并发冲突)",
             {"type": "object", "properties": {"path": {"type": "string", "description": "要编辑的文件路径"}}, "required": ["path"]},
             edit_file),
        Tool("write_file", "写入文件(需先 edit_file 获取锁, 写完自动释放)",
             {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
             write_file),
        Tool("list_dir", "列目录(项目任意路径)",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
             list_dir),
    ]


def spawn(name: str, model, *, file_tools: bool = True, project_tools: bool = False,
          tool_names: list[str] | None = None, tools: list[Tool] | None = None,
          emit: Callable[[dict], None] | None = None, workspaces_root: str = "workspaces",
          parent=None):
    """生产一个子 agent(原则 13/14)。

    - 独占 workspace=workspaces_root/<name>/; 已存在 → ValueError(不重复)
    - 无裸 exec python 工具(原则 13); 只有 file_tools(闭包绑 ws) + 赋予的 tools
    - emit: 若给, 设为该 agent 的 hooks["emit"](TUI 用它把子 agent 输出汇入主 transcript)

    返回的 Agent 已是 kind="sub"(actor 线程已起)。调用方负责把它的 emit 桥到 UI。
    """
    ws = Path(workspaces_root) / name
    if ws.exists():
        raise ValueError(f"'{name}' 工作区已存在(子 agent workspace 不重复)")
    ws.mkdir(parents=True)

    # 构建工具池
    ws_tools = {t.name: t for t in make_file_tools(ws)}
    proj_tools = {t.name: t for t in make_project_tools(name)}
    all_pool = {}
    all_pool.update(ws_tools)
    all_pool.update(proj_tools)

    granted: list[Tool] = []
    if tool_names:
        # 声明式: 按 tools 列表选
        for tn in tool_names:
            if tn in all_pool:
                granted.append(all_pool[tn])
            # else: 可能是 registry 注入的(如 search), skip — Agent.__init__ 会从 registry 加
    else:
        # 布尔兼容: 旧接口
        if file_tools:
            granted += make_file_tools(ws)
        if project_tools:
            granted += make_project_tools(name)
    granted += list(tools or [])  # 额外手工赋予

    from .agent import Agent
    agent = Agent(name, model, kind="sub", tools=granted, actor=True)
    agent.workspace = ws
    if emit is not None:
        agent.hooks["emit"] = emit
    elif parent is not None and parent.hooks.get("emit"):
        agent.hooks["emit"] = parent.hooks["emit"]   # 继承父 emit, 避免默认 _default_emit print 跳出 TUI
    if parent is not None:
        parent.namespace[name] = agent   # 父 agent 能 inject/读子 agent(原则 16)
    return agent
