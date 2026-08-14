"""_load_env 多路径加载验收: 包根 .env + cwd/.env 兜底(用户裁决: 模型配置不随 clone 丢失)。

固化:
  [E1] 指定路径的 .env 被读入 os.environ(不覆盖已有)
  [E2] 文件不存在/注释空行 安全跳过
"""
import os


def _load_env():
    # 延迟 import 触发副作用可控(直接拿函数测, 不重跑 import 时的包根+cwd 注入)
    import importlib
    import prism
    importlib.reload(prism)
    return prism._load_env


def test_e1_env_file_loaded_no_override(tmp_path, monkeypatch):
    load = _load_env()
    f = tmp_path / ".env"
    f.write_text("PRISM_TEST_MODEL=glm-4.6\n"
                 "# 注释行\n"
                 "\n"
                 "PRISM_TEST_EXISTING=from_env\n", encoding="utf-8")
    monkeypatch.delenv("PRISM_TEST_MODEL", raising=False)
    monkeypatch.setenv("PRISM_TEST_EXISTING", "from_os")   # 已有 → 不覆盖
    load([f])
    assert os.environ["PRISM_TEST_MODEL"] == "glm-4.6"
    assert os.environ["PRISM_TEST_EXISTING"] == "from_os"


def test_e2_missing_file_skipped(tmp_path):
    load = _load_env()
    load([tmp_path / "nope.env", tmp_path / "also_nope.env"])   # 不崩即过
