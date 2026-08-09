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

from .agent import Agent
from .model import ModelBackend, OpenAIModel

__all__ = ["Agent", "ModelBackend", "OpenAIModel"]
__version__ = "0.0.1"
