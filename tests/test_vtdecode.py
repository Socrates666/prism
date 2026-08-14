"""REQ-G2 验收: POSIX VT 解码 —— 修饰键 / Alt 合并 / Shift+Enter / Ctrl+J。

固化 CHECKS [V1]-[V3]: CSI 修饰参数不再丢; \x1b+字符合并为 Alt 不再产多余 escape;
\x1b\r 识别为 Shift+Enter; \n(0x0A) 不再误当 enter; bracketed paste(W1)不回归。
"""
from prism.tui.terminal import _PASTE, _parse_vt


def setup_function(_):
    # _PASTE 是跨调用模块级状态, 每个用例前复位避免串扰
    _PASTE["active"] = False
    _PASTE["buf"] = ""


def test_v1_csi_modifier_params():
    # [V1] \x1b[1;2A=Shift+Up, \x1b[1;5C=Ctrl+Right, \x1b[1;3D=Alt+Left
    k = _parse_vt(b"\x1b[1;2A")[0]
    assert (k.key, k.shift) == ("up", True), (k.key, k.shift)
    k2 = _parse_vt(b"\x1b[1;5C")[0]
    assert (k2.key, k2.ctrl) == ("right", True), (k2.key, k2.ctrl)
    k3 = _parse_vt(b"\x1b[1;3D")[0]
    assert (k3.key, k3.alt) == ("left", True), (k3.key, k3.alt)
    # 无参数序列不得凭空带修饰
    k4 = _parse_vt(b"\x1b[A")[0]
    assert (k4.key, k4.shift, k4.alt, k4.ctrl) == ("up", False, False, False)


def test_v2_alt_merge_no_stray_escape():
    # [V2] \x1b+可打印字符 = 单个 Alt+X; 孤立 \x1b(chunk 末尾)仍是 escape
    ks = _parse_vt(b"\x1bx")
    assert len(ks) == 1 and ks[0].key == "x" and ks[0].alt and ks[0].char == "x", \
        [(k.key, k.alt) for k in ks]
    ks2 = _parse_vt(b"\x1b")
    assert len(ks2) == 1 and ks2[0].key == "escape", [k.key for k in ks2]


def test_v3_shift_enter_and_ctrl_j():
    # [V3] \x1b\r=Shift+Enter 单 key(不拆成 escape+enter)
    ks = _parse_vt(b"\x1b\r")
    assert len(ks) == 1 and ks[0].key == "enter" and ks[0].shift, \
        [(k.key, k.shift) for k in ks]
    # \n=Ctrl+J, 不再产 enter; \r 保持 enter
    ks2 = _parse_vt(b"abc\n")
    keys = [k.key for k in ks2]
    assert "ctrl+j" in keys and "enter" not in keys, keys
    ks3 = _parse_vt(b"abc\r")
    assert [k.key for k in ks3][-1] == "enter", [k.key for k in ks3]
    # W1 bracketed paste 回归: 段内 \r 原样保留不产 enter
    ks4 = _parse_vt(b"abc\x1b[200~line1\rline2\r\x1b[201~def")
    pastes = [k for k in ks4 if k.key == "__paste__"]
    assert len(pastes) == 1 and "line1\rline2" in pastes[0].char, \
        [(k.key, k.char[:20]) for k in ks4]
