# 自研 TUI(textual 接口相近, 模仿 piagent 外观)

> 分支 `feat/self-tui`, 路径 `D:/workspace/projects/prism-tui`(从 prism clone)。

## 目标
1. 去掉 `textual`/`rich` 依赖, 自研一套 **API 与 textual 相近**(App/compose/query_one/
   call_from_thread/CSS/Header/Input/RichLog/Static)的 TUI 引擎。
2. 外观/功能对齐 piagent: **Header(快捷键提示) / Messages(滚动 transcript) /
   Editor(边框=accent, 多行) / Footer(cwd·model·busy)** 四段式纵向布局。
3. prism 现有行为完全保留(emit 事件流、`/`·`@`·Python 路由、跨线程 streaming、steer)。

## 架构 `prism/tui/`
| 文件 | 职责 |
|------|------|
| `terminal.py` | Win32(VT 处理+ReadConsoleInputW)+ POSIX(termios) 双后端; raw 模式/alt screen/隐藏光标/尺寸事件/按键线程 |
| `buffer.py` | 离屏 cell 网格 + box 绘制 + 按行 diff 刷新(每行末 SGR reset, 仿 pi) |
| `markup.py` | rich 风格 `[bold cyan]…[/]` → 样式段; 处理 bold/italic/dim/underline + 颜色名 + 栈式嵌套 + 定宽换行 |
| `css.py` | 极小子集: `#id{height;layout;border;padding;color}`; fixed/auto/1fr |
| `widget.py` | Widget 基类(id/can_focus/region/draw); vertical-flex 布局 |
| `widgets.py` | Header / RichLog(滚动) / Static / Input(多行+光标) / Footer |
| `app.py` | App: run()/compose()/on_mount()/on_key()/on_input_submitted()/call_from_thread()/query_one()/theme |
| `render_test.py` | 无真实终端也能渲染到 str 的夹具(单测用) |

## shell.py 改写
- 保留全部 emit 路由逻辑, 仅把 `PrismApp(textual.App)` 换成 `tui.App`。
- transcript 区用 pi 风格: 用户消息 `❯`(accent), 工具块 `▸ name … / ✓ 观察`,
  认知五阶段 magenta/yellow。Editor accent 边框; Footer 显示 cwd·model·busy●。

## 验证
- buffer/markup/css/layout/app 单测(headless, 渲染到 str 断言)。
- `python -m prism.shell` 跑真实终端冒烟(手动)。
- pyproject 去掉 textual, 新增 prism 自研 tui 包。

## 关键约束
- 跨线程: agent 在后台线程 emit, 必须经 `call_from_thread` 回主循环线程改 widget。
- 无外部重依赖; 仅 ctypes+标准库 + 既有 openai/requests。
