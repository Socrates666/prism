"""跨平台原始终端后端。

- Windows: Win32 Console API(ctypes) —— ReadConsoleInputW 拿结构化按键 + 尺寸事件;
  开 VT 输出, alt screen, 隐藏光标。主路径(本机环境)。
- POSIX: termios raw 模式 + stdin 字节流, 解析常见 ANSI 转义。尽力而为后备。

对外只暴露 :class:`Terminal`(上下文管理器) 与 :class:`Key`。
"""
from __future__ import annotations
import os
import sys
import threading
import queue
from dataclasses import dataclass

IS_WIN = sys.platform == "win32"


@dataclass
class Key:
    key: str    # 规范名: "enter"/"escape"/"left"/"ctrl+c"/"a"/"A"/"" …
    char: str   # 可打印字符, 控制键为 ""
    ctrl: bool = False
    alt: bool = False
    shift: bool = False

    def is_printable(self) -> bool:
        return self.char != "" and self.char.isprintable()


# ── Windows ───────────────────────────────────────────────────────────────
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    STD_INPUT = -10
    STD_OUTPUT = -11
    ENABLE_ECHO_INPUT = 0x0004
    ENABLE_LINE_INPUT = 0x0002
    ENABLE_PROCESSED_INPUT = 0x0001
    ENABLE_WINDOW_INPUT = 0x0008
    ENABLE_EXTENDED_FLAGS = 0x0080
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

    LEFT_CTRL_PRESSED = 0x0008
    RIGHT_CTRL_PRESSED = 0x0004
    LEFT_ALT_PRESSED = 0x0002
    RIGHT_ALT_PRESSED = 0x0001
    SHIFT_PRESSED = 0x0010

    _VK = {
        0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x1B: "escape",
        0x21: "pageup", 0x22: "pagedown", 0x23: "end", 0x24: "home",
        0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
        0x2E: "delete", 0x2D: "insert",
    }

    class _COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class _SmallRect(ctypes.Structure):
        _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                    ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

    class _CSBI(ctypes.Structure):
        _fields_ = [("dwSize", _COORD), ("dwCursorPosition", _COORD),
                    ("wAttributes", wintypes.WORD), ("srWindow", _SmallRect),
                    ("dwMaximumWindowSize", _COORD)]

    class _KeyEventRec(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class _Event(ctypes.Union):
        class _KeyEv(ctypes.Structure):
            _fields_ = [("EventType", wintypes.WORD), ("KeyEvent", _KeyEventRec)]
        class _WinEv(ctypes.Structure):
            _fields_ = [("EventType", wintypes.WORD), ("dwSize", _COORD)]
        _fields_ = [("KeyEvent", _KeyEv), ("WinEv", _WinEv)]

    KEY_EVENT_TYPE = 0x0001
    WINDOW_EVENT_TYPE = 0x0004


def _win_size() -> tuple[int, int]:
    h = _kernel32.GetStdHandle(STD_OUTPUT)
    info = _CSBI()
    if _kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(info)):
        w = info.srWindow.Right - info.srWindow.Left + 1
        hgt = info.srWindow.Bottom - info.srWindow.Top + 1
        return max(1, w), max(1, hgt)
    return 80, 24


def _win_translate(rec: "_KeyEventRec") -> Key | None:
    state = rec.dwControlKeyState
    ctrl = bool(state & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED))
    alt = bool(state & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED))
    shift = bool(state & SHIFT_PRESSED)
    code = rec.wVirtualKeyCode
    ch = rec.uChar
    name = _VK.get(code, "")
    if ctrl and ch and 1 <= ord(ch) < 32:
        letter = chr(ord(ch) + 96)        # \x03 → c
        return Key(key=f"ctrl+{letter}", char="", ctrl=True, alt=alt, shift=shift)
    if ctrl and code and 0x41 <= code <= 0x5A:   # A..Z
        return Key(key=f"ctrl+{chr(code).lower()}", char="", ctrl=True, alt=alt, shift=shift)
    if name:                                       # 方向/功能键
        return Key(key=name, char="", ctrl=ctrl, alt=alt, shift=shift)
    if ch:
        return Key(key=ch, char=ch, ctrl=ctrl, alt=alt, shift=shift)
    return None


class Terminal:
    """原始终端会话(上下文管理器)。线程安全: 输入在后台线程, 输出在主线程。"""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._in = self._out = None
        self._old_in = self._old_out = 0
        self._rows = self._cols = 0

    # ── 生命周期 ─────────────────────────────────────────────────────────
    def __enter__(self) -> "Terminal":
        if IS_WIN:
            self._setup_win()
        self._rows, self._cols = self.size()
        # alt screen + 隐藏光标 + 清屏 + 开启 bracketed paste(?2004)
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H\x1b[?2004h")
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        try:
            # 唤醒可能阻塞的 POSIX read
            if not IS_WIN:
                try:
                    sys.__stdin__.close()  # noqa
                except Exception:
                    pass
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=0.2)
        self.write("\x1b[?25h\x1b[?2004l\x1b[?1049l")
        if IS_WIN:
            self._teardown_win()
        else:
            self._teardown_posix()

    def _setup_win(self) -> None:
        self._in = _kernel32.GetStdHandle(STD_INPUT)
        self._out = _kernel32.GetStdHandle(STD_OUTPUT)
        mode = wintypes.DWORD()
        # 输出: 开 VT
        if _kernel32.GetConsoleMode(self._out, ctypes.byref(mode)):
            self._old_out = mode.value
            _kernel32.SetConsoleMode(self._out, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        # 输入: 关 echo/line/processed, 留 window(尺寸事件)
        if _kernel32.GetConsoleMode(self._in, ctypes.byref(mode)):
            self._old_in = mode.value
            new = (mode.value
                   & ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT | ENABLE_PROCESSED_INPUT))
            new |= ENABLE_WINDOW_INPUT | ENABLE_EXTENDED_FLAGS
            _kernel32.SetConsoleMode(self._in, new)

    def _teardown_win(self) -> None:
        if self._in is not None and self._old_in:
            _kernel32.SetConsoleMode(self._in, self._old_in)
        if self._out is not None and self._old_out:
            _kernel32.SetConsoleMode(self._out, self._old_out)

    # ── 尺寸 / 输出 ──────────────────────────────────────────────────────
    def size(self) -> tuple[int, int]:
        if IS_WIN:
            w, h = _win_size()
        else:
            import shutil
            sz = shutil.get_terminal_size((80, 24))
            w, h = sz.columns, sz.lines
        self._rows, self._cols = h, w
        return h, w

    def write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    # ── 输入 ─────────────────────────────────────────────────────────────
    def poll_key(self, timeout: float = 0.0) -> Key | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_loop(self) -> None:
        if IS_WIN:
            self._read_loop_win()
        else:
            self._read_loop_posix()

    def _read_loop_win(self) -> None:
        buf = (_Event * 16)()
        n = wintypes.DWORD(0)
        while not self._stop.is_set():
            ok = _kernel32.ReadConsoleInputW(self._in, buf, 16, ctypes.byref(n))
            if not ok:
                break
            for i in range(n.value):
                ev = buf[i]
                et = ev.KeyEvent.EventType
                if et == KEY_EVENT_TYPE:
                    rec = ev.KeyEvent.KeyEvent
                    if not rec.bKeyDown:
                        continue
                    k = _win_translate(rec)
                    if k:
                        self._q.put(k)
                elif et == WINDOW_EVENT_TYPE:
                    self._q.put(Key(key="__resize__", char=""))

    # ── POSIX 后备 ───────────────────────────────────────────────────────
    def _teardown_posix(self) -> None:
        try:
            import termios
            if hasattr(self, "_old_term"):
                termios.tcsetattr(0, termios.TCSADRAIN, self._old_term)
        except Exception:
            pass

    def _read_loop_posix(self) -> None:
        try:
            import termios, tty, select
            self._old_term = termios.tcgetattr(0)
            tty.setcbreak(0)
        except Exception:
            self._old_term = None
        buf = b""
        while not self._stop.is_set():
            try:
                import select
                r, _, _ = select.select([0], [], [], 0.2)
            except Exception:
                break
            if not r:
                continue
            try:
                data = os.read(0, 64)
            except OSError:
                break
            if not data:
                break
            for key in _parse_vt(data):
                self._q.put(key)

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cols(self) -> int:
        return self._cols


# ── POSIX ANSI 按键解析(后备) ─────────────────────────────────────────────
_VT_KEYS = {
    "\r": "enter", "\n": "enter", "\x7f": "backspace", "\t": "tab",
    "\x1b": "escape",
}
_VT_CSI = {
    "A": "up", "B": "down", "C": "right", "D": "left",
    "H": "home", "F": "end", "5~": "pageup", "6~": "pagedown",
    "3~": "delete", "2~": "insert",
}


# ponytail: 跨 read chunk 的 bracketed paste 状态用模块级 dict。
# POSIX 单读线程单调用者(_read_loop_posix), 无并发; 多终端实例并存时再改成 per-Terminal 解析器。
# Windows 路径经 ReadConsoleInputW 拿结构化事件, 不走 VT 解析, 故 paste 在 Win 上暂不生效(TODO)。
_PASTE = {"active": False, "buf": ""}


def _parse_vt(data: bytes) -> list[Key]:
    out: list[Key] = []
    text = data.decode("utf-8", "replace")
    i = 0
    while i < len(text):
        # bracketed paste 结束标记: 把累积内容整段产出一个 __paste__ key(段内 \r\n 不变 enter)
        if text.startswith("\x1b[201~", i):
            if _PASTE["active"]:
                out.append(Key(key="__paste__", char=_PASTE["buf"]))
                _PASTE["active"] = False
                _PASTE["buf"] = ""
            i += len("\x1b[201~")
            continue
        # 进入 paste: 后续字节原样累积, 不逐字符解释(嵌套 start 视为重开, 丢弃旧 buf)
        if text.startswith("\x1b[200~", i):
            _PASTE["active"] = True
            _PASTE["buf"] = ""
            i += len("\x1b[200~")
            continue
        if _PASTE["active"]:
            _PASTE["buf"] += text[i]
            i += 1
            continue
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ~":
                j += 1
            seq = text[i + 2:j + 1] if j < len(text) else text[i + 2:]
            name = _VT_CSI.get(seq, "")
            # 末字母映射
            if not name and seq and seq[-1] in _VT_CSI:
                name = _VT_CSI[seq[-1]]
            # 修饰参数: \x1b[1;5C → params[1]=5, mod=int-1 按位 1=shift 2=alt 4=ctrl
            shift = alt = ctrl = False
            params = seq[:-1].split(";") if seq else []
            if len(params) > 1 and params[1].isdigit():
                mod = int(params[1]) - 1
                shift, alt, ctrl = bool(mod & 1), bool(mod & 2), bool(mod & 4)
            out.append(Key(key=name or f"csi_{seq}", char="",
                           shift=shift, alt=alt, ctrl=ctrl))
            i = j + 1
        elif ch == "\x1b":
            if i + 1 < len(text) and text[i + 1] == "\r":
                # \x1b\r = 部分终端的 Shift+Enter(须在 Alt 合并前拦下, 拆开会先误中断再误提交)
                out.append(Key(key="enter", char="", shift=True))
                i += 2
            elif i + 1 < len(text) and text[i + 1].isprintable():
                # \x1b+可打印字符 = Alt+X, 合并成单 key(多余 escape 会误触发 agent 中断)
                out.append(Key(key=text[i + 1], char=text[i + 1], alt=True))
                i += 2
            else:
                out.append(Key(key="escape", char=""))
                i += 1
        elif ch == "\r":
            out.append(Key(key="enter", char=""))
            i += 1
        elif ch == "\n":
            # 0x0A=Ctrl+J: 不当 enter, 否则非 bracketed 终端多行粘贴兜底会逐行提交
            out.append(Key(key="ctrl+j", char=""))
            i += 1
        elif ch == "\t":
            out.append(Key(key="tab", char=""))
            i += 1
        elif ch == "\x7f":
            out.append(Key(key="backspace", char=""))
            i += 1
        else:
            out.append(Key(key=ch, char=ch))
            i += 1
    return out
