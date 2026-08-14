"""REQ-G4 回归: 文案中英混杂清零 + banner 五原色/字母画不复活 + 结果截断保尾部。"""
import os

_SRC = open(os.path.join(os.path.dirname(__file__), "..", "prism", "shell.py"),
            encoding="utf-8").read()


def test_shell_copy_is_chinese_and_banner_hex_gone():
    for en in ("Refracting", "more lines", "steer →"):
        assert en not in _SRC, f"{en} 残留"
    for cn in ("折射中", "错误：", "还有", "。可用：", "（已降级）", "（重启生效）", "（最近在上）："):
        assert cn in _SRC, f"{cn} 缺失"
    for hex_ in ("ff1744", "ffd000", "00ff7b", "00d4ff", "c850ff"):
        assert hex_ not in _SRC, f"spectrum {hex_} 残留"
    assert "█" not in _SRC, "字母画残留"


def test_fmt_result_keeps_head_and_tail():
    from prism.shell import _fmt_result
    out = _fmt_result("\n".join(f"L{i:02d}" for i in range(20)))
    assert "L00" in out and "L19" in out, out          # 头尾都在(错误/汇总在尾部)
    assert "还有" in out, out
    out2 = _fmt_result("\n".join(["x" * 60 for _ in range(6)]))
    assert "还有" in out2, out2                        # 计数提示不被字符上限吞掉
