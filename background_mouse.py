import threading
import time

import win32api
import win32con
import win32gui


class WindowMouseManager:
    """Send mouse messages directly to one window without moving the OS cursor."""

    def __init__(self, hwnd):
        self.hwnd = int(hwnd)
        self._lock = threading.RLock()

    def is_valid(self):
        return bool(self.hwnd and win32gui.IsWindow(self.hwnd))

    def _sender(self, use_send):
        return win32gui.SendMessage if use_send else win32gui.PostMessage

    def move(self, x, y, *, use_send=True):
        if not self.is_valid():
            return False
        lp = win32api.MAKELONG(int(x), int(y))
        with self._lock:
            self._sender(use_send)(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp)
        return True

    def click(
        self,
        x,
        y,
        *,
        double=False,
        use_send=True,
        clicks=None,
        hold=0.08,
        gap=0.08,
    ):
        if not self.is_valid():
            return False

        lp = win32api.MAKELONG(int(x), int(y))
        sender = self._sender(use_send)
        click_count = max(1, int(clicks if clicks is not None else (2 if double else 1)))

        with self._lock:
            sender(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp)
            time.sleep(0.03)
            for _ in range(click_count):
                sender(self.hwnd, win32con.WM_MOUSEMOVE, 0, lp)
                sender(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
                time.sleep(max(0.02, float(hold)))
                # The release message must not retain MK_LBUTTON. Some game UI
                # otherwise remains in hover/pressed state without committing.
                sender(self.hwnd, win32con.WM_LBUTTONUP, 0, lp)
                time.sleep(max(0.02, float(gap)))
        return True
