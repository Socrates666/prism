"""SystemPrompt 结构化段测试(阶段 13)。"""
from prism.prompt import SystemPrompt


def test_render_filled_sections_with_titles():
    p = SystemPrompt()
    p.role = "你是 alice"
    p.instructions = "输入即授权"
    p.guidelines = "简洁直接"
    r = p.render()
    assert "## 角色" in r and "你是 alice" in r
    assert "## 指令" in r and "输入即授权" in r
    assert "## 行为准则" in r and "简洁直接" in r


def test_render_skips_empty_sections():
    p = SystemPrompt()
    p.role = "x"
    r = p.render()
    assert "## 角色" in r
    assert "## 指令" not in r                 # 空段不渲染
    assert "## 环境" not in r


def test_override_replaces_all():
    p = SystemPrompt()
    p.role = "x"
    p.add_extra("y")
    p.set_override("ONLY THIS")
    assert p.render() == "ONLY THIS"


def test_goal_into_dedicated_section():
    p = SystemPrompt()
    p.role = "x"
    p.set_goal("写完所有测试")
    r = p.render()
    assert "## 当前目标" in r and "写完所有测试" in r


def test_skill_into_dedicated_section():
    p = SystemPrompt()
    p.role = "x"
    p.add_skill("code-review", "找bug并分级")
    r = p.render()
    assert "## Skills" in r and "code-review" in r and "找bug并分级" in r


def test_extra_appended():
    p = SystemPrompt()
    p.role = "x"
    p.add_extra("额外A")
    p.add_extra("额外B")
    r = p.render()
    assert "额外A" in r and "额外B" in r


def test_render_empty_when_nothing_set():
    assert SystemPrompt().render() == ""
