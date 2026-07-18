import ctypes
import threading

import numpy as np
import win32gui
import win32ui


# PW_CLIENTONLY | PW_RENDERFULLCONTENT. This is the same mode used by the
# working fork and asks Windows to render the client area even when covered.
PW_CLIENT_RENDERFULLCONTENT = 0x00000003


class WindowCaptureManager:
    """Capture a window client area without reading pixels from the desktop."""

    def __init__(self, hwnd):
        self.hwnd = int(hwnd)
        self._lock = threading.RLock()

    def is_valid(self):
        return bool(self.hwnd and win32gui.IsWindow(self.hwnd))

    def capture_client(self):
        if not self.is_valid() or win32gui.IsIconic(self.hwnd):
            return None

        left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
        width = int(right - left)
        height = int(bottom - top)
        if width <= 0 or height <= 0:
            return None

        hwnd_dc = None
        source_dc = None
        memory_dc = None
        bitmap = None
        with self._lock:
            try:
                # Keep the proven fork implementation here: create the target
                # bitmap from the window DC, while flag=3 asks PrintWindow to
                # render only the client area into it.
                hwnd_dc = win32gui.GetWindowDC(self.hwnd)
                if not hwnd_dc:
                    return None
                source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                memory_dc = source_dc.CreateCompatibleDC()
                bitmap = win32ui.CreateBitmap()
                bitmap.CreateCompatibleBitmap(source_dc, width, height)
                memory_dc.SelectObject(bitmap)

                ok = ctypes.windll.user32.PrintWindow(
                    self.hwnd,
                    memory_dc.GetSafeHdc(),
                    PW_CLIENT_RENDERFULLCONTENT,
                )
                if ok != 1:
                    return None

                raw = bitmap.GetBitmapBits(True)
                frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
                return frame[:, :, :3].copy()
            except Exception:
                return None
            finally:
                if bitmap is not None:
                    try:
                        win32gui.DeleteObject(bitmap.GetHandle())
                    except Exception:
                        pass
                if memory_dc is not None:
                    try:
                        memory_dc.DeleteDC()
                    except Exception:
                        pass
                if source_dc is not None:
                    try:
                        source_dc.DeleteDC()
                    except Exception:
                        pass
                if hwnd_dc:
                    try:
                        win32gui.ReleaseDC(self.hwnd, hwnd_dc)
                    except Exception:
                        pass

    def capture_region(self, region=None):
        frame = self.capture_client()
        if frame is None or region is None:
            return frame

        try:
            client_x, client_y = win32gui.ClientToScreen(self.hwnd, (0, 0))
            region_x, region_y, region_w, region_h = [int(v) for v in region]
            x1 = region_x - int(client_x)
            y1 = region_y - int(client_y)
            x2 = x1 + region_w
            y2 = y1 + region_h
            height, width = frame.shape[:2]
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:
                return None
            return frame[y1:y2, x1:x2].copy()
        except Exception:
            return None
