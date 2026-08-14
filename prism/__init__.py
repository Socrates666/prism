"""prism — 棱镜: 一个 IPython 内核里的 agent 外壳.

核心:
  Agent        ReAct 循环 agent, 跑在共享命名空间, hooks 自举显示
  ModelBackend LLM 接入接口(可插拔)
  OpenAIModel  OpenAI 兼容实现
"""
import sys
# Windows 终端默认 GBK, agent 输出含 unicode(▸ 等)会炸 —— 强制 utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load_env(paths=None):
    """读 .env 填进 os.environ(不覆盖已有)。让 .env 里的 key/url/model 自动生效。

    查找顺序: 包根(仓库根)/.env → 进程 cwd/.env(通用约定, 从任意目录启动该目录的
    .env 也生效)。.env 被 gitignore 不随 clone/worktree 传播, cwd 兜底让各 checkout
    只需自备一份。都不存在则静默跳过。
    """
    import os
    from pathlib import Path
    if paths is None:
        paths = [Path(__file__).resolve().parent.parent / ".env",
                 Path.cwd() / ".env"]
    for env in paths:
        if not env.is_file():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue  # pragma: no cover  (comment/空行)
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k and k not in os.environ:
                os.environ[k] = v


_load_env()

from .agent import Agent
from .model import ModelBackend, OpenAIModel

__all__ = ["Agent", "ModelBackend", "OpenAIModel"]
__version__ = "0.0.1"


def load_ipython_extension(ipython):
    """IPython 启动时加载: 注册 @ 路由 transformer。"""
    from .router import register
    register(ipython)
