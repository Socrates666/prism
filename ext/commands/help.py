"""指令: /help — 指令 / 按键 / 输入路由 / 概念 四段速查。"""
NAME = "help"
DESC = "查看帮助: 指令 · 按键 · 输入路由 · 概念"

# 全 app 按键绑定(与 tui/app.py _dispatch_key + widgets Input.on_key 对齐)
KEYBINDS = [
    ("Esc", "中断当前 agent（补全浮层开着时先关浮层）"),
    ("Tab", "补全 / 指令；循环切换 @agent"),
    ("Shift+Enter / Ctrl+J", "输入框换行（多行编辑）"),
    ("Ctrl+A / Ctrl+E", "光标到行首 / 行尾"),
    ("Ctrl+U / Ctrl+K", "删到行首 / 删到行尾"),
    ("Ctrl+W", "删除光标前一个词"),
    ("PageUp / PageDown", "滚动对话区（Home/End 到顶/底）"),
    ("↑ / ↓", "翻输入历史（多行时上下移动光标）"),
    ("Ctrl+C", "中断 agent / 清空输入 / 再按一次退出"),
]


def run(args, ctx):
    # 单一事实源: app.all_commands()(ext + 内置 revert/backups), 不再各抄一份清单
    app = ctx.get("app")
    if app is not None:
        cmds = app.all_commands()
    else:                                    # 无 app 兜底(脱离 TUI 调用)
        cmds = {n: getattr(m, "DESC", "") for n, m in ctx.get("commands", {}).items()}
    lines = ["指令:"]
    for n in sorted(cmds):
        desc = str(cmds[n]).replace("[", "\\[")   # 防 [ 被当 markup 吞掉, 参数语法可见
        lines.append(f"  /{n:<12} {desc}")
    lines.append("按键:")
    for k, d in KEYBINDS:
        lines.append(f"  {k:<22} {d}")
    lines += [
        "输入路由:",
        "  /指令   斜杠指令（Tab 补全，↑↓ 翻历史）",
        "  @agent  把消息发给指定 agent，如 @Prism 帮我看看这段代码",
        "  裸文本  Python 直通（exec 执行，print 输出到对话区）",
        "概念:",
        "  折射     = 认知循环（直觉 → 行动 → 反思 → 记忆沉淀）",
        "  直觉     = 行动前从 forest 记忆联想相关经验",
        "  思考     = 模型 reasoning 推理段",
        "  反思     = 行动后复盘，产出经验写回 forest",
        "  based_on = 直觉/反思引用的记忆条目标注",
    ]
    return "\n".join(lines)
