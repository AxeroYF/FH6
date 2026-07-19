"""Transparent mouse isolation overlay for the game client area."""

import os
import threading
import time

import win32api
import win32con
import win32gui


class MouseIsolationOverlay:
    """Consume physical mouse input above a game while leaving it visible."""

    def __init__(self, game_hwnd, *, on_dismiss=None):
        self.game_hwnd = int(game_hwnd)
        self.on_dismiss = on_dismiss
        self._thread = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._overlay_hwnd = None
        self._startup_error = None
        self._dismissed = False
        self._class_name = f"FH6MouseIsolation_{os.getpid()}_{id(self)}"
        self._wndproc_ref = None

    def is_active(self):
        hwnd = self._overlay_hwnd
        return bool(
            not self._dismissed
            and hwnd
            and win32gui.IsWindow(hwnd)
            and win32gui.IsWindowVisible(hwnd)
        )

    def start(self, timeout=1.5):
        if not win32gui.IsWindow(self.game_hwnd):
            return False
        if self._thread is not None and self._thread.is_alive():
            return self.is_active()

        self._stop_event.clear()
        self._ready_event.clear()
        self._startup_error = None
        self._dismissed = False
        self._thread = threading.Thread(
            target=self._run,
            name="FH6MouseIsolation",
            daemon=True,
        )
        self._thread.start()
        self._ready_event.wait(max(0.1, float(timeout)))
        return self.is_active()

    def stop(self):
        self._stop_event.set()
        hwnd = self._overlay_hwnd
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _game_client_bounds(self):
        if not win32gui.IsWindow(self.game_hwnd):
            return None
        left, top, right, bottom = win32gui.GetClientRect(self.game_hwnd)
        x, y = win32gui.ClientToScreen(self.game_hwnd, (left, top))
        width = int(right - left)
        height = int(bottom - top)
        if width <= 0 or height <= 0:
            return None
        return int(x), int(y), width, height

    def _dismiss_from_click(self):
        if self._dismissed:
            return
        self._dismissed = True
        hwnd = self._overlay_hwnd
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            except Exception:
                pass
        callback = self.on_dismiss
        if callable(callback):
            try:
                callback()
            except Exception:
                pass
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_NCHITTEST:
            return win32con.HTCLIENT
        if message == win32con.WM_MOUSEACTIVATE:
            # Deliver the click to this window without activating it. The
            # following LBUTTONDOWN is used only to dismiss the isolation.
            return win32con.MA_NOACTIVATE
        if message == win32con.WM_LBUTTONDOWN:
            self._dismiss_from_click()
            return 0
        if message in (
            win32con.WM_MOUSEMOVE,
            win32con.WM_LBUTTONUP,
            win32con.WM_RBUTTONDOWN,
            win32con.WM_RBUTTONUP,
            win32con.WM_MBUTTONDOWN,
            win32con.WM_MBUTTONUP,
            win32con.WM_MOUSEWHEEL,
        ):
            return 0
        if message == win32con.WM_SETCURSOR:
            win32gui.SetCursor(win32gui.LoadCursor(0, win32con.IDC_ARROW))
            return 1
        if message == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0
        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def _run(self):
        instance = win32api.GetModuleHandle(None)
        registered = False
        try:
            bounds = self._game_client_bounds()
            if bounds is None:
                raise RuntimeError("游戏客户区不可用")

            window_class = win32gui.WNDCLASS()
            window_class.hInstance = instance
            window_class.lpszClassName = self._class_name
            window_class.lpfnWndProc = self._wndproc
            window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            window_class.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)
            win32gui.RegisterClass(window_class)
            registered = True

            x, y, width, height = bounds
            ex_style = (
                win32con.WS_EX_LAYERED
                | win32con.WS_EX_NOACTIVATE
                | win32con.WS_EX_TOOLWINDOW
            )
            self._wndproc_ref = window_class.lpfnWndProc
            self._overlay_hwnd = win32gui.CreateWindowEx(
                ex_style,
                self._class_name,
                "FH6 Mouse Isolation",
                win32con.WS_POPUP,
                x,
                y,
                width,
                height,
                self.game_hwnd,
                0,
                instance,
                None,
            )
            # Alpha 1/255 is visually imperceptible but still participates in
            # Windows hit testing. Alpha 0 can become click-through on some PCs.
            win32gui.SetLayeredWindowAttributes(
                self._overlay_hwnd,
                0,
                1,
                win32con.LWA_ALPHA,
            )
            win32gui.SetWindowPos(
                self._overlay_hwnd,
                win32con.HWND_TOP,
                x,
                y,
                width,
                height,
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
            )
            self._ready_event.set()

            visible = True
            while not self._stop_event.is_set() and not self._dismissed:
                if win32gui.PumpWaitingMessages():
                    break
                if not win32gui.IsWindow(self.game_hwnd):
                    break

                should_show = bool(
                    win32gui.IsWindowVisible(self.game_hwnd)
                    and not win32gui.IsIconic(self.game_hwnd)
                )
                if should_show:
                    bounds = self._game_client_bounds()
                    if bounds is None:
                        break
                    x, y, width, height = bounds
                    win32gui.SetWindowPos(
                        self._overlay_hwnd,
                        0,
                        x,
                        y,
                        width,
                        height,
                        win32con.SWP_NOACTIVATE
                        | win32con.SWP_NOZORDER
                        | win32con.SWP_SHOWWINDOW,
                    )
                    visible = True
                elif visible:
                    win32gui.ShowWindow(self._overlay_hwnd, win32con.SW_HIDE)
                    visible = False
                time.sleep(0.05)
        except Exception as exc:
            self._startup_error = str(exc)
            self._ready_event.set()
        finally:
            hwnd = self._overlay_hwnd
            if hwnd and win32gui.IsWindow(hwnd):
                try:
                    win32gui.DestroyWindow(hwnd)
                except Exception:
                    pass
            self._overlay_hwnd = None
            self._ready_event.set()
            if registered:
                try:
                    win32gui.UnregisterClass(self._class_name, instance)
                except Exception:
                    pass
