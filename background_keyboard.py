import threading
import time

import win32con
import win32gui


VK_MAP = {
    "esc": 0x1B, "enter": 0x0D, "space": 0x20, "backspace": 0x08, "tab": 0x09,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5, "capslock": 0x14,
    **{chr(code).lower(): code for code in range(0x41, 0x5B)},
    **{str(number): 0x30 + number for number in range(10)},
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "pageup": 0x21, "pagedown": 0x22, "home": 0x24, "end": 0x23,
    "insert": 0x2D, "delete": 0x2E,
}


SCAN_MAP = {
    "esc": (0x01, False), "enter": (0x1C, False), "space": (0x39, False),
    "backspace": (0x0E, False), "tab": (0x0F, False),
    "lshift": (0x2A, False), "rshift": (0x36, False),
    "lctrl": (0x1D, False), "rctrl": (0x1D, True),
    "lalt": (0x38, False), "ralt": (0x38, True), "capslock": (0x3A, False),
    "a": (0x1E, False), "b": (0x30, False), "c": (0x2E, False),
    "d": (0x20, False), "e": (0x12, False), "f": (0x21, False),
    "g": (0x22, False), "h": (0x23, False), "i": (0x17, False),
    "j": (0x24, False), "k": (0x25, False), "l": (0x26, False),
    "m": (0x32, False), "n": (0x31, False), "o": (0x18, False),
    "p": (0x19, False), "q": (0x10, False), "r": (0x13, False),
    "s": (0x1F, False), "t": (0x14, False), "u": (0x16, False),
    "v": (0x2F, False), "w": (0x11, False), "x": (0x2D, False),
    "y": (0x15, False), "z": (0x2C, False),
    "1": (0x02, False), "2": (0x03, False), "3": (0x04, False),
    "4": (0x05, False), "5": (0x06, False), "6": (0x07, False),
    "7": (0x08, False), "8": (0x09, False), "9": (0x0A, False),
    "0": (0x0B, False),
    "up": (0x48, True), "down": (0x50, True),
    "left": (0x4B, True), "right": (0x4D, True),
    "pageup": (0x49, True), "pagedown": (0x51, True),
    "home": (0x47, True), "end": (0x4F, True),
    "insert": (0x52, True), "delete": (0x53, True),
}


def _key_lparam(scan, extended, repeat, previous, transition):
    value = int(repeat) & 0xFFFF
    value |= (int(scan) & 0xFF) << 16
    if extended:
        value |= 1 << 24
    if previous:
        value |= 1 << 30
    if transition:
        value |= 1 << 31
    return value


class WindowKeyboardManager:
    """Send keyboard messages to a game HWND without owning foreground focus."""

    def __init__(self, hwnd):
        self.hwnd = int(hwnd)
        self._pressed = set()
        self._repeat_counts = {}
        self._running = False
        self._thread = None
        self._lock = threading.RLock()

    def is_valid(self):
        return bool(self.hwnd and win32gui.IsWindow(self.hwnd))

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._repeat_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.release_all()
        self._running = False

    def key_down(self, key):
        key = str(key).lower()
        with self._lock:
            self._pressed.add(key)
            self._send_key(key, down=True, repeat=False)

    def key_up(self, key):
        key = str(key).lower()
        with self._lock:
            self._pressed.discard(key)
            self._repeat_counts.pop(key, None)
            self._send_key(key, down=False)

    def press(self, key, delay=0.08, use_send=False):
        key = str(key).lower()
        with self._lock:
            self._send_key(key, down=True, repeat=False, send_char=True, use_send=use_send)
            time.sleep(max(0.02, float(delay)))
            self._send_key(key, down=False, use_send=use_send)
        time.sleep(0.02)

    def release_all(self):
        with self._lock:
            for key in list(self._pressed):
                self._send_key(key, down=False)
            self._pressed.clear()
            self._repeat_counts.clear()

    def _send_key(self, key, *, down, repeat=False, send_char=False, use_send=False):
        if not self.is_valid():
            return False
        vk = VK_MAP.get(key)
        if vk is None:
            return False
        scan, extended = SCAN_MAP.get(key, (0, False))
        sender = win32gui.SendMessage if use_send else win32gui.PostMessage
        if down:
            if repeat:
                count = min(self._repeat_counts.get(key, 0) + 1, 0xFFFF)
                self._repeat_counts[key] = count
                lparam = _key_lparam(scan, extended, count, True, False)
            else:
                lparam = _key_lparam(scan, extended, 1, False, False)
            sender(self.hwnd, win32con.WM_KEYDOWN, vk, lparam)
            if send_char and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
                sender(self.hwnd, win32con.WM_CHAR, vk, lparam)
        else:
            lparam = _key_lparam(scan, extended, 1, True, True)
            sender(self.hwnd, win32con.WM_KEYUP, vk, lparam)
        return True

    def _repeat_loop(self):
        while self._running:
            with self._lock:
                for key in list(self._pressed):
                    self._send_key(key, down=True, repeat=True)
            time.sleep(0.05)
