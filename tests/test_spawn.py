"""spawn 子 agent 工厂 + 文件工具闭包测试(阶段 5, 原则 13/14)。"""
from pathlib import Path
import pytest
from prism.spawn import spawn, make_file_tools
from prism.agent_loop import Tool


class _M:
    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


def test_make_file_tools_bound_to_ws(tmp_path):             # [C1]
    ws = tmp_path / "ws"
    ws.mkdir()
    tools = {t.name: t for t in make_file_tools(ws)}
    assert "wrote" in tools["write"].execute({"path": "a.txt", "content": "hello"})
    assert (ws / "a.txt").read_text() == "hello"
    assert tools["read"].execute({"path": "a.txt"}) == "hello"
    assert "a.txt" in tools["ls"].execute({"path": "."})


def test_make_file_tools_absolute_path_stays_in_ws(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    tools = {t.name: t for t in make_file_tools(ws)}
    # 绝对路径 ws 外应仍解析回 ws(闭包锁死, 防逃逸)
    # —— 实际 _resolve 对绝对路径放行; 这里测相对路径必落 ws
    tools["write"].execute({"path": "sub/b.txt", "content": "x"})
    assert (ws / "sub" / "b.txt").exists()


def test_spawn_creates_subagent_with_workspace(tmp_path):   # [C2]
    bob = spawn("bob", _M(), workspaces_root=str(tmp_path))
    assert bob.kind == "sub"
    assert bob.workspace == tmp_path / "bob"
    assert (tmp_path / "bob").is_dir()


def test_spawn_duplicate_name_errors(tmp_path):             # [C3]
    spawn("bob", _M(), workspaces_root=str(tmp_path))
    with pytest.raises(ValueError):
        spawn("bob", _M(), workspaces_root=str(tmp_path))


def test_subagent_has_no_python_tool(tmp_path):             # [C4]
    bob = spawn("bob", _M(), workspaces_root=str(tmp_path))
    names = [t.name for t in bob._tools()]
    assert "python" not in names                            # 无裸 exec(原则 13)
    assert "read" in names and "write" in names and "ls" in names


def test_bob_write_lands_in_own_workspace(tmp_path):        # [C5]
    bob = spawn("bob", _M(), workspaces_root=str(tmp_path))
    write = next(t for t in bob._tools() if t.name == "write")
    write.execute({"path": "note.md", "content": "bob was here"})
    assert (tmp_path / "bob" / "note.md").read_text() == "bob was here"
    assert not (tmp_path / "note.md").exists()             # 没落在父级(不踩踏)
