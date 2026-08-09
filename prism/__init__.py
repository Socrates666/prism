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


def _load_env():
    """读 prism 目录的 .env 填进 os.environ(不覆盖已有)。让 .env 里的 key/url/model 自动生效。"""
    import os
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
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
