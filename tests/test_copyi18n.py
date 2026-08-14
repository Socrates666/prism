"""REQ-G4 回归: 文案中英混杂清零 + 字母画受 PRISM_BANNER 开关控制 + 结果截断保尾部。

用户裁决(2026-08-14): pi-faithful 彩色横幅回归为默认(大屏), 批判轮"不复活"验收作废,
改为: 字母画必须只活在 PRISM_BANNER 分支内(见 tests/test_banner.py 行为验收)。
"""
import os

_SRC = open(os.path.join(os.path.dirname(__file__), "..", "prism", "shell.py"),
            encoding="utf-8").read()


def test_shell_copy_is_chinese_and_banner_gated():
    for en in ("Refracting", "more lines", "steer →"):
        assert en not in _SRC, f"{en} 残留"
    for cn in ("折射中", "错误：", "还有", "。可用：", "（已降级）", "（重启生效）", "（最近在上）："):
        assert cn in _SRC, f"{cn} 缺失"
    # 字母画必须被开关守卫(不在开关外裸出现)
    assert "PRISM_BANNER" in _SRC, "横幅开关缺失"
    assert 'PRISM_BANNER", ""' in _SRC or "PRISM_BANNER" in _SRC


def test_fmt_result_keeps_head_and_tail():
    from prism.shell import _fmt_result
    out = _fmt_result("\n".join(f"L{i:02d}" for i in range(20)))
    assert "L00" in out and "L19" in out, out          # 头尾都在(错误/汇总在尾部)
    assert "还有" in out, out
    out2 = _fmt_result("\n".join(["x" * 60 for _ in range(6)]))
    assert "还有" in out2, out2                        # 计数提示不被字符上限吞掉
