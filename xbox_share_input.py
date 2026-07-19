"""Xbox system share-code dialog input for the standalone Xbox build."""

import ctypes
import time
from ctypes import wintypes

import win32gui


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_SHIFT = 0x10

XBOX_TITLE_HINTS = (
    "游戏用户界面",
    "共享代码",
    "game ui",
    "gaming ui",
    "share code",
)


class _KeyBdInput(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _HardwareInput(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput))


class _Input(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _InputUnion))


def _keyboard_input(vk, key_up=False):
    scan = ctypes.windll.user32.MapVirtualKeyW(int(vk), 0)
    flags = KEYEVENTF_KEYUP if key_up else 0
    extra = ctypes.c_ulong(0)
    union = _InputUnion()
    union.ki = _KeyBdInput(
        int(vk),
        int(scan),
        int(flags),
        0,
        ctypes.pointer(extra),
    )
    return _Input(INPUT_KEYBOARD, union)


def _send_inputs(*events):
    if not events:
        return True
    array_type = _Input * len(events)
    sent = ctypes.windll.user32.SendInput(
        len(events),
        array_type(*events),
        ctypes.sizeof(_Input),
    )
    return int(sent) == len(events)


def _press_vk(vk, delay=0.05):
    if not _send_inputs(_keyboard_input(vk)):
        return False
    time.sleep(max(0.02, float(delay)))
    return _send_inputs(_keyboard_input(vk, key_up=True))


def _clear_text_field():
    # Release modifiers first in case the test was started after a manual stop.
    _send_inputs(_keyboard_input(VK_SHIFT, key_up=True), _keyboard_input(VK_CONTROL, key_up=True))
    if not _send_inputs(_keyboard_input(VK_CONTROL), _keyboard_input(ord("A"))):
        return False
    time.sleep(0.05)
    if not _send_inputs(
        _keyboard_input(ord("A"), key_up=True),
        _keyboard_input(VK_CONTROL, key_up=True),
    ):
        return False
    time.sleep(0.05)
    return _press_vk(VK_BACK)


def _type_digits(code_text, interval=0.10):
    for char in str(code_text):
        if char < "0" or char > "9":
            continue
        if not _press_vk(ord(char), delay=0.05):
            return False
        time.sleep(max(0.02, float(interval)))
    return True


def _window_details(hwnd):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return {"hwnd": 0, "title": "", "class": "", "visible": False}
    try:
        title = win32gui.GetWindowText(hwnd) or ""
    except Exception:
        title = ""
    try:
        class_name = win32gui.GetClassName(hwnd) or ""
    except Exception:
        class_name = ""
    try:
        visible = bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        visible = False
    return {
        "hwnd": int(hwnd),
        "title": title,
        "class": class_name,
        "visible": visible,
    }


def _is_xbox_dialog(details, game_hwnd):
    if not details["visible"] or details["hwnd"] == int(game_hwnd or 0):
        return False
    normalized = details["title"].strip().lower()
    return any(hint in normalized for hint in XBOX_TITLE_HINTS)


def _find_xbox_dialog(game_hwnd):
    foreground = win32gui.GetForegroundWindow()
    foreground_details = _window_details(foreground)
    if _is_xbox_dialog(foreground_details, game_hwnd):
        return foreground_details

    candidates = []

    def callback(hwnd, _):
        details = _window_details(hwnd)
        if _is_xbox_dialog(details, game_hwnd):
            candidates.append(details)
        return True

    win32gui.EnumWindows(callback, None)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item["hwnd"] != foreground, len(item["title"])))
    return candidates[0]


def _dialog_is_open(details):
    if not details:
        return False
    current = _window_details(details["hwnd"])
    normalized = current["title"].strip().lower()
    return current["visible"] and any(hint in normalized for hint in XBOX_TITLE_HINTS)


def _wait_dialog_closed(details, timeout):
    deadline = time.time() + max(0.5, float(timeout))
    while time.time() < deadline:
        if not _dialog_is_open(details):
            return True
        time.sleep(0.10)
    return not _dialog_is_open(details)


def _foreground_summary():
    details = _window_details(win32gui.GetForegroundWindow())
    return (
        f"hwnd=0x{details['hwnd']:X} title={details['title']!r} "
        f"class={details['class']!r}"
    )


def enter_share_code_xbox(bot, code_text, *, dialog_timeout=10.0):
    """Type into the Xbox system dialog and submit without changing Steam code."""
    deadline = time.time() + max(1.0, float(dialog_timeout))
    dialog = None
    last_summary = ""

    while bot.is_running and time.time() < deadline:
        dialog = _find_xbox_dialog(getattr(bot, "game_hwnd", None))
        if dialog:
            break
        summary = _foreground_summary()
        if summary != last_summary:
            bot.log(f"[XboxInput] 等待系统共享代码窗口：{summary}", level="DEBUG")
            last_summary = summary
        time.sleep(0.20)

    if not bot.is_running:
        return False
    if not dialog:
        bot.log(
            "[XboxInput] 未检测到标题包含“游戏用户界面/共享代码”的 Xbox 系统窗口。",
            level="WARN",
        )
        return False

    bot.log(
        f"[XboxInput] 已连接系统输入窗口：hwnd=0x{dialog['hwnd']:X} "
        f"title={dialog['title']!r} class={dialog['class']!r}"
    )
    try:
        win32gui.SetForegroundWindow(dialog["hwnd"])
    except Exception as exc:
        bot.log(f"[XboxInput] 激活系统输入窗口失败，将尝试沿用当前焦点：{exc}", level="WARN")
    time.sleep(0.25)

    if not _clear_text_field():
        bot.log("[XboxInput] 清空分享码输入框失败。", level="WARN")
        return False
    if not _type_digits(code_text):
        bot.log("[XboxInput] 系统级数字输入未完整发送。", level="WARN")
        return False

    bot.log(f"[XboxInput] 已向系统窗口输入 {len(code_text)} 位分享码，正在确认。")
    time.sleep(0.30)
    if not _press_vk(VK_RETURN, delay=0.08):
        bot.log("[XboxInput] 第一次确认键发送失败。", level="WARN")
        return False

    if _wait_dialog_closed(dialog, 3.0):
        bot.log("[XboxInput] 系统共享代码窗口已关闭，输入提交成功。")
        time.sleep(0.50)
        return True

    bot.log("[XboxInput] Enter 后窗口仍存在，尝试 Tab 定位“确定”后再次确认。", level="WARN")
    if not _press_vk(VK_TAB, delay=0.08) or not _press_vk(VK_RETURN, delay=0.08):
        return False
    if _wait_dialog_closed(dialog, 3.0):
        bot.log("[XboxInput] 备用确认成功，系统共享代码窗口已关闭。")
        time.sleep(0.50)
        return True

    bot.log("[XboxInput] 分享码已发送，但系统窗口未关闭；已停止后续盲目按键。", level="WARN")
    return False
