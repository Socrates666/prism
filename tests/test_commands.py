"""slash 指令(ext/commands/)测试。"""
import pytest
from prism.commands import load_commands
from prism.agent import Agent


class FakeModel:
    model = "fake"
    thinking_level = None

    def chat_stream(self, m, tools=None):
        yield {"type": "done", "tool_calls": []}


def _agent():
    return Agent("t", model=FakeModel(), actor=False)


def _ctx(agent, commands=None):
    return {"agent": agent, "app": None, "write": lambda m: None, "commands": commands or {}}


def test_load_commands_from_tmp(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "hi.py").write_text(
        "NAME='hi'\nDESC='x'\ndef run(a,c): return 'hi-back'\n")
    cmds = load_commands(tmp_path)
    assert "hi" in cmds and cmds["hi"].run("", {}) == "hi-back"


def test_load_commands_skips_bad(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "good.py").write_text("NAME='g'\ndef run(a,c): return 'g'\n")
    (tmp_path / "commands" / "bad.py").write_text("raise RuntimeError('x')\n")
    errs = []
    cmds = load_commands(tmp_path, emit=lambda e: errs.append(e))
    assert "g" in cmds and "bad" not in cmds
    assert len(errs) == 1


def test_load_commands_loads_real_ext():
    cmds = load_commands("ext")
    assert {"model", "thinking", "skill", "goal", "help"} <= set(cmds)


def test_cmd_model_switches():
    a = _agent()
    r = load_commands("ext")["model"].run("glm-4.7", _ctx(a))
    assert "切换" in r and a.model.model == "glm-4.7"


def test_cmd_model_view_current():
    a = _agent()
    r = load_commands("ext")["model"].run("", _ctx(a))
    assert "fake" in r


def test_cmd_thinking_off_syncs_to_model():
    a = _agent()
    load_commands("ext")["thinking"].run("off", _ctx(a))
    assert a.thinking_level == "off"
    assert a.model.thinking_level == "off"                 # 同步到 model


def test_cmd_goal_injects_into_system_prompt():
    a = _agent()
    load_commands("ext")["goal"].run("写完所有测试", _ctx(a))
    assert "写完所有测试" in a.system_prompt and "Goal" in a.system_prompt


def test_cmd_skill_loads_md_into_system_prompt():
    a = _agent()
    r = load_commands("ext")["skill"].run("code-review", _ctx(a))
    assert "注入" in r
    assert "code-review" in a.system_prompt and "必须修复" in a.system_prompt


def test_cmd_skill_missing_returns_error():
    a = _agent()
    r = load_commands("ext")["skill"].run("nope", _ctx(a))
    assert "不存在" in r


def test_cmd_help_lists_commands():
    cmds = load_commands("ext")
    r = cmds["help"].run("", _ctx(_agent(), commands=cmds))
    assert "/model" in r and "/thinking" in r
