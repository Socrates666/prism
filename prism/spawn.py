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


def spawn(name: str, model, *, file_tools: bool = True, tools: list[Tool] | None = None,
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

    granted: list[Tool] = []
    if file_tools:
        granted += make_file_tools(ws)
    granted += list(tools or [])

    from .agent import Agent
    agent = Agent(name, model, kind="sub", tools=granted, actor=True)
    agent.workspace = ws
    if emit is not None:
        agent.hooks["emit"] = emit
    if parent is not None:
        parent.namespace[name] = agent   # 父 agent 能 inject/读子 agent(原则 16)
    return agent
