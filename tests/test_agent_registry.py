"""测试 agent 注册表、文件锁、steer 插队。"""
import os
import json
import shutil
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ── agent_registry ──────────────────────────────────────

def test_load_agent_configs_finds_all():
    """ext/agents/*/agent.yaml 都被加载。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    names = [c["name"] for c in configs]
    assert "Prism" in names
    assert "coder" in names
    assert "skill-creator" in names


def test_main_agent_sorted_first():
    """main agent 排在 sub 前。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    assert configs[0]["kind"] == "main"


def test_prism_has_prompt_sections():
    """prism 配置含 prompt_sections。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    prism = next(c for c in configs if c["name"] == "Prism")
    assert "prompt_sections" in prism
    assert "role" in prism["prompt_sections"]
    assert "capabilities" in prism["prompt_sections"]


def test_coder_has_tools_list():
    """coder 配置用 tools 列表声明工具。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    coder = next(c for c in configs if c["name"] == "coder")
    tools = coder.get("tools", [])
    assert "edit_file" in tools
    assert "write_file" in tools
    assert "read_file" in tools


def test_skill_creator_has_skills():
    """skill-creator 配置声明加载 skill-creator skill。"""
    from prism.agent_registry import load_agent_configs
    configs = load_agent_configs()
    sc = next(c for c in configs if c["name"] == "skill-creator")
    assert "skill-creator" in sc.get("skills", [])


def test_apply_prompt_from_config():
    """_apply_prompt_from_config 正确设置 prompt 各段。"""
    from prism.agent_registry import _apply_prompt_from_config
    from prism.agent import Agent

    class FakeModel:
        def chat_stream(self, m, t=None): yield {"type": "done", "tool_calls": []}

    a = Agent("test", model=FakeModel())
    cfg = {
        "prompt_sections": {
            "role": "你是 {name}, 测试 agent。",
            "environment": "测试环境。",
            "capabilities": "测试能力。",
            "instructions": "测试指令。",
            "guidelines": "测试准则。",
        },
        "extra_prompt": "额外指令。",
    }
    _apply_prompt_from_config(a, cfg)
    sp = a.system_prompt
    assert "test" in sp  # {name} 被替换
    assert "测试环境" in sp
    assert "测试能力" in sp
    assert "额外指令" in sp


def test_save_agent_config_writes_yaml(tmp_path):
    """save_agent_config 写入 YAML 并能被 load 读回。"""
    from prism.agent_registry import save_agent_config, load_agent_config
    test_dir = tmp_path / "test-agent"
    test_dir.mkdir()
    cfg = {"name": "test-agent", "kind": "sub", "tools": ["read", "write"]}
    save_agent_config("test-agent", cfg, agents_dir=str(tmp_path))
    loaded = load_agent_config(tmp_path / "test-agent")
    assert loaded["name"] == "test-agent"
    assert "read" in loaded["tools"]


# ── 文件锁 ──────────────────────────────────────────────

def test_acquire_lock_succeeds():
    from prism.spawn import acquire_lock, release_lock, _file_locks
    _file_locks.clear()
    ok, holder = acquire_lock("test_lock.py", "coder")
    assert ok is True
    assert holder == ""


def test_acquire_lock_blocks_others():
    from prism.spawn import acquire_lock, release_lock, _file_locks
    _file_locks.clear()
    acquire_lock("shared.py", "coder")
    ok, holder = acquire_lock("shared.py", "other")
    assert ok is False
    assert holder == "coder"


def test_acquire_lock_idempotent():
    from prism.spawn import acquire_lock, release_lock, _file_locks
    _file_locks.clear()
    acquire_lock("idem.py", "coder")
    ok, holder = acquire_lock("idem.py", "coder")  # same agent
    assert ok is True


def test_release_lock_allows_reacquire():
    from prism.spawn import acquire_lock, release_lock, _file_locks
    _file_locks.clear()
    acquire_lock("release.py", "coder")
    release_lock("release.py", "coder")
    ok, _ = acquire_lock("release.py", "other")
    assert ok is True


def test_release_only_own_lock():
    from prism.spawn import acquire_lock, release_lock, _file_locks
    _file_locks.clear()
    acquire_lock("own.py", "coder")
    release_lock("own.py", "other")  # other tries to release coder's lock
    ok, holder = acquire_lock("own.py", "other")
    assert ok is False  # still locked by coder
    _file_locks.clear()


# ── steer_check ─────────────────────────────────────────

def test_check_steer_empty_inbox():
    from prism.agent import Agent

    class FakeModel:
        def chat_stream(self, m, t=None): yield {"type": "done", "tool_calls": []}

    a = Agent("test", model=FakeModel(), actor=False)
    assert a._check_steer() is False


def test_check_steer_with_steer_message():
    from prism.agent import Agent

    class FakeModel:
        def chat_stream(self, m, t=None): yield {"type": "done", "tool_calls": []}

    a = Agent("test", model=FakeModel(), actor=False)
    a.inject({"type": "run", "input": "urgent"}, kind="steer")
    assert a._check_steer() is True


def test_check_steer_with_followup_only():
    from prism.agent import Agent

    class FakeModel:
        def chat_stream(self, m, t=None): yield {"type": "done", "tool_calls": []}

    a = Agent("test", model=FakeModel(), actor=False)
    a.inject({"type": "run", "input": "normal"}, kind="followUp")
    assert a._check_steer() is False


# ── steer_check in agent_loop ───────────────────────────

def test_steer_check_interrupts_loop():
    """steer_check=True 时 agent_loop 在 turn 开始时中断。"""
    from prism.agent_loop import run_agent_loop, Tool
    from prism.patch import PatchRegistry

    class SlowModel:
        def chat_stream(self, messages, tools=None):
            yield {"type": "delta", "text": "thinking..."}
            yield {"type": "done", "tool_calls": []}

    events = []
    steer_flag = [True]  # 模拟有 steer

    msgs = run_agent_loop(
        SlowModel(), "system", "go", [],
        lambda e: events.append(e["type"]),
        steer_check=lambda: steer_flag[0],
        max_turns=10,
    )
    assert "steer_interrupt" in events
    assert "turn_start" not in events  # 在 turn_start 之前中断
