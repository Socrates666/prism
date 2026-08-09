"""prism REPL 入口 —— 起一个 IPython 内核, 注入 Agent。

启动后用户直接用 Python:
    a = Agent("alice", model=OpenAIModel())   # 创建第一个 agent
    a.run("算 2+2 存到 x")                      # agent 在内核建变量
    x                                            # 直接访问(共享命名空间)
    a.system_prompt = "你只说海盗话"             # 改 agent 自己的 prompt
"""
from __future__ import annotations


BANNER = """\
╭─ prism ─ 棱镜 ─────────────────────────────────────╮
│  一个 IPython 内核里的 agent 外壳                   │
│                                                     │
│  a = Agent("alice", model=OpenAIModel())           │
│  a.run("...")   /   a.chat("...")                   │
│  直接敲 Python —— 跟 agent 共享命名空间             │
│  a.system_prompt = "..."   # 改 agent 自己          │
╰─────────────────────────────────────────────────────╯

环境变量: PRISM_MODEL / OPENAI_BASE_URL / OPENAI_API_KEY
"""


def main():
    """起 IPython REPL, 预填 Agent / OpenAIModel 到命名空间。"""
    import IPython
    from .agent import Agent
    from .model import OpenAIModel

    user_ns = {
        "Agent": Agent,
        "OpenAIModel": OpenAIModel,
    }
    IPython.start_ipython(argv=[], user_ns=user_ns, banner1=BANNER)


if __name__ == "__main__":
    main()
