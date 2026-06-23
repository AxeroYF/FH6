import sys
import os
# ====== 【修复 OMP 冲突的核心代码】 ======
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# =======================================
import json
import time
import ctypes
import subprocess
# ====== 【新增】：启动前置环境检测 (防闪退机制) ======
def check_windows_dependencies():
    if sys.platform != "win32":
        return
    missing_dlls = []
    # OpenCV(cv2) 等图像识别库强依赖微软 VC++ 2015-2022 运行库
    required_dlls = ["vcruntime140.dll", "msvcp140.dll", "vcruntime140_1.dll"]

    for dll in required_dlls:
        try:
            # 尝试静默加载该运行库，如果系统里没有，就会触发 OSError
            ctypes.WinDLL(dll)
        except OSError:
            missing_dlls.append(dll)

    if missing_dlls:
        msg = (
            f"警告：系统缺失以下关键运行库，大概率会导致程序闪退或图像识别失败：\n\n"
            f"{', '.join(missing_dlls)}\n\n"
            f"这是因为您的电脑缺少微软 C++ 运行环境。\n"
            f"请搜索下载【微软常用运行库合集】或【VC++ 2015-2022】安装后重试。\n\n"
            f"点击“确定”强行继续运行（如果闪退请安装运行库）。"
        )
        # 0x30 = MB_ICONWARNING (黄色警告图标), 0x0 = MB_OK (只有确定按钮)
        ctypes.windll.user32.MessageBoxW(0, msg, "缺少运行库拦截提示", 0x30 | 0x0)
# 在导入耗性能的大型模块前，第一时间执行拦截检测
check_windows_dependencies()
# ===================================================
# 【极其关键】：必须在任何 UI 库导入之前设置 DPI 感知
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Win 8.1+
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Win Vista+
    except Exception:
        pass

import customtkinter as ctk
ctk.deactivate_automatic_dpi_awareness()
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)
import cv2
import numpy as np
import pyautogui
import pydirectinput
from pynput import keyboard
import win32gui
import threading

from image_matcher import ImageMatcherMixin

from app_resources import (
    APP_DIR,
    INTERNAL_DIR,
    CONFIG_DIR,
    USER_CONFIG_FILE,
    LOG_FILE,
    CACHE_DIR,
    TEMPLATE_CACHE_FILE,
    TEMPLATE_META_FILE,
    CURRENT_VERSION,
    auto_extract_configs,
    auto_extract_images,
    get_app_dir,
    get_asset_path,
    get_img_path,
)


SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]


# --- 硬件扫描码 (Scan Codes) 包含数字 0-9 ---
DIK_CODES = {
    # control
    "esc": (0x01, False),
    "enter": (0x1C, False),
    "space": (0x39, False),
    "backspace": (0x0E, False),
    "tab": (0x0F, False),
    "lshift": (0x2A, False),
    "rshift": (0x36, False),
    "lctrl": (0x1D, False),
    "rctrl": (0x1D, True),
    "lalt": (0x38, False),
    "ralt": (0x38, True),
    "capslock": (0x3A, False),

    # letters
    "a": (0x1E, False),
    "b": (0x30, False),
    "c": (0x2E, False),
    "d": (0x20, False),
    "e": (0x12, False),
    "f": (0x21, False),
    "g": (0x22, False),
    "h": (0x23, False),
    "i": (0x17, False),
    "j": (0x24, False),
    "k": (0x25, False),
    "l": (0x26, False),
    "m": (0x32, False),
    "n": (0x31, False),
    "o": (0x18, False),
    "p": (0x19, False),
    "q": (0x10, False),
    "r": (0x13, False),
    "s": (0x1F, False),
    "t": (0x14, False),
    "u": (0x16, False),
    "v": (0x2F, False),
    "w": (0x11, False),
    "x": (0x2D, False),
    "y": (0x15, False),
    "z": (0x2C, False),

    # number row
    "1": (0x02, False),
    "2": (0x03, False),
    "3": (0x04, False),
    "4": (0x05, False),
    "5": (0x06, False),
    "6": (0x07, False),
    "7": (0x08, False),
    "8": (0x09, False),
    "9": (0x0A, False),
    "0": (0x0B, False),

    # arrows / navigation
    "up": (0xC8, True),
    "down": (0xD0, True),
    "left": (0xCB, True),
    "right": (0xCD, True),
    "pageup": (0xC9, True),
    "pagedown": (0xD1, True),
    "home": (0xC7, True),
    "end": (0xCF, True),
    "insert": (0xD2, True),
    "delete": (0xD3, True),

    # function keys
    "f1": (0x3B, False),
    "f2": (0x3C, False),
    "f3": (0x3D, False),
    "f4": (0x3E, False),
    "f5": (0x3F, False),
    "f6": (0x40, False),
    "f7": (0x41, False),
    "f8": (0x42, False),
    "f10": (0x44, False),
    "f11": (0x57, False),
    "f12": (0x58, False),
}

# --- 全局配置 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
pyautogui.FAILSAFE = False


class FH_UltimateBot(ImageMatcherMixin, ctk.CTk):
    def __init__(self):
        super().__init__()
        #窗口相关
        self.title(f"FH6Auto by Krami v{CURRENT_VERSION}")
        self.geometry("1480x800")
        self.minsize(1320, 760)
        self.attributes("-topmost", False)
        self.attributes("-alpha", 0.98)
        self.resizable(True, True)

        try:
            icon_path = get_asset_path("icon.ico")
            if icon_path:
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.is_running = False
        self.current_thread = None
        self.is_paused = False  # <--- 【新增】全局暂停状态

        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.global_loop_current = 0

        self.template_cache = {}
        self.scaled_template_cache = {}
        self.file_template_cache = {}
        self.image_path_cache = {}
        self.scaled_gray_template_cache = {}
        self.scaled_gray_invert_cache = {}
        self.scales_cache = {}
        self.last_positions = {}
        self.edge_template_cache = {}
        self.scaled_edge_template_cache = {}
        self._log_line_count = 0
        self._log_trim_threshold = 1200
        self._log_keep_lines = 800
        self.is_log_collapsed = False
        self.expanded_window_height = 760
        self.invalid_blueprint_abort = False
        self.strict_car_debug_seq = 0
        self.strict_car_debug_last_miss_save = 0.0
        self.ai_car_debug_seq = 0
        self.ai_car_debug_last_miss_save = 0.0
        self.yolo_car_select_model = None
        self.yolo_car_select_model_path = None
        self.yolo_car_select_model_lock = threading.Lock()
        self.ai_model_preload_started = False
        self.race_notice_shown = False

        self.init_regions()

        # 【优化加载速度】：将IO提取与图像缓存的加载/生成放到后台线程，避免阻塞主界面启动
        # 增加模型释放步骤
        def background_init():
            auto_extract_images()

            self.prepare_template_cache()
            #self.use_ocr = self.config.get("use_ocr", True)
            #if self.use_ocr:
            #    self.init_ocr_engine()
        threading.Thread(target=background_init, daemon=True).start()

        #加载配置文件
        auto_extract_configs()
        self.load_config()

        self.setup_ui()
        self.start_hotkey_listener()
        self.update_skill_grid()
        self.center_window()
        self.preload_ai_model_async()

        self.log("免责声明：本脚本仅供 Python 自动化技术交流与学习使用。请勿用于商业盈利或破坏游戏平衡，因使用本脚本造成的账号封禁等损失，由使用者自行承担。")
        self.log("因为是个人优化开发，测试条件以及能适配的设备有限，遇到难以解决的兼容性问题，敬请谅解")
        self.log("默认刷图车辆：【斯巴鲁Impreza 22B-STi Version】【调校S2-834】【保持默认涂装】【收藏车辆】")
        self.log("蓝图代码可自行修改")
        self.log("默认分辨率为1080P，请勿开启HDR，以免影响图片识别。工具运行目录不要有中文。")
        self.log("游戏设置为【自动转向】【手动挡】，游戏语言设置为【简体中文】")
        self.log("ai版自带一个预训练模型。点击【AI辅助】开启后，会优先使用ai模型选车，兼容性可能比模板检测更好")
        self.log("大部分以图像识别作为引导，减少机器盲目操作的风险，但仍无法完全避免，使用前请做好准备")

    # ==========================================
    # --- UI 安全调度 ---
    # ==========================================
    def ui_call(self, func, *args, **kwargs):
        try:
            self.after(0, lambda: func(*args, **kwargs))
        except Exception:
            pass

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        gx, gy, gw, gh = self.regions["全界面"]
        x = gx + (gw - w) // 2
        y = gy + (gh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def format_elapsed(self, seconds):
        seconds = max(0, int(seconds))
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def reset_run_stats(self):
        self.start_time = time.time()
        self.active_task_name = "初始化"
        self.active_task_started_at = self.start_time
        self.task_time_totals = {
            "循环跑图": 0.0,
            "批量买车": 0.0,
            "超级抽奖": 0.0,
            "测试启动": 0.0,
            "F3测图": 0.0,
        }

    def finalize_active_task_time(self):
        task_name = getattr(self, "active_task_name", "")
        started_at = getattr(self, "active_task_started_at", None)
        if task_name in getattr(self, "task_time_totals", {}) and started_at:
            self.task_time_totals[task_name] += max(0.0, time.time() - started_at)
        self.active_task_started_at = time.time()

    def normalize_step_entry(self, entry_widget, default_value):
        try:
            v = "".join(c for c in entry_widget.get() if c.isdigit())
            if v == "":
                v = str(default_value)
            iv = int(v)
            if iv < 1:
                iv = 1
            if iv > 3:
                iv = 3
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(iv))
        except Exception:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, str(default_value))
    # ==========================================
    # --- 初始化全局 Region ---
    # ==========================================
    def init_regions(self):
        sw, sh = pyautogui.size()
        self.update_regions_by_window(0, 0, sw, sh)

    def update_regions_by_window(self, x, y, w, h):
        self.regions = {
            "全界面": (x, y, w, h),
            "左上": (x, y, w // 2, h // 2),
            "右上": (x + w // 2, y, w // 2, h // 2),
            "左下": (x, y + h // 2, w // 2, h // 2),
            "右下": (x + w // 2, y + h // 2, w // 2, h // 2),
            "上": (x, y, w, h // 2),
            "下": (x, y + h // 2, w, h // 2),
            "左": (x, y, w // 2, h),
            "右": (x + w // 2, y, w // 2, h),
            "中间": (x + w // 4, y + h // 4, w // 2, h // 2),
            "车辆菜单列表": (
                x,
                y + int(h * 0.48),
                int(w * 0.26),
                int(h * 0.42),
            ),
        }

    # ==========================================
    # --- 配置管理 ---
    # ==========================================
    def load_config(self):
        # 1. 直接使用内置字典作为“绝对底本”（最安全，无视打包丢文件问题）
        self.config = {
            "race_count": 99,
            "buy_count": 30,
            "cj_count": 30,
            "chk_1": True,
            "chk_2": True,
            "chk_3": True,
            "next_1": 2,
            "next_2": 3,
            "next_3": 1,
            "global_loops": 10,
            "skill_dirs": ["right", "up", "up", "up", "left"],
            "share_code": "890169683",
            "auto_restart": False,
            "restart_cmd": "start steam://run/2483190",
            "race_timeout": 300,
            "ai_assist": False,
            "ai_prefer": False,
            "ai_only": False,
            "ai_auto_capture": False,
            "smart_page": False,
            "ai_model_path": "models/fh6_car_select_yolo.pt"
        }
        ext_path = USER_CONFIG_FILE
        # 2. 读取用户的 config.json，并与底本合并（自动补全缺失项）
        if os.path.exists(ext_path):
            try:
                with open(ext_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
            except Exception as e:
                self.log(f"用户 config.json 损坏，已自动恢复默认配置。")
        self.config["ai_prefer"] = bool(self.config.get("ai_assist", False))

        # 3. 将最新、最完整的配置重新写回外置文件
        try:
            with open(ext_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass


    def save_config(self):
        try:
            self.config["race_count"] = int(self.entry_race.get())
            self.config["buy_count"] = int(self.entry_car.get())
            self.config["cj_count"] = int(self.entry_cj.get())
            self.config["global_loops"] = int(self.entry_global_loop.get())
            if hasattr(self, "entry_race_timeout"):
                self.config["race_timeout"] = max(60, int(self.entry_race_timeout.get()))
            self.config["share_code"] = "".join(c for c in self.entry_share.get() if c.isdigit())
            #self.config["base_width"] = int(self.entry_base_w.get())
            self.config["next_1"] = int(self.entry_next1.get())
            self.config["next_2"] = int(self.entry_next2.get())
            self.config["next_3"] = int(self.entry_next3.get())
        except Exception:
            pass

        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        self.config["auto_restart"] = self.config.get("auto_restart", False)
        if hasattr(self, "var_ai_assist"):
            self.config["ai_assist"] = self.var_ai_assist.get()
            self.config["ai_prefer"] = self.config["ai_assist"]
        if hasattr(self, "var_ai_only"):
            self.config["ai_only"] = self.var_ai_only.get()
        if hasattr(self, "var_ai_auto_capture"):
            self.config["ai_auto_capture"] = self.var_ai_auto_capture.get()
        if hasattr(self, "var_smart_page"):
            self.config["smart_page"] = self.var_smart_page.get()
        if hasattr(self, "le_restart_cmd"):
            self.config["restart_cmd"] = self.le_restart_cmd.get().strip()
        try:
            with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"保存配置失败: {e}")

    # ==========================================
    # --- UI 布局设计 ---
    # ==========================================
    def setup_ui(self):
        from ui_layout import setup_ui
        setup_ui(self)

    def update_timer(self):
        if not self.is_running:
            return

        now = time.time()
        total_elapsed = now - getattr(self, "start_time", now)
        task_elapsed = now - getattr(self, "active_task_started_at", now)
        totals = getattr(self, "task_time_totals", {})
        race_total = totals.get("循环跑图", 0.0)
        buy_total = totals.get("批量买车", 0.0)
        cj_total = totals.get("超级抽奖", 0.0)

        active_task = getattr(self, "active_task_name", "")
        if active_task == "循环跑图":
            race_total += task_elapsed
        elif active_task == "批量买车":
            buy_total += task_elapsed
        elif active_task == "超级抽奖":
            cj_total += task_elapsed

        try:
            self.lbl_runtime_task_time.configure(text=self.format_elapsed(task_elapsed))
            self.lbl_runtime_total_time.configure(text=self.format_elapsed(total_elapsed))
            self.lbl_runtime_totals.configure(
                text=(
                    f"跑图 {self.format_elapsed(race_total)} | "
                    f"买车 {self.format_elapsed(buy_total)} | "
                    f"超抽 {self.format_elapsed(cj_total)}"
                )
            )
        except Exception: pass

        if self.is_running:
            self.after(1000, self.update_timer)

    def update_running_ui(self, task_name="", current_val=0, max_val=0):
        try:
            if task_name:
                old_task = getattr(self, "active_task_name", "")
                if old_task != task_name:
                    self.finalize_active_task_time()
                    self.active_task_name = task_name
                self.ui_call(self.lbl_runtime_task.configure, text=task_name)
            if max_val > 0:
                self.ui_call(self.lbl_runtime_progress.configure, text=f"{current_val} / {max_val}")
        except Exception:
            pass

    def update_running_state(self, state):
        try:
            if state == "running":
                self.lbl_run_state.configure(text="运行中", fg_color="#238636", text_color="#FFFFFF")
                self.btn_runtime_stop.configure(state="normal")
                self.btn_stop.configure(text="停止任务 (F8)", fg_color="#DA3633", hover_color="#B02A37")
            elif state == "paused":
                self.lbl_run_state.configure(text="已暂停", fg_color="#9A6700", text_color="#FFFFFF")
                self.btn_runtime_stop.configure(state="normal")
            else:
                self.lbl_run_state.configure(text="待机", fg_color="#222B36", text_color="#C9D1D9")
                self.lbl_runtime_task.configure(text="等待中")
                self.lbl_runtime_progress.configure(text="0 / 0")
                self.lbl_runtime_loop.configure(text="0 / 0")
                self.lbl_runtime_task_time.configure(text="00:00:00")
                self.lbl_runtime_total_time.configure(text="00:00:00")
                self.lbl_runtime_totals.configure(text="跑图 00:00:00 | 买车 00:00:00 | 超抽 00:00:00")
                self.btn_runtime_stop.configure(state="disabled")
                self.btn_stop.configure(text="等待指令 (F8)", fg_color="#222B36", hover_color="#2F3B4A")
        except Exception:
            pass

    # ==========================================
    # --- 核心操作与流程控制 ---
    # ==========================================
    def hw_key_down(self, key):
        if key not in DIK_CODES:
            return
        scan_code, extended = DIK_CODES[key]
        flags = 0x0008 | (0x0001 if extended else 0)
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def hw_key_up(self, key):
        if key not in DIK_CODES:
            return
        scan_code, extended = DIK_CODES[key]
        flags = 0x000A | (0x0001 if extended else 0)
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(1), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def hw_press(self, key, delay=0.08):
        self.check_pause()  # <--- 【新增】如果正在暂停，脚本会在此处无限等待直到恢复
        if not self.is_running:
            return
        self.hw_key_down(key)
        time.sleep(delay)
        self.hw_key_up(key)
    #副屏支持
    def hw_mouse_move(self, x, y):
        # 获取多显示器组成的整个“虚拟桌面”坐标和尺寸
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width == 0 or height == 0:
            return
        # 映射到 0~65535 的绝对虚拟坐标系统
        calc_x = int((x - left) * 65535 / width)
        calc_y = int((y - top) * 65535 / height)
        # MOUSEEVENTF_MOVE = 0x0001, MOUSEEVENTF_ABSOLUTE = 0x8000, MOUSEEVENTF_VIRTUALDESK = 0x4000
        flags = 0x0001 | 0x8000 | 0x4000
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.mi = MouseInput(calc_x, calc_y, 0, flags, 0, ctypes.pointer(extra))
        cmd = Input(ctypes.c_ulong(0), ii_)
        SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))
    def game_click(self, pos, double=False):
        self.check_pause()  # <--- 【新增】拦截鼠标点击
        if not self.is_running or not pos:
            return
        x, y = int(pos[0]), int(pos[1])

        # 使用多屏兼容的硬件级移动
        self.hw_mouse_move(x, y)
        time.sleep(0.2)
        for _ in range(2 if double else 1):
            pydirectinput.mouseDown()
            time.sleep(0.1)
            pydirectinput.mouseUp()
            time.sleep(0.1)
        time.sleep(0.1)
        # 移开鼠标 10 像素，防止游戏里的悬浮提示框遮挡下一次截图
        try:
            gx, gy, gw, gh = self.regions["全界面"]
            # 移动到游戏左上角向内偏移 5 个像素，确保在游戏内但绝对不会挡住任何中间UI
            self.hw_mouse_move(gx + 5, gy + 5)
        except Exception:
            # 兜底：如果获取不到窗口坐标，移到绝对屏幕左上角
            self.hw_mouse_move(5, 5)
        time.sleep(0.2)

    def move_to_game_coord(self, x, y):
        """
        将鼠标移动到以【游戏窗口左上角】为起点的 (x, y) 坐标。
        例如传入 (5, 5)，就会移动到游戏内左上角 5 像素的安全位置。
        """
        try:
            gx, gy, gw, gh = self.regions["全界面"]
            abs_x = gx + x
            abs_y = gy + y
            self.hw_mouse_move(abs_x, abs_y)
        except Exception:
            # 兜底：如果获取不到窗口坐标，就直接当绝对坐标移动
            self.hw_mouse_move(x, y)

    def add_skill_dir(self, direction):
        self.config["skill_dirs"].append(direction)
        self.update_skill_grid()
        self.save_config()

    def clear_skill_dir(self):
        self.config["skill_dirs"].clear()
        self.update_skill_grid()
        self.save_config()

    def update_skill_grid(self):
        for r in range(4):
            for c in range(4):
                self.grid_labels[r][c].configure(fg_color="#333333")

        curr_r, curr_c = 3, 0
        self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
        valid_dirs = []

        for d in self.config["skill_dirs"]:
            if d == "up":
                curr_r -= 1
            elif d == "down":
                curr_r += 1
            elif d == "left":
                curr_c -= 1
            elif d == "right":
                curr_c += 1

            if 0 <= curr_r < 4 and 0 <= curr_c < 4:
                self.grid_labels[curr_r][curr_c].configure(fg_color="#3498DB")
                valid_dirs.append(d)
            else:
                break

        self.config["skill_dirs"] = valid_dirs

    def log(self, message):
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}"

        def write_ui():
            try:
                # 写入下方大界面的日志
                self.log_box.configure(state="normal")
                self.log_box.insert("end", full_msg + "\n")
                self._log_line_count = getattr(self, "_log_line_count", 0) + 1
                if self._log_line_count > getattr(self, "_log_trim_threshold", 1200):
                    keep_lines = getattr(self, "_log_keep_lines", 800)
                    self.log_box.delete("1.0", f"end-{keep_lines + 1}lines")
                    self._log_line_count = keep_lines
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            except Exception:
                pass
        self.ui_call(write_ui)

    def toggle_log_panel(self):
        try:
            if self.is_log_collapsed:
                self.bottom_frame.pack(fill="both", expand=True, pady=(8, 0))
                if hasattr(self, "lbl_log_title"):
                    self.lbl_log_title.configure(text="运行日志")
                if hasattr(self, "btn_toggle_log"):
                    self.btn_toggle_log.configure(text="收起日志")
                self.minsize(1180, 700)
                self.geometry(f"{self.winfo_width()}x{getattr(self, 'expanded_window_height', 760)}")
                self.is_log_collapsed = False
            else:
                self.expanded_window_height = self.winfo_height()
                self.bottom_frame.pack_forget()
                if hasattr(self, "lbl_log_title"):
                    self.lbl_log_title.configure(text="日志已收起")
                if hasattr(self, "btn_toggle_log"):
                    self.btn_toggle_log.configure(text="展开日志")
                self.minsize(1180, 510)
                self.geometry(f"{self.winfo_width()}x510")
                self.is_log_collapsed = True
        except Exception:
            pass

    def write_debug_image(self, path, image_bgr):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            ok, buf = cv2.imencode(".png", image_bgr)
            if ok:
                buf.tofile(path)
                return True
        except Exception:
            pass
        return False

    def on_ai_assist_changed(self):
        enabled = bool(self.var_ai_assist.get())
        self.config["ai_assist"] = enabled
        self.config["ai_prefer"] = enabled
        if not enabled:
            if hasattr(self, "var_ai_only"):
                self.var_ai_only.set(False)
                self.config["ai_only"] = False
            self.yolo_car_select_model = None
            self.yolo_car_select_model_path = None
            self.ai_model_preload_started = False
        self.save_config()
        self.log("AI assist enabled." if enabled else "AI assist disabled.")
        if enabled:
            self.preload_ai_model_async()

    def on_smart_page_changed(self):
        enabled = bool(self.var_smart_page.get())
        self.config["smart_page"] = enabled
        if not enabled:
            self.memory_car_page = 0
        self.save_config()
        self.log("Smart page enabled." if enabled else "Smart page disabled.")

    def on_ai_only_changed(self):
        enabled = bool(self.var_ai_only.get())
        self.config["ai_only"] = enabled
        if enabled:
            self.var_ai_assist.set(True)
            self.config["ai_assist"] = True
            self.config["ai_prefer"] = True
        self.save_config()
        self.log("AI only enabled." if enabled else "AI only disabled.")

    def on_ai_auto_capture_changed(self):
        enabled = bool(self.var_ai_auto_capture.get())
        self.config["ai_auto_capture"] = enabled
        self.save_config()
        self.log("AI auto capture enabled." if enabled else "AI auto capture disabled.")

    def resolve_ai_model_path(self):
        candidates = []
        configured = str(self.config.get("ai_model_path", "")).strip()
        if configured:
            candidates.append(configured)
        candidates.extend([
            "models/fh6_car_select_yolo.pt",
            "runs/detect/fh6_car_select/yolo11n_all_boxes_v2/weights/best.pt",
            "runs/detect/fh6_car_select/yolo11n_all_boxes/weights/best.pt",
            "runs/detect/runs/fh6_car_select/yolo11n_draft/weights/best.pt",
        ])
        seen = set()
        for item in candidates:
            if not item or item in seen:
                continue
            seen.add(item)
            path = item if os.path.isabs(item) else os.path.join(get_app_dir(), item)
            if os.path.exists(path):
                return path
        return None

    def get_yolo_car_select_model(self):
        if not self.config.get("ai_assist", False):
            return None
        model_path = self.resolve_ai_model_path()
        if not model_path:
            self.log("[AISelect] model not found. Put best.pt at models/fh6_car_select_yolo.pt or update config.json ai_model_path.")
            return None
        with self.yolo_car_select_model_lock:
            if self.yolo_car_select_model is not None and self.yolo_car_select_model_path == model_path:
                return self.yolo_car_select_model
            try:
                from ultralytics import YOLO
                self.yolo_car_select_model = YOLO(model_path)
                self.yolo_car_select_model_path = model_path
                self.log(f"[AISelect] model loaded: {model_path}")
                return self.yolo_car_select_model
            except Exception as e:
                self.log(f"[AISelect] cannot load YOLO model: {e}")
                self.yolo_car_select_model = None
                self.yolo_car_select_model_path = None
                return None

    def preload_ai_model_async(self):
        if self.ai_model_preload_started or not self.config.get("ai_assist", False):
            return
        self.ai_model_preload_started = True

        def worker():
            self.log("[AISelect] preloading model...")
            self.get_yolo_car_select_model()

        threading.Thread(target=worker, daemon=True).start()

    def resolve_ai_device(self):
        configured = str(self.config.get("ai_device", "auto")).strip().lower()
        try:
            import torch
            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                return configured if configured and configured != "auto" else "0"
        except Exception:
            pass
        if configured in ("cpu", "mps"):
            return configured
        return "cpu"

    def yolo_box_to_dict(self, item, conf_threshold=0.25):
        conf = float(item.conf[0])
        if conf < conf_threshold:
            return None
        cls_id = int(item.cls[0])
        names = {0: "new", 1: "b600", 2: "car"}
        x1, y1, x2, y2 = [float(v) for v in item.xyxy[0].tolist()]
        return {
            "cls": cls_id,
            "name": names.get(cls_id, f"class_{cls_id}"),
            "conf": conf,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "w": x2 - x1,
            "h": y2 - y1,
            "cx": (x1 + x2) / 2.0,
            "cy": (y1 + y2) / 2.0,
        }

    def yolo_yellow_tag_ratio(self, img, box):
        try:
            x1 = max(0, int(box["x1"]))
            y1 = max(0, int(box["y1"]))
            x2 = min(img.shape[1], int(box["x2"]))
            y2 = min(img.shape[0], int(box["y2"]))
            roi = img[y1:y2, x1:x2]
            if roi.size == 0:
                return 0.0
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, np.array([24, 90, 170]), np.array([42, 255, 255]))
            return float(np.count_nonzero(mask)) / max(1, mask.size)
        except Exception:
            return 0.0

    def yolo_box_distance(self, a, b):
        return float(np.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]))

    def find_yolo_car_candidate(self, img, boxes, min_tag_yellow_ratio=0.18):
        image_h, image_w = img.shape[:2]
        tags = [b for b in boxes if b["name"] == "new"]
        classes = [b for b in boxes if b["name"] == "b600"]
        cars = [b for b in boxes if b["name"] == "car"]
        failures = []
        candidates = []

        for tag in sorted(tags, key=lambda b: (b["y1"], b["x1"])):
            if tag["x1"] < image_w * 0.20 or tag["y1"] < image_h * 0.16 or tag["y1"] > image_h * 0.92:
                failures.append(f"tag out area conf={tag['conf']:.2f}")
                continue
            yellow_ratio = self.yolo_yellow_tag_ratio(img, tag)
            if yellow_ratio < min_tag_yellow_ratio:
                failures.append(f"tag color low conf={tag['conf']:.2f} yellow={yellow_ratio:.2f}")
                continue

            near_classes = []
            for cls_box in classes:
                dx = cls_box["cx"] - tag["cx"]
                dy = cls_box["cy"] - tag["cy"]
                if -120 <= dx <= 80 and -12 <= dy <= 80:
                    near_classes.append((abs(dx) + abs(dy), cls_box))
            if not near_classes:
                failures.append(f"no B600 near tag conf={tag['conf']:.2f}")
                continue
            near_classes.sort(key=lambda item: item[0])
            cls_box = near_classes[0][1]

            near_cars = []
            for car in cars:
                if car["w"] <= 0 or car["h"] <= 0:
                    continue
                rel_x = tag["cx"] - car["x1"]
                rel_y = tag["cy"] - car["y1"]
                if 0.58 * car["w"] <= rel_x <= 1.12 * car["w"] and 0.50 * car["h"] <= rel_y <= 1.12 * car["h"]:
                    near_cars.append((self.yolo_box_distance(tag, car), car))
            if not near_cars:
                failures.append(f"no target car linked conf={tag['conf']:.2f}")
                continue
            near_cars.sort(key=lambda item: item[0])
            car = near_cars[0][1]
            score = tag["conf"] * 0.34 + cls_box["conf"] * 0.28 + car["conf"] * 0.38
            candidates.append({
                "tag": tag,
                "b600": cls_box,
                "car": car,
                "score": score,
                "yellow": yellow_ratio,
                "reason": "pass",
            })

        if not candidates:
            reason = "; ".join(failures[-4:]) if failures else "no candidates"
            return None, reason

        candidates.sort(key=lambda c: (c["tag"]["y1"], c["tag"]["x1"], -c["score"]))
        return candidates[0], "pass"

    def save_ai_car_debug(self, screen_bgr, status, boxes=None, candidate=None, reason="", click=None, force=False):
        try:
            now = time.time()
            if status == "miss" and not force:
                if now - getattr(self, "ai_car_debug_last_miss_save", 0.0) < 1.5:
                    return
                self.ai_car_debug_last_miss_save = now

            self.ai_car_debug_seq += 1
            stamp = time.strftime("%Y%m%d_%H%M%S")
            name = f"{stamp}_{self.ai_car_debug_seq:04d}_{status}"
            root = os.path.join(get_app_dir(), "debug", "car_select_ai")
            raw_path = os.path.join(root, "raw", f"{name}.png")
            self.write_debug_image(raw_path, screen_bgr)

            annotated = screen_bgr.copy()
            colors = {
                "new": (0, 255, 255),
                "b600": (0, 128, 255),
                "car": (0, 255, 0),
            }
            selected = []
            if candidate:
                selected = [candidate["tag"], candidate["b600"], candidate["car"]]
            for box in boxes or []:
                color = colors.get(box["name"], (255, 255, 255))
                x1, y1, x2, y2 = [int(v) for v in (box["x1"], box["y1"], box["x2"], box["y2"])]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    annotated,
                    f"{box['name']} {box['conf']:.2f}",
                    (x1, max(18, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                    cv2.LINE_AA,
                )
            for box in selected:
                x1, y1, x2, y2 = [int(v) for v in (box["x1"], box["y1"], box["x2"], box["y2"])]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)

            if click:
                cx, cy = int(click[0]), int(click[1])
                cv2.drawMarker(annotated, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 30, 2)
                cv2.putText(
                    annotated,
                    f"CLICK {cx},{cy}",
                    (cx + 8, max(20, cy - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
            if reason:
                cv2.putText(
                    annotated,
                    reason[:130],
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0) if candidate else (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
            out_dir = "pass" if status == "pass" else "miss"
            self.write_debug_image(os.path.join(root, out_dir, f"{name}.png"), annotated)
        except Exception as e:
            self.log(f"[AISelect] save debug failed: {e}")

    def find_new_consumable_car_ai(self, region=None, save_miss=True):
        model = self.get_yolo_car_select_model()
        if model is None:
            return None
        try:
            screen_bgr = self.capture_region(region)
            result = model.predict(
                source=screen_bgr,
                imgsz=int(self.config.get("ai_imgsz", 960)),
                conf=float(self.config.get("ai_conf", 0.25)),
                device=self.resolve_ai_device(),
                verbose=False,
            )[0]
            boxes = []
            if result.boxes is not None:
                for item in result.boxes:
                    box = self.yolo_box_to_dict(item, conf_threshold=float(self.config.get("ai_conf", 0.25)))
                    if box:
                        boxes.append(box)
            candidate, reason = self.find_yolo_car_candidate(
                screen_bgr,
                boxes,
                min_tag_yellow_ratio=float(self.config.get("ai_min_tag_yellow_ratio", 0.18)),
            )
            if not candidate:
                counts = (
                    f"new={sum(1 for b in boxes if b['name'] == 'new')} "
                    f"b600={sum(1 for b in boxes if b['name'] == 'b600')} "
                    f"car={sum(1 for b in boxes if b['name'] == 'car')}"
                )
                self.log(f"[AISelect] miss: {counts}; {reason}")
                if save_miss and self.config.get("ai_auto_capture", False):
                    self.save_ai_car_debug(screen_bgr, "miss", boxes=boxes, reason=reason, force=True)
                return None

            click_local = (int(candidate["car"]["cx"]), int(candidate["car"]["cy"]))
            click_abs = (
                click_local[0] + (region[0] if region else 0),
                click_local[1] + (region[1] if region else 0),
            )
            self.log(
                f"[AISelect] pass: score={candidate['score']:.3f} "
                f"new={candidate['tag']['conf']:.2f} yellow={candidate['yellow']:.2f} "
                f"b600={candidate['b600']['conf']:.2f} car={candidate['car']['conf']:.2f}"
            )
            if self.config.get("ai_auto_capture", False):
                self.save_ai_car_debug(screen_bgr, "pass", boxes=boxes, candidate=candidate, reason="pass", click=click_local, force=True)
            return click_abs
        except Exception as e:
            self.log(f"[AISelect] exception: {e}")
            return None

    def save_strict_car_debug(self, screen_bgr, status, reason="", boxes=None, scores=None, click=None, force=False):
        try:
            now = time.time()
            if status == "miss" and not force:
                # wait_for_new_consumable_car_strict 会循环调用，miss 图做节流即可。
                if now - getattr(self, "strict_car_debug_last_miss_save", 0.0) < 1.5:
                    return
                self.strict_car_debug_last_miss_save = now

            self.strict_car_debug_seq += 1
            stamp = time.strftime("%Y%m%d_%H%M%S")
            name = f"{stamp}_{self.strict_car_debug_seq:04d}_{status}"
            root = os.path.join(get_app_dir(), "debug", "car_select")
            if status == "pass":
                self.cleanup_recent_strict_car_miss(root, keep_seconds=12.0)

            raw_path = os.path.join(root, "raw", f"{name}.png")
            self.write_debug_image(raw_path, screen_bgr)

            annotated = screen_bgr.copy()
            color_map = {
                "new": (0, 255, 255),
                "b600": (0, 128, 255),
                "car": (0, 255, 0),
            }
            for label, rect in (boxes or {}).items():
                if not rect:
                    continue
                x, y, w, h = [int(v) for v in rect]
                color = color_map.get(label, (255, 255, 255))
                cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
                score = ""
                if scores and label in scores:
                    score = f" {scores[label]:.2f}"
                cv2.putText(
                    annotated,
                    f"{label}{score}",
                    (x, max(20, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            if click:
                cx, cy = int(click[0]), int(click[1])
                cv2.drawMarker(annotated, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 28, 2)
                cv2.putText(
                    annotated,
                    f"CLICK {cx},{cy}",
                    (cx + 8, max(20, cy - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

            if reason:
                cv2.putText(
                    annotated,
                    reason[:120],
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255) if status == "miss" else (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            out_dir = "pass" if status == "pass" else "miss"
            annotated_path = os.path.join(root, out_dir, f"{name}.png")
            self.write_debug_image(annotated_path, annotated)
        except Exception as e:
            self.log(f"保存 StrictCar 调试图异常: {e}")

    def cleanup_recent_strict_car_miss(self, root, keep_seconds=12.0):
        try:
            now = time.time()
            miss_dir = os.path.join(root, "miss")
            raw_dir = os.path.join(root, "raw")
            if not os.path.isdir(miss_dir):
                return

            for filename in os.listdir(miss_dir):
                if not filename.lower().endswith(".png"):
                    continue
                miss_path = os.path.join(miss_dir, filename)
                try:
                    if now - os.path.getmtime(miss_path) > keep_seconds:
                        continue
                    os.remove(miss_path)
                    raw_name = filename.replace("_miss.png", "_miss.png")
                    raw_path = os.path.join(raw_dir, raw_name)
                    if os.path.exists(raw_path):
                        os.remove(raw_path)
                except Exception:
                    pass
        except Exception:
            pass
    def start_pipeline(self, start_step):
        if self.is_running:
            return

        if start_step == "race" and not self.race_notice_shown:
            race_notice = (
                "为了兼容性，请务必将游戏界面设置到1080P窗口模式，关闭HDR。"
                "\n\n点击确定才会开始流程，本弹窗只会出现一次。"
            )
            ok = ctypes.windll.user32.MessageBoxW(
                0,
                race_notice,
                "循环跑图开始提示",
                0x1 | 0x30,
            )
            if ok != 1:
                return
            self.race_notice_shown = True

        self.is_running = True
        self.save_config()

        self.reset_run_stats()
        self.update_running_state("running")
        self.update_timer()
        self.update_running_ui("初始化中...")
        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.global_loop_current = 0
        self.invalid_blueprint_abort = False

        def runner():
            if not self.check_and_focus_game():
                self.stop_all()
                return

            steps = ["race", "buy", "cj"]
            curr_idx = steps.index(start_step)

            try:
                total_loops = int(self.entry_global_loop.get())
            except Exception:
                total_loops = self.config.get("global_loops", 10)
            self.global_loop_current = 1
            self.ui_call(self.lbl_runtime_loop.configure, text=f"{self.global_loop_current} / {total_loops}")

            # 【新增】：全局连续失败计数器
            continuous_failures = 0
            # 【你可以修改这里】：设置全局允许的最大连续恢复次数（比如 3 次）
            MAX_RECOVERIES = 10

            while self.is_running:
                step_name = steps[curr_idx]
                success = False

                try:
                    if step_name == "race":
                        success = self.logic_race(int(self.entry_race.get()))
                    elif step_name == "buy":
                        success = self.logic_buy_car(int(self.entry_car.get()))
                    elif step_name == "cj":
                        success = self.logic_super_wheelspin(int(self.entry_cj.get()))
                except Exception as e:
                    self.log(f"执行模块 {step_name} 时异常: {e}")
                    success = False

                if not self.is_running:
                    break

                if getattr(self, "invalid_blueprint_abort", False):
                    break

                if not success:
                    if getattr(self, "invalid_blueprint_abort", False):
                        break

                    continuous_failures += 1

                    # 检查是否超过最大容忍次数
                    if continuous_failures > MAX_RECOVERIES:
                        self.log(f"!!! 警告：连续 {continuous_failures} 次触发断点恢复仍未能解决问题！")
                        self.log("为防止游戏陷入死循环，强制终止当前所有任务，请人工检查游戏状态。")
                        break # 直接跳出 while，停止脚本

                    self.log(f"正在进行全局恢复 (第 {continuous_failures}/{MAX_RECOVERIES} 次允许的重试)...")

                    if self.attempt_recovery():
                        continue # 恢复成功，回到 while 顶部再次尝试这个任务
                    else:
                        self.log("致命错误：连退回菜单/重启也失败了，彻底停止。")
                        break
                else:
                    # 只要这一个大步骤成功跑完了，就把连续失败次数清零，奖励它继续跑！
                    continuous_failures = 0
                #v1.0.1
                # ====== 核心流转与无限循环逻辑 ======
                next_idx = curr_idx + 1 # 默认前往下一步
                if curr_idx == 0:
                    if self.var_chk1.get():
                        try: next_idx = max(0, min(3, int(self.entry_next1.get()) - 1))
                        except Exception: next_idx = 1
                    else: break
                elif curr_idx == 1:
                    if self.var_chk2.get():
                        try: next_idx = max(0, min(3, int(self.entry_next2.get()) - 1))
                        except Exception: next_idx = 2
                    else: break
                elif curr_idx == 2:
                    if self.var_chk3.get():
                        try: next_idx = max(0, min(2, int(self.entry_next3.get()) - 1))
                        except Exception: next_idx = 0
                    else: break

                if next_idx <= curr_idx:
                    self.global_loop_current += 1

                    if self.global_loop_current > total_loops:
                        self.log("达到设定的总循环次数，任务圆满结束。")
                        break

                    self.log(f"开启新一轮大循环 ({self.global_loop_current}/{total_loops})")

                    self.ui_call(self.lbl_runtime_loop.configure, text=f"{self.global_loop_current} / {total_loops}")

                    self.race_counter = 0
                    self.car_counter = 0
                    self.cj_counter = 0

                curr_idx = next_idx

            self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

    def stop_all(self):
        if not self.is_running:
            return

        self.is_running = False
        self.is_paused = False  # <--- 【新增】彻底停止时必须解除暂停锁

        for key in DIK_CODES.keys():
            self.hw_key_up(key)

        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            self.hw_key_up(key)

        try:
            pydirectinput.mouseUp()
        except Exception:
            pass

        self.finalize_active_task_time()
        self.ui_call(self.update_running_state, "idle")
        self.log("!!! 任务已停止，所有物理按键状态已强制重置")
    def start_test_boot(self):
        """独立运行的测试开机流程"""
        if self.is_running:
            self.log("已有任务正在运行，请先点击停止后再测试启动流程！")
            return

        self.is_running = True
        self.save_config()
        self.reset_run_stats()
        self.update_running_state("running")
        self.update_running_ui("测试启动")
        self.update_timer()

        self.log("====== 开始独立测试自动开机与识别流程 ======")

        def test_runner():
            success = self.restart_game_and_boot(force_test=True)
            if success:
                self.log("测试结束：自动开机、A/B/C状态机识别并到达菜单完美跑通！")
            else:
                self.log("测试结束：自动开机流程失败，请检查截图或日志。")
            self.stop_all() # 测试完毕自动停止脚本，自动恢复回大窗口状态

        self.current_thread = threading.Thread(target=test_runner, daemon=True)
        self.current_thread.start()
    # ==========================================
    # --- 【新增】暂停与恢复逻辑 ---
    # ==========================================
    def toggle_pause(self):
        if not self.is_running:
            return

        self.is_paused = not self.is_paused

        if self.is_paused:
            self.log("⏸ 任务已暂停 (点击按钮恢复)")
            # 强制松开所有可能按住的按键，防止车自己开走或UI乱跳
            for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
                self.hw_key_up(key)
            try:
                pydirectinput.mouseUp()
            except Exception:
                pass
            self.ui_call(self.update_running_state, "paused")
        else:
            self.log("▶ 任务已恢复")
            self.ui_call(self.update_running_state, "running")

    def check_pause(self):
        """核心阻塞器：任何动作前调用此方法，如果是暂停状态，将在此无限等待"""
        while self.is_paused and self.is_running:
            time.sleep(0.1)


    def start_hotkey_listener(self):
        def hotkey_thread():
            def on_press(k):
                if k == keyboard.Key.f8:
                    self.stop_all()
                elif k == keyboard.Key.f3:  # <--- 【新增】F3 测试找图
                    self.start_test_find_image()

            with keyboard.Listener(on_press=on_press) as listener:
                listener.join()

        threading.Thread(target=hotkey_thread, daemon=True).start()


    # ==========================================
    # --- 逻辑保障 ---
    # ==========================================
    # 【新增】：强制切换英文键盘与关闭中文状态
    def set_english_input(self):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return
            # 策略1：尝试切美式键盘
            hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
            ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl)
            # 策略2：底层强制关闭当前中文输入法的中文状态(绝杀)
            WM_IME_CONTROL = 0x0283
            IMC_SETOPENSTATUS = 0x0006
            ctypes.windll.user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)

            self.log("已自动切换英文键盘/关闭中文输入法状态。")
        except Exception as e:
            self.log(f"自动防中文输入设置失败: {e}")
    def check_and_focus_game(self):
        self.log("检查游戏进程 (forzahorizon6.exe)...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if "forzahorizon6.exe" not in output.lower():
                self.log("未发现 forzahorizon6.exe 进程！(请确保游戏已运行)")
                return False

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                self.log("找到进程但无法解析PID！")
                return False

            hwnds = []

            def foreach_window(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        window_pid = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == target_pid:
                            hwnds.append(hwnd)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

            if hwnds:
                hwnd = hwnds[0]
                if ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                else:
                    ctypes.windll.user32.ShowWindow(hwnd, 5)

                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                # ====== 【新增】：强制关闭中文输入法 ======
                self.set_english_input()
                # ==========================================
                try:
                    # 1. 更新识图区域为游戏实际窗口区域（识图必须在游戏窗口内）
                    client_rect = win32gui.GetClientRect(hwnd)
                    pt = win32gui.ClientToScreen(hwnd, (0, 0))
                    gx, gy = pt[0], pt[1]
                    gw, gh = client_rect[2], client_rect[3]
                    # ====== 【核心修复】：拦截启动小窗/防作弊闪屏 ======
                    # 如果窗口宽度和高度太小，说明绝对不是正常的游戏主画面
                    if gw < 1000 or gh < 600:
                        self.log(f"拦截到过小窗口 ({gw}x{gh})，判定为启动闪屏，等待主窗口加载...")
                        return False
                    # ====================================================
                    self.update_regions_by_window(gx, gy, gw, gh)

                    # 2. 获取该窗口所在的物理显示器边界
                    MONITOR_DEFAULTTONEAREST = 2
                    hMonitor = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
                    class RECT(ctypes.Structure):
                        _fields_ = [
                            ("left", ctypes.c_long),
                            ("top", ctypes.c_long),
                            ("right", ctypes.c_long),
                            ("bottom", ctypes.c_long)
                        ]
                    class MONITORINFO(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", ctypes.c_ulong),
                            ("rcMonitor", RECT),
                            ("rcWork", RECT),
                            ("dwFlags", ctypes.c_ulong)
                        ]
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)

                    if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
                        mx = mi.rcMonitor.left
                        my = mi.rcMonitor.top
                        mw = mi.rcMonitor.right - mi.rcMonitor.left
                        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
                    else:
                        # 兜底：如果获取不到屏幕边界，就用游戏窗口边界
                        mx, my, mw, mh = gx, gy, gw, gh

                except Exception as e:
                    self.log(f"获取窗口坐标失败: {e}")

                time.sleep(1.0)
                return True

        except Exception as e:
            self.log(f"检查进程异常: {e}")
            return False

        return False

    def restart_game_and_boot(self, force_test=False):
        # 除非点击了测试按钮(force_test)，否则检查设置里是否允许自动重启
        if not force_test:
            auto_restart = getattr(self, "var_auto_restart", None)
            if auto_restart is None or not auto_restart.get():
                self.log("未开启自动重启，任务结束。")
                return False

        self.log("触发启动机制！正在拉起游戏...")
        try:
            cmd_widget = getattr(self, "le_restart_cmd", None)
            cmd_str = cmd_widget.get() if cmd_widget else self.config.get("restart_cmd", "start steam://run/2483190")
            os.system(cmd_str)
        except Exception as e:
            self.log(f"执行启动命令失败: {e}")
            return False

        self.log("等待游戏进程出现 (最多60秒)...")
        process_found = False
        for _ in range(120):
            if hasattr(self, "check_pause"): self.check_pause()
            if not self.is_running: return False
            if self.check_and_focus_game():
                process_found = True
                break
            time.sleep(1)

        if not process_found:
            self.log("未检测到游戏进程，启动失败。")
            return False

        self.log("游戏进程已启动，进入动态识别阶段 (限制5分钟)...")
        start_time = time.time()

        passed_screen_1 = False      # 记录是否已经按过画面1的回车
        last_continue_time = 0       # 记录最后一次看到/点击“继续按钮”的时间戳

        while self.is_running and time.time() - start_time < 300:
            if hasattr(self, "check_pause"): self.check_pause()

            # ==============================
            # 画面1：寻找左下角 horizon6.png -> 按回车
            # ==============================
            if not passed_screen_1:
                pos_h6 = None

                # 策略A：透明图识别
                pos_h6 = self.find_image_transparent("horizon6.png", region=self.regions["全界面"], threshold=0.60, fast_mode=False)

                # 策略B：边缘轮廓识别兜底！
                if not pos_h6:
                    try:
                        screen_bgr = self.capture_region(self.regions["全界面"])
                        tpl_bgr, _ = self.load_template("horizon6.png")
                        if tpl_bgr is not None:
                            screen_edge = self.to_edge_image(screen_bgr)
                            tpl_edge = self.to_edge_image(tpl_bgr)

                            for scale in self.get_scales_to_try(fast_mode=False):
                                t_e = tpl_edge if scale == 1.0 else cv2.resize(tpl_edge, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                                h, w = t_e.shape[:2]
                                if h > screen_edge.shape[0] or w > screen_edge.shape[1] or h < 5 or w < 5: continue

                                res = cv2.matchTemplate(screen_edge, t_e, cv2.TM_CCOEFF_NORMED)
                                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                                if max_val >= 0.40:
                                    self.log(f"[轮廓黑科技] 无视背景命中！得分: {max_val:.2f} 缩放: {scale:.2f}")
                                    pos_h6 = (max_loc[0] + w//2 + self.regions["全界面"][0], max_loc[1] + h//2 + self.regions["全界面"][1])
                                    break
                    except Exception:
                        pass

                if pos_h6:
                    self.log("✅ 成功识别到 画面1 (horizon6.png)，按下【回车键】...")
                    time.sleep(1)
                    for _ in range(2):
                        self.hw_press("enter")
                        time.sleep(1)
                    passed_screen_1 = True
                    # 激活画面2的倒计时机制，如果在后续的寻找中一直没看到画面2，也会在30秒后尝试进菜单
                    last_continue_time = time.time()
                    self.log("已确认画面1，强制等待 10 秒等待画面2加载...")
                    time.sleep(10) # 等待10秒
                    continue
                else:
                    self.log("未找到画面1。正在使用全比例深度扫描...")

            # ==============================
            # 画面2：寻找右下角 continue-b 或 continue-w -> 死磕点击
            # ==============================
            # 只有在通过了画面1的前提下，才去寻找画面2
            if passed_screen_1:
                pos_continue = self.find_any_image_gray(["continue-b.png", "continue-w.png"], threshold=0.75)
                if pos_continue:
                    self.log("识别到 画面2 (继续按钮)，进行点击...")
                    self.game_click(pos_continue)

                    # 【核心逻辑】：只要点击了，就刷新时间戳！
                    last_continue_time = time.time()

                    time.sleep(3.0) # 点击后过3秒再试，只要有就继续点
                    continue

                # ==============================
                # 状态转化：进入漫游与菜单呼出
                # ==============================
                # 如果当前时间 距离【最后一次点击画面2的时间】已经超过了 30秒，且期间再也没找到过
                time_since_last_seen = time.time() - last_continue_time
                if time_since_last_seen >= 30.0:
                    self.log("✅ 已经连续 30 秒未再发现继续按钮，判定为漫游载入完毕！开始尝试进入菜单...")

                    if getattr(self, "enter_menu")():
                        self.log("🎉 验证成功：已成功进入游戏主菜单！启动流程完美结束。")
                        return True
                    else:
                        self.log("普通进入菜单失败(可能还在黑屏或有新弹窗)，重置 30秒倒计时，继续观察...")
                        # 如果没进成功，重置时间戳，脚本会继续找画面2，或者再等30秒重试进菜单
                        last_continue_time = time.time()

            time.sleep(1.0) # 每次总循环休息1秒，防止CPU占用过高

        self.log("自动启动超时(5分钟)，放弃抢救。")
        return False

    def handle_vramne_restart(self):
        self.log("!!! 检测到 VRAMNE.png。已禁用强杀游戏进程，脚本将停止并交由人工处理。")
        return False


    def check_vramne_during_race(self):
        try:
            pos_vram = self.find_image_gray(
                "VRAMNE.png",
                region=self.regions["全界面"],
                threshold=0.70,
                fast_mode=True
            )
            if pos_vram:
                return self.handle_vramne_restart()
            return None
        except Exception as e:
            self.log(f"检测到显存不足: {e}")
            return None
    def attempt_recovery(self):
        self.log("任务执行异常中断，准备执行断点恢复流程...")
        if not self.check_and_focus_game():
            # 游戏没开或者进程没了，直接走重启流程
            if not self.restart_game_and_boot():
                return False
        else:
            # 进程还在，使用【高级状态机】尝试动态退回
            if not self.advanced_enter_menu():
                self.log("高级动态退回失败。已禁用强杀游戏进程，停止脚本并保留游戏运行状态。")
                return False
        self.log("环境重置成功！即将从中断处继续剩余任务。")
        return True

    def wait_for_freeroam(self):
        self.log("验证漫游状态...")
        for i in range(100):
            if not self.is_running:
                return False

            if self.find_image("anna.png", region=self.regions["左下"], threshold=0.5):
                self.log("验证成功：已确认处于游戏漫游界面。")
                return True

            self.log(f"重试返回漫游界面({i + 1}/100)")
            self.hw_press("esc")

            for _ in range(20):
                if not self.is_running:
                    return False
                time.sleep(0.1)

        self.log("多次尝试验证漫游界面失败，尝试进入菜单。")
        return True

    def recover_to_menu(self):
        self.log("开始尝试退回主菜单...")
        return self.enter_menu()

    def is_in_menu(self):
        return self.find_image_gray(
            "collectionjournal.png",
            region=self.regions["全界面"],
            threshold=0.66,
            fast_mode=False,
            invert_mode=True,
        )
    def enter_menu(self):
        self.log("正在尝试进入主菜单...")
        # 连续尝试 60 次，大概花费 40~60 秒
        for i in range(60):
            if not self.is_running:
                return False


            pos_menu = self.find_image_gray(
                "collectionjournal.png",
                region=self.regions["全界面"],
                threshold=0.66,
                fast_mode=False,
                invert_mode=True,
            )

            if pos_menu:
                self.log(f"成功定位到菜单锚点！({i + 1}/60)")
                time.sleep(0.5)
                return True

            self.log(f"未在主菜单... ({i + 1}/60)")
            self.hw_press("esc")
            # 给游戏一点动画加载时间
            time.sleep(1.0)

        self.log("60 次尝试均未进入菜单，请检查游戏状态。")
        return False
    def advanced_enter_menu(self):
        """
        高级状态机退回：专门用于故障恢复。
        能够识别中途的特定弹窗、中间过渡画面，并执行点击，没找到目标才按 ESC。
        """
        self.log("正在使用【高级恢复模式】尝试退回主菜单...")

        # ==========================================
        # 动态读取 images/obstacles/ 里的所有图片
        # ==========================================
        obstacles_dir = os.path.join("images", "obstacles")
        dynamic_obstacles = []

        # 检查文件夹是否存在
        if os.path.exists(obstacles_dir):
            for file in os.listdir(obstacles_dir):
                # 只要是 png 或 jpg 格式的图片，统统加进来
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    # 拼成 "obstacles/文件名.png"，这样 find_any_image_gray 就能正确找到路径
                    dynamic_obstacles.append(f"obstacles/{file}")

        if not dynamic_obstacles:
            self.log("提示：images/obstacles/ 文件夹为空或不存在，将只使用 ESC 退回。")
        # 连续尝试 80 次，处理较长的随机过程
        for i in range(80):
            if hasattr(self, "check_pause"): self.check_pause() # 兼容暂停功能
            if not self.is_running:
                return False

            # 1. 终极判断：是不是已经在菜单了？
            if self.is_in_menu():
                self.log(f"成功定位到菜单锚点！(尝试次数: {i + 1})")
                time.sleep(0.5)
                return True

            # 2. 致命错误排查 (检测到显存不足，强制休息 10 分钟)
            if self.find_image_gray("VRAMNE.png", region=self.regions["全界面"], threshold=0.75, fast_mode=True):
                self.log("!!! 严重警告: 检测到显存不足 (VRAMNE.png) 报错！")
                self.log("已禁用强杀游戏进程，停止恢复流程并交由人工处理。")
                return False

            # 3. 动态扫描所有可能的弹窗 / 需要点击的中间图片
            pos_obs = self.find_any_image_gray(dynamic_obstacles, region=self.regions["全界面"], threshold=0.75, fast_mode=True)
            if pos_obs:
                self.log(f"退回途中检测到已知图片/弹窗，点击推进... ({i+1}/80)")
                self.game_click(pos_obs)
                time.sleep(1.5) # 给画面跳转留出动画时间
                continue # 点击后，跳过本轮，不要按 ESC

            # 4. 如果既没进菜单，也没看到特定的图片，说明处于常规界面，按 ESC 退回
            self.log(f"未在主菜单且无已知特定图片，按下 ESC... ({i + 1}/80)")
            self.hw_press("esc")
            time.sleep(1.2) # 给游戏一点动画加载时间

        self.log("80 次动态尝试均未进入菜单，高级退回失败。")
        return False
    # ==========================================
    # --- 图像寻找 ---
    # ==========================================
    def logic_race(self, target_count):
        if self.race_counter >= target_count:
            return True

        self.update_running_ui("循环跑图", self.race_counter, target_count)

        self.log("准备验证/进入菜单...")
        if not self.enter_menu():
            return False

        self.log("切换到创意中心...")
        for _ in range(4):
            self.hw_press("pagedown", delay=0.15)
            time.sleep(0.3)

        time.sleep(0.8)


        pos_el = self.wait_for_image_gray(
            "eventlab.png",
            region=self.regions["全界面"],
            threshold=0.7,
            timeout=5,
            interval=0.25,
            fast_mode=True
        )

        if not pos_el:
            self.log("未找到 eventlab")
            return False

        self.game_click(pos_el)

        pos_yg = self.wait_for_image_gray(
            "playenent.png",
            region=self.regions["中间"],
            threshold=0.75,
            timeout=40,
            interval=0.3,
            fast_mode=True
        )
        if not pos_yg:
            self.log("未找到游玩赛事")
            return False

        self.game_click(pos_yg)
        time.sleep(1.5)    #点击游玩赛事后的延时

        self.hw_press("backspace")
        time.sleep(0.8)
        self.hw_press("up")
        time.sleep(0.4)
        self.hw_press("enter")
        pos_share_dialog = self.wait_for_image_gray(
            "sharecode-dialog.png",
            region=self.regions["中间"],
            threshold=0.72,
            timeout=8.0,
            interval=0.25,
            fast_mode=False
        )
        if not pos_share_dialog:
            self.log("未找到蓝图共享代码输入框")
            return False

        code_text = "".join(c for c in self.entry_share.get() if c.isdigit())
        for char in code_text:
            if not self.is_running:
                return False
            if char in DIK_CODES:
                self.hw_press(char, delay=0.05)
                time.sleep(0.05)

        time.sleep(0.4)
        self.hw_press("enter")
        time.sleep(0.8)
        self.hw_press("down")  # 蓝图输入并回车后，向下定位到确认按钮
        time.sleep(0.3)
        self.hw_press("enter")
        self.log("搜索蓝图中")
        blueprint_result = None
        blueprint_wait_deadline = time.time() + 20
        blueprint_last_wait_log = 0.0
        while self.is_running and time.time() < blueprint_wait_deadline:
            now = time.time()
            if now - blueprint_last_wait_log >= 2.0:
                remaining = max(0.0, blueprint_wait_deadline - now)
                self.log(f"蓝图搜索结果待确认，继续等待... 剩余 {remaining:.1f}s")
                blueprint_last_wait_log = now

            if self.find_image_gray(
                "racenotfound.png",
                region=self.regions["全界面"],
                threshold=0.70,
                fast_mode=False,
                invert_mode=True,
            ):
                return self.abort_invalid_blueprint_and_back_to_roam()

            blueprint_result = self.find_image_gray(
                "VEI.png",
                region=self.regions["下"],
                threshold=0.70,
                fast_mode=False,
                invert_mode=True,
            )
            if blueprint_result:
                self.log("已识别到目标赛事信息")
                break

            time.sleep(0.25)

        if not blueprint_result:
            return self.abort_invalid_blueprint_and_back_to_roam()

        self.hw_press("enter")  #识别到蓝图后enter进入蓝图
        time.sleep(1.0)
        self.hw_press("enter")  #点击单人比赛方式
        time.sleep(2.0)

        pos_target = self.find_skill_car_with_like_tag(
            region=self.regions["全界面"],
            timeout=2.0,
            interval=0.25
        )

        if not pos_target:
            self.log("未找到带 liketag 的目标车辆，重新选品牌...")
            self.hw_press("backspace")
            time.sleep(1.2)

            found_brand = False
            for _ in range(3):
                if not self.is_running:
                    return False

                pos_brand = self.wait_for_image_gray("skillcarbrand.png", region=self.regions["全界面"], threshold=0.8, timeout=1.2, interval=0.2, fast_mode=True)
                if pos_brand:
                    self.game_click(pos_brand)
                    time.sleep(1.2)
                    found_brand = True
                    break

                self.hw_press("up")
                time.sleep(0.4)

            if not found_brand:
                self.log("三次尝试未找到刷图车辆品牌。")
                return False

            for _ in range(20):
                if not self.is_running:
                    return False

                pos_target = self.find_skill_car_with_like_tag(
                    region=self.regions["全界面"],
                    timeout=2.0,
                    interval=0.25
                )
                if pos_target:
                    break

                for _ in range(4):
                    self.hw_press("right", delay=0.08)
                    time.sleep(0.08)
                time.sleep(0.4)

        if not pos_target:
            self.log("翻页未能找到带有 liketag 的刷图车辆！")
            return False

        self.game_click(pos_target)
        time.sleep(0.5)
        self.hw_press("enter")
        start_ready = self.wait_for_any_image_gray(
            ["start.png", "startw.png"],
            region=self.regions["左下"],
            threshold=0.75,
            timeout=4.0,
            interval=0.2,
            fast_mode=True,
        )
        if start_ready:
            self.log("已提前识别到赛事起点入口，继续跑图流程。")

        self.log("前置完成，开始循环跑图！")

        while self.race_counter < target_count:
            if not self.is_running:
                return False

            self.log(f"跑图 {self.race_counter + 1}/{target_count}: 找赛事起点...")

            pos = None
            for _ in range(120):
                if not self.is_running:
                    return False

                pos = self.wait_for_any_image_gray(
                    ["start.png", "startw.png"],
                    region=self.regions["左下"],
                    threshold=0.75,
                    timeout=0.7,
                    interval=0.2,
                    fast_mode=True
                )
                if pos:
                    break

                self.hw_press("down")
                time.sleep(0.25)

            if not pos:
                self.log("找不到赛事起点，退出跑图。")
                return False

            self.game_click(pos)
            time.sleep(4.0)
            self.hw_key_down("w")
            self.hw_key_down("up")

            # 初始化各类计时器
            race_start_time = time.time()  # 新增：记录跑图发车时间
            last_like_chk = time.time()
            last_chk = 0
            finished = False
            timeout_triggered = False      # 新增：标记是否触发了120秒超时

            driving_keys_held = True # <--- 【新增】标记油门状态
            try:
                race_timeout = max(60, int(self.config.get("race_timeout", 300)))
            except Exception:
                race_timeout = 300

            while self.is_running:
                # ====== 【新增】跑图专用暂停处理逻辑 ======
                if self.is_paused:
                    if driving_keys_held: # 刚进入暂停，松开油门
                        self.hw_key_up("w")
                        self.hw_key_up("up")
                        driving_keys_held = False
                    self.check_pause() # 阻塞在此处
                    # 从暂停中恢复，如果还没跑完，重新按下油门
                    if self.is_running:
                        self.hw_key_down("w")
                        self.hw_key_down("up")
                        driving_keys_held = True

                    # 避免恢复瞬间触发超时，重置计时器
                    race_start_time = time.time()
                    last_like_chk = time.time()
                    last_chk = time.time()
                    continue
                # =========================================
                now = time.time()

                # 【新增逻辑】：超时防卡死检测
                if now - race_start_time > race_timeout:
                    self.log(f"跑图超时(已超过{race_timeout}秒)！触发强制重开赛事逻辑...")
                    timeout_triggered = True
                    break

                # 每隔3秒处理一次跑图中的特殊界面/异常
                if now - last_like_chk >= 3.0:
                    vram_result = self.check_vramne_during_race()
                    if vram_result is True:
                        self.log("VRAM恢复完成，结束当前跑图流程，交给外层重新恢复。")
                        return False
                    elif vram_result is False:
                        self.log("VRAM恢复失败。")
                        return False
                    if self.handle_author_prompt(release_drive_keys=True):
                        if not self.is_running:
                            return False
                        self.hw_key_down("w")
                        self.hw_key_down("up")
                        driving_keys_held = True
                    last_like_chk = now

                # 每1秒检测一次重新开始(正常完赛)
                if now - last_chk >= 1.0:
                    found_restart = self.find_image_gray("restart.png", region=self.regions["下"], threshold=0.75, fast_mode=True)
                    if found_restart:
                        finished = True
                        break
                    last_chk = now

                time.sleep(0.3)

            # 无论正常结束还是超时，都必须先松开油门和方向
            self.hw_key_up("w")
            self.hw_key_up("up")

            if not self.is_running:
                return False

            self.handle_author_prompt(release_drive_keys=False)
            if not self.is_running:
                return False

            # ====== 【新增】：执行超时重置操作 ======
            if timeout_triggered:
                time.sleep(0.5)
                self.hw_press("esc")
                time.sleep(1.5)  # 等待菜单动画加载

                # 寻找并点击 restarta.png
                pos_restarta = self.wait_for_image_gray("restarta.png", region=self.regions["全界面"], threshold=0.70, timeout=4.0, interval=0.3, fast_mode=True)
                if pos_restarta:
                    self.log("找到 restarta.png，点击重开赛事...")
                    self.game_click(pos_restarta)
                    time.sleep(1.0)
                    self.hw_press("enter")  # 地平线重开赛事通常有确认弹窗，按一次回车确认
                    time.sleep(4.0)         # 等待黑屏重加载动画
                else:
                    self.log("未找到 restarta.png，尝试直接继续...")

                # 【关键】：直接跳过下方的结算流程，回到最外层 while 重新找 start.png（并且本次不计入 race_counter）
                continue
            # ========================================

            if not finished:
                return False

            self.handle_author_prompt(release_drive_keys=False)
            if not self.is_running:
                return False

            if self.race_counter == target_count - 1:
                self.hw_press("enter")
                time.sleep(2.0)
                self.handle_author_prompt(release_drive_keys=False)
            else:
                self.hw_press("x")
                time.sleep(0.8)
                self.handle_author_prompt(release_drive_keys=False)
                self.hw_press("enter")
                time.sleep(2.0)
                self.handle_author_prompt(release_drive_keys=False)

            self.race_counter += 1
            self.update_running_ui("循环跑图", self.race_counter, target_count)

        return True

    def abort_invalid_blueprint_and_back_to_roam(self):
        self.invalid_blueprint_abort = True
        self.log("该蓝图已失效")
        for _ in range(3):
            if not self.is_running:
                return False
            self.hw_press("esc")
            time.sleep(0.35)
        return False

    def handle_author_prompt(self, release_drive_keys=False):
        pos_author = self.find_any_image_gray(
            ["likeauthor.png", "dislikeauthor.png"],
            region=self.regions["全界面"],
            threshold=0.68,
            fast_mode=False,
            invert_mode=True,
        )
        if not pos_author:
            return False

        if release_drive_keys:
            self.hw_key_up("w")
            self.hw_key_up("up")

        self.log("识别到作者评价界面，执行确认跳过。")
        for _ in range(2):
            if not self.is_running:
                return True
            self.hw_press("enter")
            time.sleep(0.35)
        time.sleep(0.8)
        return True

    # ==========================================
    # --- 模块：买车 ---
    # ==========================================
    def logic_buy_car(self, target_count):
        if self.car_counter >= target_count:
            return True

        self.update_running_ui("批量买车", self.car_counter, target_count)

        self.log("准备验证/进入菜单...")
        if not self.enter_menu():
            return False

        pos_collectionjournal = self.wait_for_image_transparent(
            "collectionjournal.png",
            region=self.regions["左"],
            threshold=0.7,
            timeout=30,
            interval=0.4,
            fast_mode=True
        )
        if not pos_collectionjournal:
            self.log("未找到收集簿")
            return False

        self.game_click(pos_collectionjournal, double=True)
        time.sleep(1.0)


        pos_masterexplorer = self.wait_for_image(
            "masterexplorer.png",
            region=self.regions["全界面"],
            threshold=0.75,
            timeout=30,
            interval=0.4,
            fast_mode=True
        )
        if not pos_masterexplorer:
            self.log("未找到探索")
            return False

        self.game_click(pos_masterexplorer, double=True)
        time.sleep(0.6)

        pos_carcollection = self.wait_for_image_transparent(
            "carcollection.png",
            region=self.regions["全界面"],
            threshold=0.75,
            timeout=30,
            interval=0.3,
            fast_mode=True
        )
        if not pos_carcollection:
            self.log("未找到车辆收集")
            return False

        self.game_click(pos_carcollection, double=True)
        time.sleep(1.0)

        self.hw_press("backspace")
        time.sleep(0.5)

        brand_pos = None
        for _ in range(5):
            if not self.is_running:
                return False


            brand_pos = self.wait_for_any_image_gray(
                ["CCbrand.png"],
                region=self.regions["全界面"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if brand_pos:
                break

            self.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            self.log("未找到品牌")
            return False

        self.game_click(brand_pos)
        time.sleep(0.8)
        self.hw_press("down")
        time.sleep(0.4)

        pos_22b = self.wait_for_image(
            "consumablecar.png",
            region=self.regions["全界面"],
            threshold=0.90,
            timeout=8,
            interval=0.3,
            fast_mode=False
        )
        if not pos_22b:
            self.log("未找到消耗品车辆")
            return False

        self.game_click(pos_22b, double=True)
        time.sleep(1.0)

        while self.car_counter < target_count:
            if not self.is_running:
                return False

            self.hw_press("space")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("down")
            time.sleep(0.2)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.6)
            self.move_to_game_coord(5, 5)
            self.hw_press("enter")
            time.sleep(0.7)

            self.car_counter += 1
            self.update_running_ui("批量买车", self.car_counter, target_count)

        for _ in range(5):
            if not self.is_running:
                return False
            self.hw_press("esc")
            time.sleep(0.8)

        return True
    # ==========================================
    # --- 模块：抽奖 ---
    # ==========================================
    def enter_design_paint_choose_car(self):
        pos_designpaint = self.wait_for_any_image_gray(
            ["designpaint-w.png", "designpaint-b.png"],
            region=self.regions["全界面"],
            threshold=0.62,
            timeout=10,
            interval=0.25,
            fast_mode=False
        )
        if not pos_designpaint:
            self.log("[CJ] 未找到设计与涂装按钮。")
            return False

        self.game_click(pos_designpaint)
        time.sleep(1.0)

        pos_choosecar = self.wait_for_any_image_gray(
            ["choosecar.png", "choosecar-b.png"],
            region=self.regions["全界面"],
            threshold=0.62,
            timeout=2,
            interval=0.25,
            fast_mode=False
        )
        if not pos_choosecar:
            self.log("[CJ] 未找到选车按钮。")
            self.hw_press("enter")
            time.sleep(1.5)
            pos_choosecar = self.wait_for_any_image_gray(
                ["choosecar.png", "choosecar-b.png"],
                region=self.regions["全界面"],
                threshold=0.62,
                timeout=10,
                interval=0.25,
                fast_mode=False
            )
        if not pos_choosecar:
            self.log("[CJ] 未找到 choosecar 按钮。")
            return False

        self.game_click(pos_choosecar)
        time.sleep(1.5)
        return True

    def select_new_consumable_car_from_list(self):
        self.hw_press("backspace")
        time.sleep(1.0)

        brand_pos = None
        for _ in range(30):
            if not self.is_running:
                return False

            brand_pos = self.wait_for_any_image_gray(
                ["CCbrand.png"],
                region=self.regions["全界面"],
                threshold=0.75,
                timeout=0.8,
                interval=0.2,
                fast_mode=True
            )
            if brand_pos:
                break

            self.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            self.log("选品牌失败")
            return False

        self.game_click(brand_pos)
        time.sleep(1.0)
        smart_page_enabled = bool(self.config.get("smart_page", False))
        jump_pages = max(0, self.memory_car_page - 1) if smart_page_enabled else 0

        if jump_pages > 0:
            self.log(f"智能记忆触发：快速跳过前 {jump_pages} 页...")
            for _ in range(jump_pages):
                if not self.is_running:
                    return False
                for _ in range(4):
                    self.hw_press("right", delay=0.06)
                    time.sleep(0.1)
                time.sleep(0.15)

        found_car = False
        current_page = jump_pages

        for _ in range(85 - jump_pages):
            if not self.is_running:
                return False
            pos_target = self.wait_for_new_consumable_car_strict(timeout=1.5, interval=0.2)

            if pos_target:
                self.game_click(pos_target)
                found_car = True
                if smart_page_enabled:
                    self.memory_car_page = current_page
                    self.log(f"锁定目标车辆！已记录当前页码: {current_page}")
                else:
                    self.log("锁定目标车辆！")
                break

            for _ in range(4):
                self.hw_press("right", delay=0.06)
                time.sleep(0.1)
            time.sleep(0.4)
            current_page += 1

        if not found_car:
            self.log("列表中未找到目标车辆。")
            if smart_page_enabled:
                self.log("已重置智能记忆页码。")
                self.memory_car_page = 0
            return False

        time.sleep(1.2)
        return True

    def logic_super_wheelspin(self, target_count):
        if self.cj_counter >= target_count:
            return True

        self.update_running_ui("超级抽奖", self.cj_counter, target_count)
        # 【新增】：初始化记忆页码
        if not hasattr(self, 'memory_car_page'):
            self.memory_car_page = 0
        self.log("准备验证/进入菜单...")
        if not self.enter_menu():
            return False

        self.log("进入车辆与收藏...")
        self.hw_press("pagedown", delay=0.15)
        time.sleep(1.0)

        pos_buycar = self.wait_for_buy_and_used_car(timeout=15)
        if not pos_buycar:
            self.log("未识别到【购买新车与二手车】")
            return False

        self.game_click(pos_buycar)
        time.sleep(0.8)
        self.hw_press("enter")

        pos_bs = self.wait_for_any_image_gray(
            ["buyandsell-w.png", "buyandsell-b.png"],
            region=self.regions["全界面"],
            threshold=0.70,
            timeout=15,
            interval=0.3,
            fast_mode=False,
            invert_mode=True,
        )
        if not pos_bs:
            self.log("嘉年华内信息未成功识别")
            return False

        # 进入嘉年华界面后
        self.hw_press("pagedown", delay=0.15)
        self.log("进入车辆界面...")
        time.sleep(0.5)

        while self.cj_counter < target_count:
            if not self.is_running:
                return False
            self.log("通过 designpaint 进入选择车辆界面.")
            if not self.enter_design_paint_choose_car():
                return False
            if not self.select_new_consumable_car_from_list():
                return False
            time.sleep(1.2)
            self.log("尝试寻找'上车'按钮...")

            pos_rc = None
            pos_rc = self.wait_for_image_gray("rc.png", region=self.regions["全界面"], threshold=0.70, timeout=0.5, interval=0.1, fast_mode=True)

            if pos_rc:
                self.log("点击上车")
                self.game_click(pos_rc)
            else:
                self.log("回车上车")
                self.hw_press("enter")
                time.sleep(1.0)
                self.hw_press("enter")
                time.sleep(1.0)

            pos_spraycar = self.wait_for_image_gray(
                "spraycar-w.png",
                region=self.regions["左"],
                threshold=0.68,
                timeout=4.0,
                interval=0.2,
                fast_mode=False,
                invert_mode=True,
            )
            if not pos_spraycar:
                self.log("上车后未确认进入喷漆车辆页面")
                return False

            self.log("已确认喷漆车辆页面，按 ESC 返回车辆菜单...")
            self.hw_press("esc")

            pos_vehicle_menu = self.wait_for_image_gray(
                "designpaint-w.png",
                region=self.regions["左"],
                threshold=0.68,
                timeout=2.0,
                interval=0.15,
                fast_mode=False,
                invert_mode=True,
            )
            if not pos_vehicle_menu:
                pos_vehicle_menu = self.wait_for_image_gray(
                    "designpaint-b.png",
                    region=self.regions["左"],
                    threshold=0.68,
                    timeout=1.0,
                    interval=0.15,
                    fast_mode=False,
                    invert_mode=True,
            )
            if not pos_vehicle_menu:
                self.log("ESC 后未确认返回车辆菜单")
                return False

            menu_stable_deadline = time.time() + 0.8
            while self.is_running and time.time() < menu_stable_deadline:
                menu_stable = self.find_any_image_gray(
                    ["designpaint-w.png", "designpaint-b.png"],
                    region=self.regions["左"],
                    threshold=0.68,
                    fast_mode=False,
                    invert_mode=True,
                )
                if not menu_stable:
                    menu_stable_deadline = time.time() + 0.25
                time.sleep(0.08)

            self.log("车辆菜单已稳定，使用方向键定位到升级与调校...")
            self.hw_press("up", delay=0.05)
            time.sleep(0.2)
            self.hw_press("enter")
            time.sleep(0.5)

            pos_cls = self.wait_for_any_image_gray(
                ["clsldcnw.png", "clsldcnb.png"],
                region=self.regions["全界面"],
                threshold=0.62,
                timeout=8,
                interval=0.25,
                fast_mode=False
            )
            if not pos_cls:
                self.log("未找到车辆专精")
                return False
            self.game_click(pos_cls)
            time.sleep(1.2)

            pos_exp = self.wait_for_any_image(
                ["EXPwU.png"],
                region=self.regions["左"],
                threshold=0.75,
                timeout=1.5,
                interval=0.3,
                fast_mode=True
            )

            if pos_exp:
                self.log("该车辆技能已点过，跳过计数")
            else:
                time.sleep(1.0)
                self.hw_press("enter")
                time.sleep(1.5)

                spne_found = None
                for dk in self.config["skill_dirs"]:
                    if not self.is_running:
                        return False
                    self.hw_press(dk)
                    time.sleep(0.2)
                    self.hw_press("enter")
                    time.sleep(1.2)
                    spne_found = self.wait_for_image_gray(
                        "SPNE.png",
                        region=self.regions["全界面"],
                        threshold=0.66,
                        timeout=0.8,
                        interval=0.15,
                        fast_mode=False,
                        invert_mode=True,
                    )
                    if spne_found:
                        break

                if spne_found:
                    self.log("技能点不足，提前结束专精环节！")
                    time.sleep(1.0)
                    self.hw_press("enter")
                    time.sleep(0.8)
                    self.hw_press("esc")
                    time.sleep(1.0)
                    self.hw_press("esc")
                    time.sleep(1.0)
                    if self.should_switch_skillcar_after_cj():
                        if not self.prepare_skillcar_for_next_race_after_cj():
                            return False
                    else:
                        self.hw_press("esc")
                        time.sleep(1.0)
                    return True
                self.cj_counter += 1
                self.update_running_ui("超级抽奖", self.cj_counter, target_count)

            if not self.return_to_vehicle_menu_after_mastery():
                return False
        if self.should_switch_skillcar_after_cj():
            if not self.prepare_skillcar_for_next_race_after_cj():
                return False
        else:
            self.hw_press("esc")
            time.sleep(1.2)
            self.hw_press("esc")
            time.sleep(1.2)
        return True
if __name__ == "__main__":
    app = FH_UltimateBot()
    app.mainloop()
