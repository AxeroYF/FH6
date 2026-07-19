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
try:
    from pynput import keyboard
except Exception:
    keyboard = None
import win32gui
import threading

from image_matcher import ImageMatcherMixin
from background_mouse import WindowMouseManager
from background_capture import WindowCaptureManager
from background_keyboard import WindowKeyboardManager
from mouse_isolation import MouseIsolationOverlay
from developer_ui_editor import apply_saved_text_overrides, open_developer_text_editor
from flow_buy import logic_buy_car as flow_logic_buy_car
from flow_delete import logic_delete_car as flow_logic_delete_car
from flow_cj import (
    cleanup_recent_template_car_miss as flow_cleanup_recent_template_car_miss,
    enter_design_paint_choose_car as flow_enter_design_paint_choose_car,
    find_new_consumable_car_with_ai as flow_find_new_consumable_car_with_ai,
    find_yolo_car_candidate as flow_find_yolo_car_candidate,
    get_yolo_car_select_model as flow_get_yolo_car_select_model,
    logic_super_wheelspin as flow_logic_super_wheelspin,
    preload_ai_model_async as flow_preload_ai_model_async,
    resolve_ai_device as flow_resolve_ai_device,
    resolve_ai_model_path as flow_resolve_ai_model_path,
    save_ai_car_debug as flow_save_ai_car_debug,
    save_template_car_debug as flow_save_template_car_debug,
    select_new_consumable_car_from_list as flow_select_new_consumable_car_from_list,
    yolo_box_distance as flow_yolo_box_distance,
    yolo_box_to_dict as flow_yolo_box_to_dict,
    yolo_yellow_tag_ratio as flow_yolo_yellow_tag_ratio,
)
from flow_race import (
    abort_invalid_blueprint_and_back_to_roam as flow_abort_invalid_blueprint_and_back_to_roam,
    handle_author_prompt as flow_handle_author_prompt,
    logic_race as flow_logic_race,
)

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

DEFAULT_BUY_CJ_VEHICLE_PRICES = {
    "subaru": 330000,
    "mazda": 95000,
}

DEFAULT_SKILL_DIRS_BY_VEHICLE = {
    "subaru": ["right", "up", "up", "up", "left"],
    "mazda": ["right", "right", "up", "up", "up"],
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
        self.geometry("1240x800")
        self.minsize(1120, 760)
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
        self.game_hwnd = None
        self.background_mouse = None
        self.background_capture = None
        self.background_keyboard = None
        self.mouse_isolation_overlay = None
        self._mouse_isolation_dismissed_for_run = False
        self._background_attach_lock = threading.RLock()
        self._background_preload_started = False
        self._background_preload_announced = False

        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.delete_counter = 0
        self.delete_counter = 0
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
        self.expanded_window_height = 800
        self.invalid_blueprint_abort = False
        self.strict_car_debug_seq = 0
        self.strict_car_debug_last_miss_save = 0.0
        self.ai_car_debug_seq = 0
        self.ai_car_debug_last_miss_save = 0.0
        self.yolo_car_select_model = None
        self.yolo_car_select_model_path = None
        self.yolo_car_select_model_lock = threading.Lock()
        self.ai_model_preload_started = False
        self._developer_editor_window = None
        self._developer_f9_last_time = 0.0
        self.race_notice_shown = False
        self.diagnostic_trace = None
        self.total_car_bought = 0
        self.total_car_limit = None
        self.stop_after_cj_due_buy_limit = False
        self.init_match_calibration()

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
        self._developer_text_override_count = apply_saved_text_overrides(self)
        self.update_match_calibration_ui()
        self.start_hotkey_listener()
        self.update_skill_grid()
        self.center_window()
        self.preload_ai_model_async()
        self.after(500, self.preload_background_services_async)

        self.log("免责声明：本脚本仅供 Python 自动化技术交流与学习使用。请勿用于商业盈利或破坏游戏平衡，因使用本脚本造成的账号封禁等损失，由使用者自行承担。")
        self.log("默认刷图车辆：【斯巴鲁22b，调校代码325360351】【等级R-917】【保持原厂涂装】【收藏车辆】")
        self.log("蓝图代码可自行修改,工具运行目录不要有中文。")
        self.log("游戏设置为【自动转向】【手动挡】，游戏语言设置为【简体中文】")
        self.log("【设置】-【抬头显示与游戏】，关闭【技术】和【失去焦点时暂停】")
        self.log("大部分以图像识别作为引导，减少机器盲目操作的风险，但仍无法完全避免，使用前请做好准备。")

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
            "删除车辆": 0.0,
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
        self.match_window_info = {
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "aspect": round((w / h), 4) if h else 0.0,
        }
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

    def init_match_calibration(self):
        self.match_calibration = {
            "state": "idle",
            "status": "未校准",
            "detail": "等待游戏窗口",
            "preferred_scale": 1.0,
            "gray_threshold_offset": 0.0,
            "edge_bias": 0.0,
            "sharpness": 0.0,
            "brightness": 0.0,
            "anchor": "",
            "anchor_score": 0.0,
            "window_signature": None,
            "updated_at": 0.0,
        }

    def update_match_calibration_ui(self):
        calib = getattr(self, "match_calibration", {})
        state = calib.get("state", "idle")
        status = calib.get("status", "未校准")
        detail = calib.get("detail", "等待游戏窗口")
        color_map = {
            "idle": "#D29922",
            "running": "#D29922",
            "ready": "#238636",
            "fallback": "#9A6700",
            "error": "#DA3633",
        }
        color = color_map.get(state, "#D29922")

        def apply_ui():
            try:
                if hasattr(self, "lbl_calibration_status"):
                    self.lbl_calibration_status.configure(text=status, text_color=color)
                if hasattr(self, "lbl_calibration_detail"):
                    self.lbl_calibration_detail.configure(text=detail)
            except Exception:
                pass

        self.ui_call(apply_ui)

    def set_match_calibration_state(self, state, status, detail):
        self.match_calibration["state"] = state
        self.match_calibration["status"] = status
        self.match_calibration["detail"] = detail
        self.update_match_calibration_ui()

    def calibrate_match_profile(self, force=False):
        region = self.regions.get("全界面")
        if not region:
            self.set_match_calibration_state("error", "校准失败", "未获取到游戏窗口区域")
            return False

        window_signature = (int(region[2]), int(region[3]))
        prev_sig = self.match_calibration.get("window_signature")
        prev_time = float(self.match_calibration.get("updated_at", 0.0) or 0.0)
        if not force and prev_sig == window_signature and (time.time() - prev_time) < 20:
            self.update_match_calibration_ui()
            return True

        self.set_match_calibration_state("running", "校准中", f"窗口 {window_signature[0]}x{window_signature[1]}，正在分析模板缩放与清晰度")
        self.log(f"[Calibration] 开始自适应校准，窗口 {window_signature[0]}x{window_signature[1]}")

        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(screen_gray, cv2.CV_64F).var())
            brightness = float(screen_gray.mean())
            curr_w = float(window_signature[0])

            anchors = [
                "collectionjournal.png",
                "eventlab.png",
                "continue-b.png",
                "continue-w.png",
                "horizon6.png",
                "buyandsell-w.png",
                "designpaint-w.png",
                "choosecar.png",
                "rc.png",
            ]
            scale_candidates = []
            for s in [
                1.0,
                curr_w / 1600.0,
                curr_w / 1920.0,
                curr_w / 2560.0,
                0.995,
                1.005,
                0.99,
                1.01,
                0.985,
                1.015,
                0.97,
                1.03,
                0.95,
                1.05,
            ]:
                s = round(float(s), 3)
                if 0.45 <= s <= 1.8 and s not in scale_candidates:
                    scale_candidates.append(s)
            best = None

            for template_name in anchors:
                tpl_gray_raw = self.load_template_gray(template_name)
                if tpl_gray_raw is None:
                    continue

                for scale in scale_candidates:
                    tpl_gray = tpl_gray_raw
                    if scale != 1.0:
                        tpl_gray = cv2.resize(tpl_gray_raw, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    th, tw = tpl_gray.shape[:2]
                    if th < 5 or tw < 5 or th > screen_gray.shape[0] or tw > screen_gray.shape[1]:
                        continue

                    res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                    _, score, _, _ = cv2.minMaxLoc(res)
                    if best is None or score > best["score"]:
                        best = {
                            "template": template_name,
                            "scale": float(scale),
                            "score": float(score),
                        }

            preferred_scale = 1.0
            anchor_name = "none"
            anchor_score = 0.0
            state = "fallback"
            status = "兜底模式"

            if best:
                anchor_name = best["template"]
                anchor_score = best["score"]
                if anchor_score >= 0.58:
                    preferred_scale = best["scale"]
                    state = "ready"
                    status = "已校准"

            gray_threshold_offset = 0.0
            if sharpness < 120:
                gray_threshold_offset -= 0.06
            elif sharpness < 180:
                gray_threshold_offset -= 0.04
            elif sharpness < 260:
                gray_threshold_offset -= 0.02

            if anchor_score < 0.62:
                gray_threshold_offset -= 0.02

            gray_threshold_offset = max(-0.08, min(0.02, gray_threshold_offset))
            edge_bias = 1.0 if (sharpness < 140 or brightness < 55 or brightness > 210) else 0.0

            detail = (
                f"scale={preferred_scale:.3f} | threshold={gray_threshold_offset:+.02f} | "
                f"sharp={sharpness:.0f} | anchor={anchor_name} {anchor_score:.2f}"
            )

            self.match_calibration.update({
                "state": state,
                "status": status,
                "detail": detail,
                "preferred_scale": preferred_scale,
                "gray_threshold_offset": gray_threshold_offset,
                "edge_bias": edge_bias,
                "sharpness": sharpness,
                "brightness": brightness,
                "anchor": anchor_name,
                "anchor_score": anchor_score,
                "window_signature": window_signature,
                "updated_at": time.time(),
            })
            self.update_match_calibration_ui()
            self.log(
                f"[Calibration] {status}: scale={preferred_scale:.3f}, threshold={gray_threshold_offset:+.02f}, "
                f"sharp={sharpness:.0f}, brightness={brightness:.0f}, anchor={anchor_name}, score={anchor_score:.3f}"
            )
            return True
        except Exception as e:
            self.match_calibration.update({
                "state": "error",
                "status": "校准失败",
                "detail": f"使用默认参数继续: {e}",
                "preferred_scale": 1.0,
                "gray_threshold_offset": 0.0,
                "edge_bias": 0.0,
                "window_signature": window_signature,
                "updated_at": time.time(),
            })
            self.update_match_calibration_ui()
            self.log(f"[Calibration] 校准失败，已回退默认参数: {e}")
            return False

    # ==========================================
    # --- 配置管理 ---
    # ==========================================
    def load_config(self):
        # 1. 直接使用内置字典作为“绝对底本”（最安全，无视打包丢文件问题）
        self.config = {
            "race_count": 99,
            "buy_count": 30,
            "cj_count": 30,
            "delete_count": 30,
            "chk_1": True,
            "chk_2": True,
            "chk_3": True,
            "route_cj_delete": True,
            "route_delete_race": False,
            "global_loops": 10,
            "skill_dirs": list(DEFAULT_SKILL_DIRS_BY_VEHICLE["subaru"]),
            "skill_dirs_by_vehicle": {
                key: list(value) for key, value in DEFAULT_SKILL_DIRS_BY_VEHICLE.items()
            },
            "skillcar_templates": ["skillcar_r917.png"],
            "buy_cj_vehicle": "subaru",
            "buy_cj_vehicle_prices": dict(DEFAULT_BUY_CJ_VEHICLE_PRICES),
            "share_code": "103435586",
            "cr_amount": 0,
            "auto_restart": False,
            "background_mouse_enabled": True,
            "background_capture_enabled": True,
            "background_keyboard_enabled": True,
            "compact_on_run": False,
            "restart_cmd": "start steam://run/2483190",
            "race_timeout": 300,
            "challenge_load_seconds": 15,
            "ai_assist": False,
            "ai_prefer": False,
            "ai_only": False,
            "ai_auto_capture": False,
            "diagnostic_mode": False,
            "recognition_profiles": {},
            "smart_page": False,
            "ai_model_path": "models/fh6_car_select_yolo.pt",
            "ai_model_paths": {
                "subaru": "models/fh6_car_select_yolo.pt",
                "mazda": "models/fh6_car_select_mazda_yolo.pt"
            }
        }
        ext_path = USER_CONFIG_FILE
        # 2. 读取用户的 config.json，并与底本合并（自动补全缺失项）
        user_config = {}
        if os.path.exists(ext_path):
            try:
                with open(ext_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
            except Exception as e:
                self.log(f"用户 config.json 损坏，已自动恢复默认配置。")
        self.config["ai_prefer"] = bool(self.config.get("ai_assist", False))
        if "route_cj_delete" not in user_config:
            # v4.2 曾把“抽奖→删车”错误地拆成“跑图→删车”等旧开关。
            # 升级时优先沿用已经开启的删车路线，否则兼容旧 chk_3。
            self.config["route_cj_delete"] = bool(
                user_config.get("route_race_delete", user_config.get("chk_3", True))
            )
        else:
            self.config["route_cj_delete"] = bool(self.config.get("route_cj_delete", True))
        self.config["route_delete_race"] = bool(self.config.get("route_delete_race", False))
        for obsolete_key in ("route_race_delete", "next_1", "next_2", "next_3"):
            self.config.pop(obsolete_key, None)
        selected_vehicle = str(self.config.get("buy_cj_vehicle", "subaru")).lower()
        self.config["buy_cj_vehicle"] = selected_vehicle if selected_vehicle in ("subaru", "mazda") else "subaru"
        selected_vehicle = self.config["buy_cj_vehicle"]
        configured_skill_dirs = user_config.get("skill_dirs_by_vehicle")
        normalized_skill_dirs = {
            key: list(value) for key, value in DEFAULT_SKILL_DIRS_BY_VEHICLE.items()
        }
        if isinstance(configured_skill_dirs, dict):
            for vehicle_key in normalized_skill_dirs:
                vehicle_dirs = configured_skill_dirs.get(vehicle_key)
                if isinstance(vehicle_dirs, list):
                    normalized_skill_dirs[vehicle_key] = [
                        direction for direction in vehicle_dirs
                        if direction in ("up", "down", "left", "right")
                    ]
        else:
            # 兼容旧配置：把原来的单一路径保留给当时选中的车辆，
            # 另一个车辆使用各自的新默认路径。
            legacy_dirs = self.config.get("skill_dirs")
            if isinstance(legacy_dirs, list):
                normalized_skill_dirs[selected_vehicle] = [
                    direction for direction in legacy_dirs
                    if direction in ("up", "down", "left", "right")
                ]
        self.config["skill_dirs_by_vehicle"] = normalized_skill_dirs
        self.config["skill_dirs"] = list(normalized_skill_dirs[selected_vehicle])
        configured_prices = self.config.get("buy_cj_vehicle_prices", {})
        normalized_prices = dict(DEFAULT_BUY_CJ_VEHICLE_PRICES)
        if isinstance(configured_prices, dict):
            for vehicle_key in normalized_prices:
                try:
                    configured_price = int(configured_prices.get(vehicle_key, normalized_prices[vehicle_key]))
                    if configured_price > 0:
                        normalized_prices[vehicle_key] = configured_price
                except Exception:
                    pass
        self.config["buy_cj_vehicle_prices"] = normalized_prices
        configured_model_paths = self.config.get("ai_model_paths", {})
        normalized_model_paths = {
            "subaru": "models/fh6_car_select_yolo.pt",
            "mazda": "models/fh6_car_select_mazda_yolo.pt",
        }
        if isinstance(configured_model_paths, dict):
            for vehicle_key in normalized_model_paths:
                configured_path = str(configured_model_paths.get(vehicle_key, "")).strip()
                if configured_path:
                    normalized_model_paths[vehicle_key] = configured_path
        self.config["ai_model_paths"] = normalized_model_paths

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
            if hasattr(self, "entry_delete"):
                self.config["delete_count"] = max(1, int(self.entry_delete.get()))
            self.config["global_loops"] = int(self.entry_global_loop.get())
            if hasattr(self, "entry_cr_amount"):
                self.config["cr_amount"] = max(0, int(self.entry_cr_amount.get() or 0))
            if hasattr(self, "entry_race_timeout"):
                self.config["race_timeout"] = max(60, int(self.entry_race_timeout.get()))
            self.config["share_code"] = "".join(c for c in self.entry_share.get() if c.isdigit())
            #self.config["base_width"] = int(self.entry_base_w.get())
        except Exception:
            pass

        self.config["chk_1"] = self.var_chk1.get()
        self.config["chk_2"] = self.var_chk2.get()
        self.config["chk_3"] = self.var_chk3.get()
        if hasattr(self, "var_cj_to_delete"):
            self.config["route_cj_delete"] = bool(self.var_cj_to_delete.get())
        if hasattr(self, "var_delete_to_race"):
            self.config["route_delete_race"] = bool(self.var_delete_to_race.get())
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
        if hasattr(self, "var_background_mouse"):
            self.config["background_mouse_enabled"] = bool(self.var_background_mouse.get())
        if hasattr(self, "var_compact_on_run"):
            self.config["compact_on_run"] = bool(self.var_compact_on_run.get())
        if hasattr(self, "var_buy_cj_vehicle"):
            selected_vehicle = str(self.var_buy_cj_vehicle.get() or "")
            self.config["buy_cj_vehicle"] = self.resolve_buy_cj_vehicle_mode(selected_vehicle)
        self.sync_current_skill_dirs_for_vehicle(self.config.get("buy_cj_vehicle", "subaru"))
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

    def on_flow_route_changed(self, route):
        """Persist route switches without imposing policy on the user's flow."""
        self.save_config()

    def resolve_pipeline_next_index(self, curr_idx):
        """Resolve the four fixed adjacent routes; None means stop after this module."""
        if curr_idx == 0:
            return 1 if self.var_chk1.get() else None
        if curr_idx == 1:
            return 2 if self.var_chk2.get() else None
        if curr_idx == 2:
            if not self.var_cj_to_delete.get():
                return None

            # Vehicle deletion currently supports Mazda only. When the two
            # routes around deletion are both enabled, Subaru keeps the full
            # loop intact by treating deletion as an unavailable no-op and
            # wrapping directly from wheelspin back to race.
            vehicle_mode = self.get_buy_cj_vehicle_mode()
            if vehicle_mode == "subaru" and self.var_delete_to_race.get():
                self.log(
                    "[流程] 当前为斯巴鲁方案，删除车辆仅支持 Mazda；"
                    "本轮跳过删车并进入下一轮跑图。"
                )
                return 0
            return 3
        if curr_idx == 3:
            return 0 if self.var_delete_to_race.get() else None
        return None

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
        delete_total = totals.get("删除车辆", 0.0)

        active_task = getattr(self, "active_task_name", "")
        if active_task == "循环跑图":
            race_total += task_elapsed
        elif active_task == "批量买车":
            buy_total += task_elapsed
        elif active_task == "超级抽奖":
            cj_total += task_elapsed
        elif active_task == "删除车辆":
            delete_total += task_elapsed

        try:
            self.lbl_runtime_task_time.configure(text=self.format_elapsed(task_elapsed))
            self.lbl_runtime_total_time.configure(text=self.format_elapsed(total_elapsed))
            if hasattr(self, "lbl_compact_total_time"):
                self.lbl_compact_total_time.configure(text=self.format_elapsed(total_elapsed))
            self.lbl_runtime_totals.configure(
                text=(
                    f"跑图 {self.format_elapsed(race_total)} | "
                    f"买车 {self.format_elapsed(buy_total)} | "
                    f"超抽 {self.format_elapsed(cj_total)} | "
                    f"删车 {self.format_elapsed(delete_total)}"
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
                if hasattr(self, "lbl_compact_task"):
                    self.ui_call(self.lbl_compact_task.configure, text=task_name)
            if max_val > 0:
                self.ui_call(self.lbl_runtime_progress.configure, text=f"{current_val} / {max_val}")
                if hasattr(self, "lbl_compact_progress"):
                    self.ui_call(self.lbl_compact_progress.configure, text=f"{current_val} / {max_val}")
        except Exception:
            pass

    def preload_background_services_async(self):
        """Attach background I/O and capture shortly after UI startup, without focus theft."""
        if self._background_preload_started or self.is_running:
            return
        self._background_preload_started = True

        def worker():
            connected = False
            try:
                connected = bool(
                    self.check_and_focus_game(
                        focus_game=False,
                        quiet=True,
                        calibrate=False,
                    )
                )
            finally:
                self._background_preload_started = False

            if connected:
                if not self._background_preload_announced:
                    self._background_preload_announced = True
                    self.log("[模式] 后台鼠标、键盘与识图模块已在启动阶段预连接。")
                return

            if not self.is_running:
                try:
                    self.after(2000, self.preload_background_services_async)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def update_delete_progress(self, current, target):
        current = max(0, int(current))
        target = max(1, int(target))
        self.update_running_ui("删除车辆", current, target)
        label = getattr(self, "lbl_delete", None)
        if label is not None:
            self.ui_call(label.configure, text=f"执行: {current} / {target}")

    def update_running_state(self, state):
        try:
            if state == "running":
                self.lbl_run_state.configure(text="运行中", fg_color="#238636", text_color="#FFFFFF")
                self.btn_runtime_stop.configure(state="normal")
                self.btn_stop.configure(text="停止任务 (F8)", fg_color="#DA3633", hover_color="#B02A37")
                if hasattr(self, "lbl_compact_state"):
                    self.lbl_compact_state.configure(text="运行中", fg_color="#238636")
                if self.is_compact_on_run_enabled():
                    self.set_compact_window(True)
            elif state == "paused":
                self.lbl_run_state.configure(text="已暂停", fg_color="#9A6700", text_color="#FFFFFF")
                self.btn_runtime_stop.configure(state="normal")
                if hasattr(self, "lbl_compact_state"):
                    self.lbl_compact_state.configure(text="已暂停", fg_color="#9A6700")
            else:
                self.lbl_run_state.configure(text="待机", fg_color="#222B36", text_color="#C9D1D9")
                self.lbl_runtime_task.configure(text="等待中")
                self.lbl_runtime_progress.configure(text="0 / 0")
                self.lbl_runtime_loop.configure(text="0 / 0")
                self.lbl_runtime_task_time.configure(text="00:00:00")
                self.lbl_runtime_total_time.configure(text="00:00:00")
                self.lbl_runtime_totals.configure(
                    text="跑图 00:00:00 | 买车 00:00:00 | 超抽 00:00:00 | 删车 00:00:00"
                )
                if hasattr(self, "lbl_compact_task"):
                    self.lbl_compact_task.configure(text="等待中")
                    self.lbl_compact_progress.configure(text="0 / 0")
                    self.lbl_compact_loop.configure(text="0 / 0")
                    self.lbl_compact_total_time.configure(text="00:00:00")
                self.btn_runtime_stop.configure(state="disabled")
                self.btn_stop.configure(text="等待指令 (F8)", fg_color="#222B36", hover_color="#2F3B4A")
                if hasattr(self, "lbl_compact_state"):
                    self.lbl_compact_state.configure(text="待机", fg_color="#222B36")
                self.set_compact_window(False)
        except Exception as e:
            self.log(f"运行状态界面更新失败：{e}", level="ERROR", frontend=True)

    def is_compact_on_run_enabled(self):
        variable = getattr(self, "var_compact_on_run", None)
        if variable is not None:
            return bool(variable.get())
        return bool(self.config.get("compact_on_run", False))

    def on_compact_on_run_changed(self):
        enabled = self.is_compact_on_run_enabled()
        self.config["compact_on_run"] = enabled
        self.save_config()
        self.log(f"[模式] 运行时缩小{'已开启' if enabled else '已关闭'}")
        if self.is_running:
            self.set_compact_window(enabled)

    def set_compact_window(self, compact):
        compact = bool(compact)
        if not hasattr(self, "compact_container"):
            return
        active = bool(getattr(self, "_compact_window_active", False))
        if compact == active:
            return

        if compact:
            self.update_idletasks()
            self._full_window_geometry = self.geometry()
            try:
                raw_minimum = self.tk.call("wm", "minsize", self._w)
                minimum_values = self.tk.splitlist(raw_minimum)
                self._full_window_minsize = (
                    int(minimum_values[0]),
                    int(minimum_values[1]),
                )
            except Exception:
                self._full_window_minsize = (
                    (1040, 650) if self.is_log_collapsed else (1120, 760)
                )
            compact_width = 522
            compact_height = 398
            x, y = self.get_compact_top_right_position(compact_width, compact_height)
            self.main_container.pack_forget()
            self.compact_container.pack(fill="both", expand=True, padx=14, pady=14)
            self.minsize(500, 376)
            self.geometry(f"{compact_width}x{compact_height}+{x}+{y}")
            self._compact_window_active = True
            self.log("[模式] 已切换到运行时紧凑窗口")
        else:
            self.compact_container.pack_forget()
            self.main_container.pack(fill="both", expand=True, padx=16, pady=14)
            restore_minimum = getattr(self, "_full_window_minsize", (1120, 760))
            self.minsize(int(restore_minimum[0]), int(restore_minimum[1]))
            restore_geometry = getattr(self, "_full_window_geometry", "1240x800")
            self.geometry(restore_geometry)
            self._compact_window_active = False

    def get_compact_top_right_position(self, width, height, margin=16):
        """Position the compact UI at the current monitor's work-area top-right."""
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            hwnd = int(self.winfo_id())
            monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if monitor and ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                return (
                    int(max(work.left, work.right - int(width) - int(margin))),
                    int(work.top + int(margin)),
                )
        except Exception:
            pass

        return (
            max(0, int(self.winfo_screenwidth()) - int(width) - int(margin)),
            max(0, int(margin)),
        )

    def restore_compact_window_normal_layer(self):
        """Raise compact UI once without making it permanently topmost."""
        if not bool(getattr(self, "_compact_window_active", False)):
            return
        try:
            self.attributes("-topmost", False)
            self.lift()
        except Exception:
            pass

    # ==========================================
    # --- 核心操作与流程控制 ---
    # ==========================================
    def hw_key_down(self, key):
        if self.config.get("background_keyboard_enabled", True):
            manager = self.ensure_background_keyboard()
            if manager:
                return manager.key_down(key)
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
        if self.config.get("background_keyboard_enabled", True):
            manager = self.ensure_background_keyboard()
            if manager:
                return manager.key_up(key)
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
        if self.config.get("background_keyboard_enabled", True):
            manager = self.ensure_background_keyboard()
            if manager:
                return manager.press(key, delay=delay, use_send=False)
        self.hw_key_down(key)
        time.sleep(delay)
        self.hw_key_up(key)
    #副屏支持
    def is_background_mouse_enabled(self):
        if hasattr(self, "var_background_mouse"):
            return bool(self.var_background_mouse.get())
        return bool(self.config.get("background_mouse_enabled", True))

    def on_background_mouse_changed(self):
        enabled = self.is_background_mouse_enabled()
        self.config["background_mouse_enabled"] = enabled
        self.save_config()
        state = "已开启，不会移动系统物理鼠标" if enabled else "已关闭，恢复物理鼠标点击"
        self.log(f"[模式] 后台鼠标{state}")
        if not enabled:
            self.deactivate_mouse_isolation()
        elif self.is_running:
            self._mouse_isolation_dismissed_for_run = False
            self.activate_mouse_isolation_for_run()

    def activate_mouse_isolation_for_run(self):
        if (
            not self.is_running
            or not self.is_background_mouse_enabled()
            or self._mouse_isolation_dismissed_for_run
        ):
            return False

        hwnd = getattr(self, "game_hwnd", None)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False

        current = getattr(self, "mouse_isolation_overlay", None)
        if current is not None:
            if current.game_hwnd == int(hwnd) and current.is_active():
                return True
            current.stop()

        def on_dismiss():
            self._mouse_isolation_dismissed_for_run = True
            self.log(
                "[模式] 鼠标隔离已关闭，本次任务可直接操作游戏画面。",
                frontend=True,
            )

        overlay = MouseIsolationOverlay(hwnd, on_dismiss=on_dismiss)
        self.mouse_isolation_overlay = overlay
        if not overlay.start():
            self.mouse_isolation_overlay = None
            detail = getattr(overlay, "_startup_error", None)
            self.log(
                f"鼠标隔离启动失败{'：' + detail if detail else ''}。",
                level="WARN",
                frontend=True,
            )
            return False

        self.log(
            "[模式] 鼠标隔离已启动，单击游戏画面关闭。",
            frontend=True,
        )
        return True

    def deactivate_mouse_isolation(self):
        overlay = getattr(self, "mouse_isolation_overlay", None)
        self.mouse_isolation_overlay = None
        if overlay is not None:
            overlay.stop()

    def ensure_background_mouse(self):
        hwnd = getattr(self, "game_hwnd", None)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        manager = getattr(self, "background_mouse", None)
        if manager is None or manager.hwnd != int(hwnd) or not manager.is_valid():
            manager = WindowMouseManager(
                hwnd,
                protect_from_physical_cursor=True,
            )
            self.background_mouse = manager
        return manager

    def ensure_background_keyboard(self):
        hwnd = getattr(self, "game_hwnd", None)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        manager = getattr(self, "background_keyboard", None)
        if manager is None or manager.hwnd != int(hwnd) or not manager.is_valid():
            if manager is not None:
                manager.stop()
            manager = WindowKeyboardManager(
                hwnd,
                resilient_holds=True,
            )
            manager.start()
            self.background_keyboard = manager
        return manager

    def screen_to_game_client(self, x, y):
        hwnd = getattr(self, "game_hwnd", None)
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        try:
            return win32gui.ScreenToClient(hwnd, (int(x), int(y)))
        except Exception:
            gx, gy, _, _ = self.regions["全界面"]
            return int(x - gx), int(y - gy)

    def hw_mouse_move(self, x, y):
        if self.is_background_mouse_enabled():
            manager = self.ensure_background_mouse()
            client_pos = self.screen_to_game_client(x, y)
            if manager and client_pos:
                return manager.move(client_pos[0], client_pos[1], use_send=True)
            return False

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
    def game_click(
        self,
        pos,
        double=False,
        confirm_key=None,
        move_away=True,
        clicks=None,
        hold=0.08,
        gap=0.08,
        use_send=True,
    ):
        self.check_pause()  # <--- 【新增】拦截鼠标点击
        if not self.is_running or not pos:
            return False
        x, y = int(pos[0]), int(pos[1])

        if self.is_background_mouse_enabled():
            manager = self.ensure_background_mouse()
            client_pos = self.screen_to_game_client(x, y)
            if not manager or not client_pos:
                self.log("后台鼠标点击失败：游戏窗口句柄无效。", level="ERROR", frontend=True)
                return False
            try:
                mode = "SendMessage" if use_send else "PostMessage"
                self.log(
                    f"[BackgroundMouse] {mode} client=({client_pos[0]},{client_pos[1]}) "
                    f"double={bool(double)} clicks={clicks} hold={hold:.2f} gap={gap:.2f}",
                    level="DEBUG",
                )
                ok = manager.click(
                    client_pos[0],
                    client_pos[1],
                    double=double,
                    use_send=use_send,
                    clicks=clicks,
                    hold=hold,
                    gap=gap,
                )
                if not ok:
                    self.log("后台鼠标点击失败：窗口消息未发送。", level="ERROR", frontend=True)
                    return False
                if move_away:
                    manager.stabilize(5, 5, duration=0.12, use_send=True)
                if confirm_key:
                    self.hw_press(confirm_key, delay=0.1)
                return True
            except Exception as e:
                self.log(f"后台鼠标点击异常：{e}", level="ERROR", frontend=True)
                return False

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
        if move_away:
            try:
                gx, gy, gw, gh = self.regions["全界面"]
                # 移动到游戏左上角向内偏移 5 像素，避免遮挡后续识图。
                self.hw_mouse_move(gx + 5, gy + 5)
            except Exception:
                self.hw_mouse_move(5, 5)
            time.sleep(0.2)
        if confirm_key:
            self.hw_press(confirm_key, delay=0.1)
        return True

    def move_to_game_coord(self, x, y):
        """
        将鼠标移动到以【游戏窗口左上角】为起点的 (x, y) 坐标。
        例如传入 (5, 5)，就会移动到游戏内左上角 5 像素的安全位置。
        """
        if self.is_background_mouse_enabled():
            manager = self.ensure_background_mouse()
            if manager:
                return manager.move(int(x), int(y), use_send=True)
            return False
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
        self.sync_current_skill_dirs_for_vehicle()

    def sync_current_skill_dirs_for_vehicle(self, mode=None):
        mode = str(mode or self.config.get("buy_cj_vehicle", "subaru")).lower()
        if mode not in DEFAULT_SKILL_DIRS_BY_VEHICLE:
            mode = "subaru"
        paths = self.config.get("skill_dirs_by_vehicle")
        if not isinstance(paths, dict):
            paths = {
                key: list(value) for key, value in DEFAULT_SKILL_DIRS_BY_VEHICLE.items()
            }
            self.config["skill_dirs_by_vehicle"] = paths
        paths[mode] = list(self.config.get("skill_dirs", []))

    def get_skill_dirs_for_vehicle(self, mode=None):
        mode = str(mode or self.get_buy_cj_vehicle_mode()).lower()
        if mode not in DEFAULT_SKILL_DIRS_BY_VEHICLE:
            mode = "subaru"
        paths = self.config.get("skill_dirs_by_vehicle", {})
        dirs = paths.get(mode) if isinstance(paths, dict) else None
        if not isinstance(dirs, list):
            dirs = DEFAULT_SKILL_DIRS_BY_VEHICLE[mode]
        return [direction for direction in dirs if direction in ("up", "down", "left", "right")]

    def infer_log_level(self, message, level=None):
        if level:
            return str(level).upper()

        text = str(message or "")
        upper_text = text.upper()
        if upper_text.startswith("[ERROR]") or "致命" in text or "异常" in text:
            return "ERROR"
        if upper_text.startswith("[WARN]") or "警告" in text or "失败" in text or "未找到" in text:
            return "WARN"
        if upper_text.startswith("[DEBUG]") or "[Calibration]" in text or "[Diagnostic]" in text:
            return "DEBUG"
        return "INFO"

    def record_diagnostic_log(self, level, message, ts=None):
        trace = getattr(self, "diagnostic_trace", None)
        if not trace:
            return

        event = {
            "ts": ts or time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "log",
            "level": str(level or "INFO").upper(),
            "message": str(message or ""),
        }
        try:
            with open(trace["logs_path"], "a", encoding="utf-8-sig") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            return

        trace["log_count"] += 1
        trace["log_levels"][event["level"]] = trace["log_levels"].get(event["level"], 0) + 1

    def should_show_frontend_log(self, message, level="INFO"):
        """Keep the UI log concise while diagnostic mode retains every message."""
        text = str(message or "")
        frontend_prefixes = (
            "免责声明：",
            "默认刷图车辆：",
            "蓝图代码可自行修改",
            "游戏设置为",
            "【设置】",
            "大部分以图像识别作为引导",
            "诊断记录已",
            "买车/超抽车辆方案已切换为：",
            "技能树路径已自动切换为：",
            "[AI模型]",
            "[模式]",
            "[流程]",
            "[进度]",
            "[大循环]",
            "已启用 CR 买车限制：",
            "未启用 CR 买车限制",
            "CR 买车上限已触发",
            "达到设定的总循环次数",
            "执行模块 ",
            "为防止游戏陷入死循环",
            "致命错误：",
            "!!! 警告：",
            "!!! 任务已停止",
            "⏸ 任务已暂停",
            "▶ 任务已恢复",
            "未发现 forzahorizon6.exe",
            "找到进程但无法解析PID",
            "未检测到游戏进程",
            "自动启动超时",
            "!!! 检测到 VRAMNE.png",
            "!!! 严重警告:",
        )
        return text.startswith(frontend_prefixes)

    def capture_diagnostic_snapshot(self, name, *, region=None, image_bgr=None, reason=None, level="WARN", meta=None, dedupe_key=None):
        trace = getattr(self, "diagnostic_trace", None)
        if not trace:
            return None

        capture_key = dedupe_key or name
        if capture_key in trace["capture_keys"]:
            return None

        try:
            frame = image_bgr if image_bgr is not None else self.capture_region(region)
        except Exception:
            return None
        if frame is None:
            return None

        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(name or "capture"))
        capture_index = trace["capture_count"] + 1
        filename = f"{capture_index:03d}_{safe_name}.png"
        file_path = os.path.join(trace["captures_dir"], filename)
        if not self.write_debug_image(file_path, frame):
            return None

        trace["capture_count"] = capture_index
        trace["capture_keys"].add(capture_key)
        capture_event = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "capture",
            "name": name,
            "level": str(level or "WARN").upper(),
            "reason": reason,
            "file": file_path,
            "region": region,
            "meta": meta or {},
        }
        trace["captures"].append(capture_event)
        return file_path

    def log(self, message, level=None, frontend=None):
        resolved_level = self.infer_log_level(message, level=level)
        curr_time = time.strftime("%H:%M:%S")
        full_msg = f"[{curr_time}] {message}" if resolved_level == "INFO" else f"[{curr_time}] [{resolved_level}] {message}"
        self.record_diagnostic_log(resolved_level, message, ts=time.strftime("%Y-%m-%d %H:%M:%S"))

        if frontend is None:
            frontend = self.should_show_frontend_log(message, resolved_level)
        if not frontend:
            return

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
                compact_log = getattr(self, "compact_log_box", None)
                if compact_log is not None:
                    compact_log.configure(state="normal")
                    compact_log.insert("end", full_msg + "\n")
                    self._compact_log_line_count = getattr(self, "_compact_log_line_count", 0) + 1
                    if self._compact_log_line_count > 400:
                        compact_log.delete("1.0", "end-251lines")
                        self._compact_log_line_count = 250
                    compact_log.see("end")
                    compact_log.configure(state="disabled")
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
                self.minsize(1040, 700)
                self.geometry(f"{self.winfo_width()}x{getattr(self, 'expanded_window_height', 800)}")
                self.is_log_collapsed = False
            else:
                self.expanded_window_height = self.winfo_height()
                self.bottom_frame.pack_forget()
                if hasattr(self, "lbl_log_title"):
                    self.lbl_log_title.configure(text="日志已收起")
                if hasattr(self, "btn_toggle_log"):
                    self.btn_toggle_log.configure(text="展开日志")
                self.minsize(1040, 650)
                self.geometry(f"{self.winfo_width()}x650")
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
        self.log(f"[模式] AI辅助{'已开启' if enabled else '已关闭'}")
        if enabled:
            self.preload_ai_model_async()

    def on_smart_page_changed(self):
        enabled = bool(self.var_smart_page.get())
        self.config["smart_page"] = enabled
        if not enabled:
            self.memory_car_page = 0
        self.save_config()
        self.log(f"[模式] 智能页码{'已开启' if enabled else '已关闭'}")

    def on_ai_only_changed(self):
        enabled = bool(self.var_ai_only.get())
        self.config["ai_only"] = enabled
        if enabled:
            self.var_ai_assist.set(True)
            self.config["ai_assist"] = True
            self.config["ai_prefer"] = True
        self.save_config()
        self.log(f"[模式] 纯AI{'已开启' if enabled else '已关闭'}")

    def on_ai_auto_capture_changed(self):
        enabled = bool(self.var_ai_auto_capture.get())
        self.config["ai_auto_capture"] = enabled
        self.save_config()
        self.log(f"[模式] AI自动截图{'已开启' if enabled else '已关闭'}")

    def on_diagnostic_mode_changed(self):
        enabled = bool(getattr(self, "var_diagnostic_mode", None).get())
        self.config["diagnostic_mode"] = enabled
        self.save_config()
        self.log("诊断记录已开启。" if enabled else "诊断记录已关闭。")

    def on_buy_cj_vehicle_changed(self, selected):
        mode = self.resolve_buy_cj_vehicle_mode(selected)
        previous_mode = str(self.config.get("buy_cj_vehicle", "subaru")).lower()
        if previous_mode in DEFAULT_SKILL_DIRS_BY_VEHICLE:
            self.sync_current_skill_dirs_for_vehicle(previous_mode)
        self.config["buy_cj_vehicle"] = mode
        self.config["skill_dirs"] = self.get_skill_dirs_for_vehicle(mode)
        self.update_skill_grid()
        self.save_config()
        vehicle_name = "马自达（通行证车辆）" if mode == "mazda" else "斯巴鲁 22B"
        unit_price = self.get_buy_cj_vehicle_price(mode)
        if hasattr(self, "lbl_buy_cj_vehicle_price"):
            suffix = " · 需要通行证" if mode == "mazda" else ""
            self.lbl_buy_cj_vehicle_price.configure(text=f"单价 {unit_price:,} CR{suffix}")
        self.log(f"买车/超抽车辆方案已切换为：{vehicle_name}，单价 {unit_price:,} CR")
        arrows = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
        path_text = " ".join(arrows[direction] for direction in self.config["skill_dirs"])
        self.log(f"技能树路径已自动切换为：{path_text}")
        self.yolo_car_select_model = None
        self.yolo_car_select_model_path = None
        self.ai_model_preload_started = False
        if self.config.get("ai_assist", False):
            self.preload_ai_model_async()

    def get_buy_cj_vehicle_mode(self, prefer_active=True):
        if prefer_active:
            active_mode = str(getattr(self, "active_buy_cj_vehicle", "")).lower()
            if active_mode in ("subaru", "mazda"):
                return active_mode
        if hasattr(self, "var_buy_cj_vehicle"):
            selected = str(self.var_buy_cj_vehicle.get() or "")
            return self.resolve_buy_cj_vehicle_mode(selected)
        selected = str(self.config.get("buy_cj_vehicle", "subaru")).lower()
        return selected if selected in ("subaru", "mazda") else "subaru"

    def resolve_buy_cj_vehicle_mode(self, selected):
        selected_text = str(selected or "")
        labels = getattr(self, "_buy_cj_vehicle_labels", {}) or {}
        if selected_text == str(labels.get("mazda", "马自达")):
            return "mazda"
        if selected_text == str(labels.get("subaru", "斯巴鲁 22B")):
            return "subaru"
        return "mazda" if "马自达" in selected_text else "subaru"

    def get_buy_cj_vehicle_price(self, mode=None):
        mode = mode or self.get_buy_cj_vehicle_mode()
        prices = self.config.get("buy_cj_vehicle_prices", {})
        fallback = DEFAULT_BUY_CJ_VEHICLE_PRICES.get(mode, DEFAULT_BUY_CJ_VEHICLE_PRICES["subaru"])
        try:
            price = int(prices.get(mode, fallback)) if isinstance(prices, dict) else int(fallback)
        except Exception:
            price = int(fallback)
        return price if price > 0 else int(fallback)

    def start_diagnostic_trace_session(self, session_name):
        if not bool(self.config.get("diagnostic_mode", False)):
            self.diagnostic_trace = None
            return

        report_dir = self.create_diagnostic_report_dir()
        events_path = os.path.join(report_dir, "events.jsonl")
        logs_path = os.path.join(report_dir, "logs.jsonl")
        captures_dir = os.path.join(report_dir, "captures")
        os.makedirs(captures_dir, exist_ok=True)
        self.diagnostic_trace = {
            "session_name": session_name,
            "report_dir": report_dir,
            "events_path": events_path,
            "logs_path": logs_path,
            "captures_dir": captures_dir,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event_count": 0,
            "hit_count": 0,
            "miss_count": 0,
            "log_count": 0,
            "log_levels": {},
            "capture_count": 0,
            "capture_keys": set(),
            "captures": [],
        }
        self.log(f"[Diagnostic] 已开启诊断记录: {report_dir}", level="DEBUG")

    def record_diagnostic_match(
        self,
        kind,
        name,
        *,
        region_name=None,
        threshold=None,
        effective_threshold=None,
        fast_mode=None,
        invert_mode=None,
        hit=False,
        score=0.0,
        scale=1.0,
        mode="原图",
        template=None,
        position=None,
        elapsed_ms=None,
        extra=None,
    ):
        trace = getattr(self, "diagnostic_trace", None)
        if not trace:
            return

        event = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "name": name,
            "region": region_name,
            "threshold": threshold,
            "effective_threshold": effective_threshold,
            "fast_mode": fast_mode,
            "invert_mode": invert_mode,
            "hit": bool(hit),
            "score": float(score or 0.0),
            "scale": float(scale or 1.0),
            "mode": mode,
            "template": template,
            "position": position,
            "elapsed_ms": elapsed_ms,
        }
        if extra:
            event["extra"] = extra

        try:
            with open(trace["events_path"], "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            return

        trace["event_count"] += 1
        if event["hit"]:
            trace["hit_count"] += 1
        else:
            trace["miss_count"] += 1

    def finish_diagnostic_trace_session(self):
        trace = getattr(self, "diagnostic_trace", None)
        if not trace:
            return

        summary = {
            "session_name": trace["session_name"],
            "started_at": trace["started_at"],
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event_count": trace["event_count"],
            "hit_count": trace["hit_count"],
            "miss_count": trace["miss_count"],
            "log_count": trace["log_count"],
            "log_levels": dict(trace["log_levels"]),
            "capture_count": trace["capture_count"],
            "window_info": dict(getattr(self, "match_window_info", {}) or {}),
            "calibration": dict(getattr(self, "match_calibration", {}) or {}),
            "events_path": trace["events_path"],
            "logs_path": trace["logs_path"],
        }

        try:
            with open(os.path.join(trace["report_dir"], "summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        try:
            events = []
            logs = []
            if os.path.exists(trace["events_path"]):
                with open(trace["events_path"], "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            continue

            if os.path.exists(trace["logs_path"]):
                with open(trace["logs_path"], "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            logs.append(json.loads(line))
                        except Exception:
                            continue

            def fmt_bool(v):
                return "是" if v else "否"

            lines = [
                "FH6Auto 诊断记录报告",
                f"会话: {summary['session_name']}",
                f"开始时间: {summary['started_at']}",
                f"结束时间: {summary['finished_at']}",
                "",
                "一、整体结果",
                f"- 总识图次数: {summary['event_count']}",
                f"- 命中次数: {summary['hit_count']}",
                f"- 未命中次数: {summary['miss_count']}",
                f"- 日志条数: {summary['log_count']}",
                f"- 失败截图数: {summary['capture_count']}",
                "",
                "二、窗口信息",
                f"- 窗口坐标: ({summary['window_info'].get('x', '-')}, {summary['window_info'].get('y', '-')})",
                f"- 窗口尺寸: {summary['window_info'].get('width', '-')} x {summary['window_info'].get('height', '-')}",
                f"- 窗口宽高比: {summary['window_info'].get('aspect', '-')}",
                "",
                "三、自适应校准",
                f"- 状态: {summary['calibration'].get('status', '-')}",
                f"- 说明: {summary['calibration'].get('detail', '-')}",
                f"- 首选缩放: {summary['calibration'].get('preferred_scale', '-')}",
                f"- 阈值偏移: {summary['calibration'].get('gray_threshold_offset', '-')}",
                f"- 清晰度: {summary['calibration'].get('sharpness', '-')}",
                f"- 亮度: {summary['calibration'].get('brightness', '-')}",
                f"- 校准锚点: {summary['calibration'].get('anchor', '-')}",
                f"- 锚点分数: {summary['calibration'].get('anchor_score', '-')}",
                "",
                "四、日志等级统计",
                f"- INFO: {summary['log_levels'].get('INFO', 0)}",
                f"- WARN: {summary['log_levels'].get('WARN', 0)}",
                f"- ERROR: {summary['log_levels'].get('ERROR', 0)}",
                f"- DEBUG: {summary['log_levels'].get('DEBUG', 0)}",
                "",
                "五、关键失败截图",
            ]

            if trace["captures"]:
                for idx, capture in enumerate(trace["captures"], 1):
                    lines.append(
                        f"{idx}. [{capture.get('level', '-')}] {capture.get('name', '-')} -> {os.path.basename(capture.get('file', '-'))}"
                    )
                    if capture.get("reason"):
                        lines.append(f"   - 原因: {capture['reason']}")
                    if capture.get("meta"):
                        lines.append(f"   - 补充信息: {capture['meta']}")
            else:
                lines.append("- 本次没有生成失败截图。")

            lines.extend([
                "",
                "六、识图流水（按真实运行顺序）",
            ])

            for idx, event in enumerate(events, 1):
                lines.append(
                    f"{idx}. [{event.get('ts', '-')}] {event.get('kind', '-')}: {event.get('name', '-')}"
                )
                lines.append(
                    f"   - 结果: {'命中' if event.get('hit') else '未命中'} | 分数: {event.get('score', 0.0):.3f} | "
                    f"阈值: {event.get('effective_threshold', 0.0):.3f} | 缩放: {event.get('scale', 1.0):.3f}"
                )
                lines.append(
                    f"   - 模式: {event.get('mode', '-')} | 区域: {event.get('region', '-')} | 模板: {event.get('template', '-')}"
                )
                lines.append(
                    f"   - fast_mode: {fmt_bool(event.get('fast_mode'))} | invert_mode: {fmt_bool(event.get('invert_mode'))} | 耗时: {event.get('elapsed_ms', '-') }ms"
                )
                if event.get("position"):
                    lines.append(f"   - 坐标: {event['position']}")
                if event.get("extra"):
                    lines.append(f"   - 补充信息: {event['extra']}")
                lines.append("")

            lines.append("七、运行日志（玩家可直接阅读）")
            if logs:
                for idx, log_event in enumerate(logs, 1):
                    lines.append(
                        f"{idx}. [{log_event.get('ts', '-')}] [{log_event.get('level', 'INFO')}] {log_event.get('message', '')}"
                    )
            else:
                lines.append("- 无日志记录。")

            report_txt = os.path.join(trace["report_dir"], "report.txt")
            with open(report_txt, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(lines))
        except Exception as e:
            self.log(f"[Diagnostic] 生成文本诊断报告失败: {e}", level="ERROR")

        self.log(
            f"[Diagnostic] 诊断记录已保存: {trace['report_dir']} "
            f"(hits={trace['hit_count']}, misses={trace['miss_count']})"
        , level="DEBUG")
        self.diagnostic_trace = None

    def resolve_ai_model_path(self):
        return flow_resolve_ai_model_path(self)
    def get_yolo_car_select_model(self):
        return flow_get_yolo_car_select_model(self)
    def preload_ai_model_async(self):
        return flow_preload_ai_model_async(self)
    def resolve_ai_device(self):
        return flow_resolve_ai_device(self)
    def yolo_box_to_dict(self, item, conf_threshold=0.25):
        return flow_yolo_box_to_dict(self, item, conf_threshold=conf_threshold)
    def yolo_yellow_tag_ratio(self, img, box):
        return flow_yolo_yellow_tag_ratio(self, img, box)
    def yolo_box_distance(self, a, b):
        return flow_yolo_box_distance(self, a, b)
    def find_yolo_car_candidate(self, img, boxes, min_tag_yellow_ratio=0.18):
        return flow_find_yolo_car_candidate(self, img, boxes, min_tag_yellow_ratio=min_tag_yellow_ratio)
    def save_ai_car_debug(self, screen_bgr, status, boxes=None, candidate=None, reason="", click=None, force=False):
        return flow_save_ai_car_debug(self, screen_bgr, status, boxes=boxes, candidate=candidate, reason=reason, click=click, force=force)
    def find_new_consumable_car_with_ai(self, region=None, save_miss=True):
        return flow_find_new_consumable_car_with_ai(self, region=region, save_miss=save_miss)
    def save_template_car_debug(self, screen_bgr, status, reason="", boxes=None, scores=None, click=None, force=False):
        return flow_save_template_car_debug(self, screen_bgr, status, reason=reason, boxes=boxes, scores=scores, click=click, force=force)
    def cleanup_recent_template_car_miss(self, root, keep_seconds=12.0):
        return flow_cleanup_recent_template_car_miss(self, root, keep_seconds=keep_seconds)

    def start_delete_test(self):
        """Start the Mazda-only deletion flow outside the main loop."""
        if self.is_running:
            self.log("[流程] 已有任务正在运行，请停止后再启动删除车辆任务。")
            return

        try:
            target_count = max(1, int(self.entry_delete.get()))
        except Exception:
            target_count = max(1, int(self.config.get("delete_count", 30) or 30))
            self.entry_delete.delete(0, "end")
            self.entry_delete.insert(0, str(target_count))

        self.is_running = True
        self._mouse_isolation_dismissed_for_run = False
        self.save_config()
        self.reset_run_stats()
        self.delete_counter = 0
        self.update_running_state("running")
        self.update_delete_progress(0, target_count)
        self.update_timer()
        self.start_diagnostic_trace_session("delete:standalone")
        self.log(f"[流程] 开始删除车辆任务，目标数量 {target_count}（仅 Mazda）")

        def runner():
            success = False
            try:
                if self.check_and_focus_game():
                    success = bool(self.logic_delete_car(target_count))
            except Exception as e:
                self.log(f"执行删除车辆模块时异常: {e}", level="ERROR", frontend=True)

            if success:
                self.log(f"[流程] 删除车辆任务结束，完成 {self.delete_counter}/{target_count}")
            elif self.is_running:
                self.log("[流程] 删除车辆任务尚未完成。")
            if self.is_running:
                self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

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
        self._mouse_isolation_dismissed_for_run = False
        self.save_config()

        self.reset_run_stats()
        self.update_running_state("running")
        self.update_timer()
        self.update_running_ui("初始化中...")
        self.start_diagnostic_trace_session(f"pipeline:{start_step}")
        self.race_counter = 0
        self.car_counter = 0
        self.cj_counter = 0
        self.global_loop_current = 0
        self.total_car_bought = 0
        self.total_car_limit = None
        self.stop_after_cj_due_buy_limit = False
        self.active_buy_cj_vehicle = self.get_buy_cj_vehicle_mode(prefer_active=False)
        self.active_buy_vehicle_price = self.get_buy_cj_vehicle_price(self.active_buy_cj_vehicle)
        vehicle_name = "马自达 808" if self.active_buy_cj_vehicle == "mazda" else "斯巴鲁 22B"
        ai_state = "已开启" if self.config.get("ai_assist", False) else "未开启"
        self.log(f"[模式] 本次任务车辆：{vehicle_name}；AI 选车：{ai_state}")
        try:
            cr_amount = max(0, int(getattr(self, "entry_cr_amount", None).get() or 0))
        except Exception:
            cr_amount = max(0, int(self.config.get("cr_amount", 0) or 0))
        if cr_amount > 0:
            self.total_car_limit = cr_amount // self.active_buy_vehicle_price
            vehicle_name = "马自达" if self.active_buy_cj_vehicle == "mazda" else "斯巴鲁 22B"
            self.log(
                f"已启用 CR 买车限制：车辆={vehicle_name}，单价={self.active_buy_vehicle_price:,} CR，"
                f"可用CR={cr_amount:,}，总买车上限={self.total_car_limit}"
            )
        else:
            self.log("未启用 CR 买车限制，批量买车将按原设定执行。")
        self.invalid_blueprint_abort = False

        def runner():
            if not self.check_and_focus_game():
                self.stop_all()
                return

            steps = ["race", "buy", "cj", "delete"]
            curr_idx = steps.index(start_step)

            try:
                total_loops = int(self.entry_global_loop.get())
            except Exception:
                total_loops = self.config.get("global_loops", 10)
            self.global_loop_current = 1
            self.ui_call(self.lbl_runtime_loop.configure, text=f"{self.global_loop_current} / {total_loops}")
            if hasattr(self, "lbl_compact_loop"):
                self.ui_call(self.lbl_compact_loop.configure, text=f"{self.global_loop_current} / {total_loops}")
            self.log(f"[大循环] 开始 1/{total_loops}")

            # 【新增】：全局连续失败计数器
            continuous_failures = 0
            # 【你可以修改这里】：设置全局允许的最大连续恢复次数（比如 3 次）
            MAX_RECOVERIES = 10

            while self.is_running:
                step_name = steps[curr_idx]
                step_label = {
                    "race": "循环跑图",
                    "buy": "批量买车",
                    "cj": "超级抽奖",
                    "delete": "删除车辆",
                }[step_name]
                success = False
                self.log(
                    f"[流程] 开始 {step_label}（大循环 {self.global_loop_current}/{total_loops}）"
                )

                try:
                    if step_name == "race":
                        success = self.logic_race(int(self.entry_race.get()))
                    elif step_name == "buy":
                        success = self.logic_buy_car(int(self.entry_car.get()))
                    elif step_name == "cj":
                        success = self.logic_super_wheelspin(int(self.entry_cj.get()))
                    elif step_name == "delete":
                        success = self.logic_delete_car(int(self.entry_delete.get()))
                except Exception as e:
                    self.log(f"执行模块 {step_name} 时异常: {e}")
                    success = False

                if not self.is_running:
                    break

                if getattr(self, "invalid_blueprint_abort", False):
                    self.log("[流程] 循环跑图已停止：当前挑战分享码不可用")
                    break

                if not success:
                    if getattr(self, "invalid_blueprint_abort", False):
                        break

                    continuous_failures += 1
                    self.log(
                        f"[流程] {step_label}未完成，准备恢复后重试 "
                        f"({continuous_failures}/{MAX_RECOVERIES})"
                    )

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
                    completed = {
                        "race": self.race_counter,
                        "buy": self.car_counter,
                        "cj": self.cj_counter,
                        "delete": self.delete_counter,
                    }[step_name]
                    self.log(f"[流程] {step_label}结束，本轮完成 {completed} 次")

                if step_name == "cj" and getattr(self, "stop_after_cj_due_buy_limit", False):
                    self.log("CR 买车上限已触发，本轮超抽完成后停止整个循环，避免浪费新车。")
                    break
                #v1.0.1
                # ====== 核心流转与无限循环逻辑 ======
                next_idx = self.resolve_pipeline_next_index(curr_idx)
                if next_idx is None:
                    break

                if step_name == "buy" and getattr(self, "stop_after_cj_due_buy_limit", False):
                    next_idx = 2

                if next_idx <= curr_idx:
                    self.global_loop_current += 1

                    if self.global_loop_current > total_loops:
                        self.log(f"[大循环] 已完成 {total_loops}/{total_loops}")
                        self.log("达到设定的总循环次数，任务圆满结束。")
                        break

                    self.log(f"[大循环] 已完成 {self.global_loop_current - 1}/{total_loops}")
                    self.log(f"[大循环] 开始 {self.global_loop_current}/{total_loops}")

                    self.ui_call(self.lbl_runtime_loop.configure, text=f"{self.global_loop_current} / {total_loops}")
                    if hasattr(self, "lbl_compact_loop"):
                        self.ui_call(self.lbl_compact_loop.configure, text=f"{self.global_loop_current} / {total_loops}")

                    self.race_counter = 0
                    self.car_counter = 0
                    self.cj_counter = 0
                    self.delete_counter = 0

                curr_idx = next_idx

            self.stop_all()

        self.current_thread = threading.Thread(target=runner, daemon=True)
        self.current_thread.start()

    def stop_all(self):
        self.deactivate_mouse_isolation()
        if not self.is_running:
            return

        self.is_running = False
        self.is_paused = False  # <--- 【新增】彻底停止时必须解除暂停锁

        for key in DIK_CODES.keys():
            self.hw_key_up(key)

        for key in ["w", "e", "y", "enter", "esc", "up", "down", "left", "right", "space", "backspace"]:
            self.hw_key_up(key)

        if not self.is_background_mouse_enabled():
            try:
                pydirectinput.mouseUp()
            except Exception:
                pass

        self.finalize_active_task_time()
        self.finish_diagnostic_trace_session()
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
        self.start_diagnostic_trace_session("test_boot")

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

    def create_diagnostic_report_dir(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_dir = os.path.join(APP_DIR, "debug", "diagnostics", ts)
        os.makedirs(report_dir, exist_ok=True)
        return report_dir

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
            if not self.is_background_mouse_enabled():
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
        if keyboard is None:
            self.log("未检测到 pynput，已跳过 F8/F9 全局热键监听，可继续使用界面按钮操作。")
            return

        def hotkey_thread():
            last_f9_time = 0.0

            def on_press(k):
                nonlocal last_f9_time
                try:
                    if k == keyboard.Key.f8:
                        self.stop_all()
                    elif k == keyboard.Key.f9:
                        now = time.monotonic()
                        if now - last_f9_time >= 0.5:
                            last_f9_time = now
                            self._developer_f9_last_time = now
                            self.ui_call(open_developer_text_editor, self)
                except Exception as exc:
                    self.ui_call(
                        self.log,
                        f"全局快捷键处理异常：{exc}",
                        level="ERROR",
                        frontend=True,
                    )

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
    def check_and_focus_game(self, focus_game=True, quiet=False, calibrate=True):
        if not quiet:
            self.log("检查游戏进程 (forzahorizon6.exe)...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if "forzahorizon6.exe" not in output.lower():
                if not quiet:
                    self.log("未发现 forzahorizon6.exe 进程！(请确保游戏已运行)")
                return False

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                if not quiet:
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
                titled_hwnds = []
                for candidate in hwnds:
                    title_length = ctypes.windll.user32.GetWindowTextLengthW(candidate)
                    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
                    ctypes.windll.user32.GetWindowTextW(candidate, title_buffer, title_length + 1)
                    titled_hwnds.append((candidate, title_buffer.value.strip()))
                preferred = [item for item in titled_hwnds if item[1] == "Forza Horizon 6"]
                if not preferred:
                    preferred = [item for item in titled_hwnds if "Forza Horizon 6" in item[1]]
                hwnd = (preferred or titled_hwnds)[0][0]
                if focus_game:
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
                    with self._background_attach_lock:
                        self.game_hwnd = hwnd
                        mouse = getattr(self, "background_mouse", None)
                        if mouse is None or mouse.hwnd != int(hwnd) or not mouse.is_valid():
                            self.background_mouse = WindowMouseManager(
                                hwnd,
                                protect_from_physical_cursor=True,
                            )

                        capture = getattr(self, "background_capture", None)
                        if capture is None or capture.hwnd != int(hwnd) or not capture.is_valid():
                            self.background_capture = WindowCaptureManager(hwnd)

                        keyboard_manager = getattr(self, "background_keyboard", None)
                        if (
                            keyboard_manager is None
                            or keyboard_manager.hwnd != int(hwnd)
                            or not keyboard_manager.is_valid()
                        ):
                            if keyboard_manager is not None:
                                keyboard_manager.stop()
                            keyboard_manager = WindowKeyboardManager(
                                hwnd,
                                resilient_holds=True,
                            )
                            keyboard_manager.start()
                            self.background_keyboard = keyboard_manager
                        elif not getattr(keyboard_manager, "_running", False):
                            keyboard_manager.start()

                    if not quiet:
                        mouse_state = "后台" if self.is_background_mouse_enabled() else "物理"
                        capture_state = "后台" if self.config.get("background_capture_enabled", True) else "桌面"
                        keyboard_state = "后台" if self.config.get("background_keyboard_enabled", True) else "物理"
                        self.log(
                            f"[模式] 游戏窗口已连接（{gw}×{gh}；"
                            f"鼠标={mouse_state}，识图={capture_state}，键盘={keyboard_state}）"
                        )
                    if calibrate:
                        self.calibrate_match_profile()
                    # SetForegroundWindow(game) is needed for initial hookup, but
                    # it also leaves the compact UI behind the game.  Raise the UI
                    # once as a normal window; do not keep it topmost.
                    if focus_game and self.is_compact_on_run_enabled():
                        self.ui_call(self.restore_compact_window_normal_layer)

                    self.activate_mouse_isolation_for_run()

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

                if focus_game:
                    time.sleep(1.0)
                return True

        except Exception as e:
            if not quiet:
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
        obstacles_dir = get_img_path("obstacles")
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
        return flow_logic_race(self, target_count)
    def abort_invalid_blueprint_and_back_to_roam(self):
        return flow_abort_invalid_blueprint_and_back_to_roam(self)
    def handle_author_prompt(self, release_drive_keys=False):
        return flow_handle_author_prompt(self, release_drive_keys=release_drive_keys)
    def logic_buy_car(self, target_count):
        return flow_logic_buy_car(self, target_count)
    def logic_delete_car(self, target_count):
        return flow_logic_delete_car(self, target_count)
    def enter_design_paint_choose_car(self):
        return flow_enter_design_paint_choose_car(self)
    def select_new_consumable_car_from_list(self):
        return flow_select_new_consumable_car_from_list(self)
    def logic_super_wheelspin(self, target_count):
        return flow_logic_super_wheelspin(self, target_count)
if __name__ == "__main__":
    app = FH_UltimateBot()
    app.mainloop()


