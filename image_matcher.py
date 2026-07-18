import os
import time
import json
import pickle

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

from background_capture import WindowCaptureManager

from app_resources import (
    APP_DIR,
    INTERNAL_DIR,
    CACHE_DIR,
    TEMPLATE_CACHE_FILE,
    TEMPLATE_META_FILE,
    get_images_dir,
    get_img_path,
)
from recognition_config import get_recognition_profile

MATCH_THRESHOLD = 0.8


CONSUMABLE_CAR_TEMPLATE_PROFILES = {
    "subaru": {
        "vehicle_name": "斯巴鲁 22B",
        "main_template": "newCC.png",
        "tag_template": "newcartag.png",
        "class_template": "classB600.png",
        "class_label": "B600",
        "class_threshold": 0.58,
        "car_threshold": 0.56,
        "top_threshold": 0.72,
        "bottom_threshold": 0.72,
        "fixed_title_threshold": 0.0,
        "vehicle_detail_threshold": 0.0,
    },
    "mazda": {
        "vehicle_name": "马自达 #123 Mad Mike 808 Wagon",
        "main_template": "newCC_Mazda.png",
        "tag_template": "newcartag_Mazda.png",
        "class_template": "classS1702_Mazda.png",
        "class_label": "S1 702",
        # 马自达列表里所有车辆共用大面积白底卡片，必须依赖车型细节而不是整卡轮廓。
        "class_threshold": 0.80,
        "car_threshold": 0.82,
        "top_threshold": 0.78,
        "bottom_threshold": 0.78,
        "fixed_title_threshold": 0.78,
        "vehicle_detail_threshold": 0.76,
    },
}


class ImageMatcherMixin:
    # ==========================================
    def should_capture_diagnostic_template(self, template_name):
        watched = {
            "eventlab.png",
            "joinchallenge.png",
            "changecar.png",
            "racenotfound.png",
            "VEI.png",
            "skillcarbrand.png",
            "skillcar_r917.png",
            "consumablecar.png",
            "CCbrand_Mazda.png",
            "consumablecar_Mazda.png",
            "newCC.png",
            "newcartag.png",
            "classB600.png",
            "newCC_Mazda.png",
            "newcartag_Mazda.png",
            "classS1702_Mazda.png",
        }
        return os.path.basename(str(template_name or "")) in watched

    def capture_diagnostic_template_miss(self, template_name, *, region=None, screen_bgr=None, best_score=None, threshold=None, extra=None):
        if not hasattr(self, "capture_diagnostic_snapshot"):
            return None
        if not self.should_capture_diagnostic_template(template_name):
            return None

        region_name = next((name for name, rect in self.regions.items() if rect == region), "custom") if region else "全界面"
        safe_name = os.path.basename(str(template_name or "template")).replace(".", "_")
        meta = {
            "template": template_name,
            "region": region_name,
            "best_score": round(float(best_score or 0.0), 4),
            "threshold": threshold,
        }
        if extra:
            meta["extra"] = extra

        return self.capture_diagnostic_snapshot(
            f"miss_{safe_name}",
            region=region,
            image_bgr=screen_bgr,
            reason=f"关键模板未命中: {template_name}",
            level="WARN",
            meta=meta,
            dedupe_key=f"miss:{template_name}:{region_name}",
        )

    def load_template(self, template_path):
        actual_path = get_img_path(template_path)
        cache_key = actual_path

        if cache_key in self.template_cache:
            return self.template_cache[cache_key], actual_path

        tpl = cv2.imread(actual_path, cv2.IMREAD_COLOR)
        if tpl is not None:
            self.template_cache[cache_key] = tpl
        return tpl, actual_path
    def load_template_gray(self, template_path):
        actual_path = get_img_path(template_path)
        cache_key = ("gray", actual_path)
        if not hasattr(self, "template_gray_cache"):
            self.template_gray_cache = {}
        if cache_key in self.template_gray_cache:
            return self.template_gray_cache[cache_key]
        tpl = cv2.imread(actual_path, cv2.IMREAD_GRAYSCALE)
        if tpl is not None:
            self.template_gray_cache[cache_key] = tpl
        return tpl
    def get_images_root_dir(self):
        ext_dir = get_images_dir(APP_DIR)
        if ext_dir:
            return ext_dir

        int_dir = get_images_dir(INTERNAL_DIR)
        if int_dir:
            return int_dir

        return None

    def get_template_meta(self):
        images_dir = self.get_images_root_dir()
        meta_data = {}
        if not images_dir:
            return meta_data

        for root, _, files in os.walk(images_dir):
            for file in files:
                if not file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    continue

                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, images_dir).replace("\\", "/")

                try:
                    stat = os.stat(path)
                    meta_data[rel_path] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
                except Exception:
                    pass

        return meta_data

    def is_template_cache_valid(self):
        if not os.path.exists(TEMPLATE_CACHE_FILE) or not os.path.exists(TEMPLATE_META_FILE):
            return False

        try:
            with open(TEMPLATE_META_FILE, "r", encoding="utf-8") as f:
                old_meta = json.load(f)
        except Exception:
            return False

        new_meta = self.get_template_meta()
        return old_meta == new_meta

    def build_template_file_cache(self):
        self.log("开始构建模板缓存文件...")
        os.makedirs(CACHE_DIR, exist_ok=True)

        images_dir = self.get_images_root_dir()
        if not images_dir:
            self.log("未找到 images 目录，无法构建模板缓存。")
            return False

        cache_data = {}
        meta_data = self.get_template_meta()

        scales = self.get_scales_to_try(fast_mode=False)

        for rel_path in meta_data.keys():
            img_path = os.path.join(images_dir, rel_path)
            tpl = cv2.imread(img_path, cv2.IMREAD_COLOR)
            if tpl is None:
                continue

            cache_data[rel_path] = {}
            for scale in scales:
                try:
                    if scale == 1.0:
                        scaled = tpl.copy()
                    else:
                        scaled = cv2.resize(tpl, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    cache_data[rel_path][str(round(scale, 3))] = scaled
                except Exception:
                    continue

        try:
            with open(TEMPLATE_CACHE_FILE, "wb") as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)

            with open(TEMPLATE_META_FILE, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)

            self.log("模板缓存文件构建完成。")
            return True
        except Exception as e:
            self.log(f"写入模板缓存失败: {e}")
            return False

    def load_template_file_cache(self):
        try:
            with open(TEMPLATE_CACHE_FILE, "rb") as f:
                self.file_template_cache = pickle.load(f)
            self.log("模板缓存文件加载成功。")
            return True
        except Exception as e:
            self.log(f"加载模板缓存失败: {e}")
            self.file_template_cache = {}
            return False

    def prepare_template_cache(self):
        os.makedirs(CACHE_DIR, exist_ok=True)

        if self.is_template_cache_valid():
            if self.load_template_file_cache():
                return

        self.log("模板缓存不存在或已失效，开始后台重建（这可能需要几秒钟）...")
        if self.build_template_file_cache():
            self.template_cache.clear()
            self.scaled_template_cache.clear()
            self.load_template_file_cache()

    def capture_region(self, region=None, mask_areas=None):
        screen_bgr = None
        use_background = bool(
            getattr(self, "config", {}).get("background_capture_enabled", True)
        )
        hwnd = getattr(self, "game_hwnd", None)

        if use_background and hwnd:
            manager = getattr(self, "background_capture", None)
            if manager is None or manager.hwnd != int(hwnd) or not manager.is_valid():
                manager = WindowCaptureManager(hwnd)
                self.background_capture = manager
            screen_bgr = manager.capture_region(region)
            if screen_bgr is not None:
                mean_value = float(screen_bgr.mean()) if screen_bgr.size else 0.0
                deviation = float(screen_bgr.std()) if screen_bgr.size else 0.0
                # PrintWindow can report success while returning an all-black,
                # all-white, or otherwise flat surface (notably when minimized).
                if mean_value < 3.0 or mean_value > 252.0 or deviation < 1.0:
                    self._report_background_capture_problem(
                        f"PrintWindow 返回无效画面 mean={mean_value:.1f} std={deviation:.1f}"
                    )
                    screen_bgr = None
                else:
                    previous_failures = int(getattr(self, "_background_capture_failures", 0))
                    self._background_capture_failures = 0
                    if previous_failures >= 3:
                        self.log("[模式] 后台识图已恢复。", level="INFO")

        if screen_bgr is None:
            # Compatibility path for startup (before HWND discovery), disabled
            # background capture, or a driver/window that rejects PrintWindow.
            try:
                if region:
                    x, y, w, h = region
                    bbox = (int(x), int(y), int(x + w), int(y + h))
                    screen = ImageGrab.grab(bbox=bbox, all_screens=True)
                else:
                    screen = ImageGrab.grab(all_screens=True)
            except Exception:
                screen = pyautogui.screenshot(region=region)
            screen_bgr = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

        # 对指定区域打黑块，避免重复识别同一个目标。
        if mask_areas:
            for rect in mask_areas:
                try:
                    mx1, my1, mx2, my2 = rect
                    mx1 = max(0, int(mx1))
                    my1 = max(0, int(my1))
                    mx2 = min(screen_bgr.shape[1], int(mx2))
                    my2 = min(screen_bgr.shape[0], int(my2))
                    if mx2 > mx1 and my2 > my1:
                        screen_bgr[my1:my2, mx1:mx2] = 0
                except Exception:
                    pass

        return screen_bgr

    def _report_background_capture_problem(self, detail):
        failures = int(getattr(self, "_background_capture_failures", 0)) + 1
        self._background_capture_failures = failures
        # Avoid flooding both UI and diagnostic logs during recognition loops.
        if failures in (1, 3) or failures % 20 == 0:
            self.log(f"[BackgroundCapture] {detail}，已使用桌面截图回退。", level="WARN")
        if failures == 3:
            self.log(
                "[模式] 后台识图连续失败，当前已回退桌面截图；窗口被遮挡时可能无法识别。",
                level="WARN",
            )

    def get_scales_to_try(self, fast_mode=True):
        full_region = self.regions.get("全界面")
        curr_w = full_region[2] if full_region else pyautogui.size()[0]
        scales = []
        calib = getattr(self, "match_calibration", {}) or {}
        preferred_scale = float(calib.get("preferred_scale", 1.0) or 1.0)
        hinted_scales = []
        for base_width in [1600, 1920, 2560]:
            hinted_scale = curr_w / base_width
            hinted_scales.extend([
                hinted_scale,
                hinted_scale * 0.99,
                hinted_scale * 1.01,
            ])

        def add_scale(s):
            s = round(float(s), 3)
            if 0.45 <= s <= 1.8 and s not in scales:
                scales.append(s)

        # 优先尝试校准结果和窗口提示比例，避免 fast_mode 只围绕 1.0 导致入口图漏识别。
        for s in [
            preferred_scale,
            *hinted_scales,
            preferred_scale * 0.995,
            preferred_scale * 1.005,
            preferred_scale * 0.99,
            preferred_scale * 1.01,
            preferred_scale * 0.985,
            preferred_scale * 1.015,
            1.0,
            0.99,
            1.01,
            0.985,
            1.015,
            0.97,
            1.03,
            0.95,
            1.05,
        ]:
            add_scale(s)

        # 最后保留一层兜底范围，兼容少量 UI 缩放或采样差异。
        for s in [0.92, 1.08, 0.9, 1.1, 0.88, 1.12, 0.85, 1.15, 0.8, 0.75, 0.7]:
            add_scale(s)

        if fast_mode:
            return scales[:16]
        return scales

    def get_calibrated_gray_threshold(self, threshold):
        calib = getattr(self, "match_calibration", {}) or {}
        offset = float(calib.get("gray_threshold_offset", 0.0) or 0.0)
        adjusted = float(threshold) + offset
        return max(0.50, min(0.98, adjusted))

    def get_scaled_template(self, template_path, scale):
        actual_path = get_img_path(template_path)
        images_dir = self.get_images_root_dir()

        if images_dir and os.path.exists(actual_path):
            try:
                rel_key = os.path.relpath(actual_path, images_dir).replace("\\", "/")
            except Exception:
                rel_key = os.path.basename(actual_path)
        else:
            rel_key = os.path.basename(actual_path)

        mem_key = (actual_path, round(scale, 3))
        if mem_key in self.scaled_template_cache:
            return self.scaled_template_cache[mem_key], actual_path

        scale_key = str(round(scale, 3))
        if rel_key in self.file_template_cache:
            tpl = self.file_template_cache[rel_key].get(scale_key)
            if tpl is not None:
                self.scaled_template_cache[mem_key] = tpl
                return tpl, actual_path

        template_orig, actual_path = self.load_template(template_path)
        if template_orig is None:
            return None, actual_path

        try:
            if scale == 1.0:
                tpl = template_orig.copy()
            else:
                tpl = cv2.resize(template_orig, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            self.scaled_template_cache[mem_key] = tpl
            return tpl, actual_path
        except Exception:
            return None, actual_path

    def find_image_in_screen(self, screen_bgr, template_path, region=None, threshold=0.75, fast_mode=True):
        try:
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for scale in scales_to_try:
                tpl_c, actual_path = self.get_scaled_template(template_path, scale)
                if tpl_c is None:
                    continue

                h, w = tpl_c.shape[:2]
                if h < 5 or w < 5:
                    continue
                if h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                    continue

                res = cv2.matchTemplate(screen_bgr, tpl_c, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= threshold:
                    pos = (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )
                    self.last_positions[template_path] = pos
                    # 输出基础模板匹配日志。
                    self.log(f"[ImageMatch] 命中: {template_path} | 得分: {max_val:.3f} (阈值 {threshold}) | 缩放比: {scale:.3f}")
                    return pos

            return None

        except Exception as e:
            self.log(f"find_image_in_screen 异常: {e}")
            return None

    def find_image(self, template_path, region=None, threshold=0.75, fast_mode=True):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            return self.find_image_in_screen(
                screen_bgr,
                template_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode
            )
        except Exception as e:
            self.log(f"查找图片时发生异常: {e}")
            return None

    def find_any_image(self, image_list, region=None, threshold=MATCH_THRESHOLD, fast_mode=True):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            for img_path in image_list:
                pos = self.find_image_in_screen(
                    screen_bgr,
                    img_path,
                    region=region,
                    threshold=threshold,
                    fast_mode=fast_mode
                )
                if pos:
                    return pos
            return None
        except Exception as e:
            self.log(f"find_any_image 异常: {e}")
            return None

    def find_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, fast_mode=True):
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            for scale in scales_to_try:
                # 1. 直接读取缓存后的缩放模板。
                main_tpl_c, _ = self.get_scaled_template(main_path, scale)
                sub_tpl_c, _ = self.get_scaled_template(sub_path, scale)
                if main_tpl_c is None or sub_tpl_c is None:
                    continue
                h_m, w_m = main_tpl_c.shape[:2]
                if h_m < 5 or w_m < 5 or h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue
                # 2. 第一阶段匹配：先在全图中找主目标。
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_c, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res_main >= threshold)
                checked = set()  # 坐标去重，避免相邻结果重复验证。
                for pt in zip(*loc[::-1]):
                    x, y = pt
                    # 过滤 10 像素范围内的重复命中点。
                    key = (x // 10, y // 10)
                    if key in checked:
                        continue
                    checked.add(key)
                    # 3. 在主图周边略微扩展范围，再验证子元素。
                    sub_roi = screen_bgr[
                        max(0, y - 5):min(screen_bgr.shape[0], y + h_m + 5),
                        max(0, x - 5):min(screen_bgr.shape[1], x + w_m + 5),
                    ]
                    if sub_tpl_c.shape[0] > sub_roi.shape[0] or sub_tpl_c.shape[1] > sub_roi.shape[1]:
                        continue
                    # 4. 第二阶段匹配：确认扩展区域内确实包含子元素。
                    res_sub = cv2.matchTemplate(sub_roi, sub_tpl_c, cv2.TM_CCOEFF_NORMED)
                    sub_score = cv2.minMaxLoc(res_sub)[1]
                    if sub_score >= threshold:
                        # 输出组合匹配日志，方便诊断。
                        main_score = res_main[y, x]
                        self.log(f"[ComboMatch] 命中: {main_path}+{sub_path} | 主图得分: {main_score:.3f} | 元素得分: {sub_score:.3f} (阈值 {threshold}) | 缩放比: {scale:.3f}")
                        return (
                            x + w_m // 2 + (region[0] if region else 0),
                            y + h_m // 2 + (region[1] if region else 0),
                        )
            return None
        except Exception as e:
            self.log(f"find_image_with_element 异常: {e}")
            return None
    def find_image_with_element_stable(
        self,
        main_path,
        sub_path,
        region=None,
        main_threshold=0.60,
        verify_threshold=0.72,
        sub_threshold=0.70,
        max_candidates=15
    ):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)

            main_tpl = self.load_template_gray(main_path)
            sub_tpl = self.load_template_gray(sub_path)

            if main_tpl is None or sub_tpl is None:
                return None

            h_m, w_m = main_tpl.shape[:2]
            h_s, w_s = sub_tpl.shape[:2]

            if h_m > screen_gray.shape[0] or w_m > screen_gray.shape[1]:
                return None

            res_main = cv2.matchTemplate(screen_gray, main_tpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res_main >= main_threshold)

            if len(xs) == 0:
                return None

            candidates = [(float(res_main[y, x]), x, y) for x, y in zip(xs, ys)]
            candidates.sort(key=lambda t: t[0], reverse=True)

            checked = set()
            checked_count = 0

            for main_score, x, y in candidates:
                key = (x // 8, y // 8)
                if key in checked:
                    continue
                checked.add(key)

                checked_count += 1
                if checked_count > max_candidates:
                    break

                pad = 8
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(screen_gray.shape[1], x + w_m + pad)
                y2 = min(screen_gray.shape[0], y + h_m + pad)

                sub_roi = screen_gray[y1:y2, x1:x2]
                if sub_roi.shape[0] < h_s or sub_roi.shape[1] < w_s:
                    continue

                res_sub = cv2.matchTemplate(sub_roi, sub_tpl, cv2.TM_CCOEFF_NORMED)
                sub_score = cv2.minMaxLoc(res_sub)[1]

                if main_score >= verify_threshold and sub_score >= sub_threshold:
                    cx = x + w_m // 2
                    cy = y + h_m // 2
                    if region:
                        cx += region[0]
                        cy += region[1]
                    # 銆愭柊澧炪€戯細鎵撳嵃绋冲畾鐗堢粍鍚堝尮閰嶇殑璇︾粏寰楀垎
                    self.log(f"[StableMatch] 命中: {main_path}+{sub_path} | 主图: {main_score:.3f} (需>{verify_threshold}) | 元素: {sub_score:.3f} (需>{sub_threshold})")
                    return (cx, cy)

            return None

        except Exception as e:
            self.log(f"find_image_with_element_stable 识别报错: {e}")
            return None
    def find_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True,
        main_threshold=0.60, like_threshold=0.75, final_threshold=0.72, mask_areas=None,
        detail_box=None, detail_threshold=0.0):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region, mask_areas=mask_areas)
            screen_gray = self.to_gray_image(screen_bgr)
            screen_edge = self.to_edge_image(screen_bgr)

            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for scale in scales_to_try:
                main_tpl_c, _ = self.get_scaled_template(main_path, scale)
                sub_tpl_c, _ = self.get_scaled_template(sub_path, scale)

                if main_tpl_c is None or sub_tpl_c is None:
                    continue

                main_tpl_gray = self.to_gray_image(main_tpl_c)
                main_tpl_edge = self.to_edge_image(main_tpl_c)

                h_m, w_m = main_tpl_c.shape[:2]
                if h_m < 5 or w_m < 5:
                    continue
                if h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue

                # 先用彩色主模板找候选点，初筛阈值放低一些。
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_c, cv2.TM_CCOEFF_NORMED)
                # 不只依赖硬阈值，改为提取前 N 个高分候选。
                flat = res_main.ravel()
                if flat.size == 0:
                    continue
                top_k = min(80, flat.size)   # 可调，当前先取前 80 个候选。
                idxs = np.argpartition(flat, -top_k)[-top_k:]
                points = []
                for idx in idxs:
                    y, x = np.unravel_index(idx, res_main.shape)
                    score = res_main[y, x]
                    # 给一个较低的底线，避免噪点候选过多。
                    if score < max(0.55, main_threshold - 0.12):
                        continue
                    points.append((x, y, score))
                # 先按 y、x 排序，保证从上到下、从左到右处理。
                points.sort(key=lambda p: (p[1], p[0]))

                checked_points = set()

                for pt in points:
                    x, y, base_score = pt

                    # 去重，避免同一辆车被重复计算。
                    key = (x // 10, y // 10)
                    if key in checked_points:
                        continue
                    checked_points.add(key)

                    roi_bgr = screen_bgr[y:y + h_m, x:x + w_m]
                    roi_gray = screen_gray[y:y + h_m, x:x + w_m]
                    roi_edge = screen_edge[y:y + h_m, x:x + w_m]

                    if roi_bgr.shape[:2] != main_tpl_c.shape[:2]:
                        continue

                    # 四维打分：彩色、灰度、边缘、中心区域。
                    color_score = self.match_template_score(roi_bgr, main_tpl_c)
                    gray_score = self.match_template_score(roi_gray, main_tpl_gray)
                    edge_score = self.match_template_score(roi_edge, main_tpl_edge)

                    roi_center = self.crop_center_ratio(roi_bgr, ratio=0.6)
                    tpl_center = self.crop_center_ratio(main_tpl_c, ratio=0.6)
                    center_score = self.match_template_score(roi_center, tpl_center)

                    # 标签匹配：NEW 标签或作者点赞标签。
                    pad = 5
                    sub_roi = screen_bgr[
                        max(0, y - pad):min(screen_bgr.shape[0], y + h_m + pad),
                        max(0, x - pad):min(screen_bgr.shape[1], x + w_m + pad),
                    ]
                    like_score = self.match_template_score(sub_roi, sub_tpl_c)

                    if like_score < like_threshold:
                        continue

                    detail_score = self.match_normalized_detail_score(
                        roi_bgr,
                        main_tpl_c,
                        detail_box,
                    )
                    if detail_box and detail_score < detail_threshold:
                        continue

                    # 计算综合得分。
                    final_score = (
                        color_score * 0.35 +
                        gray_score * 0.25 +
                        edge_score * 0.05 +
                        center_score * 0.20 +
                        like_score * 0.15
                    )

                    curr_pos = (
                        x + w_m // 2 + (region[0] if region else 0),
                        y + h_m // 2 + (region[1] if region else 0),
                    )

                    # 只要综合得分达标，就直接返回当前最靠前的目标。
                    if final_score >= final_threshold:
                        self.log(
                            f"[MultiMatch] 锁定目标: {main_path}+{sub_path} | "
                            f"综合: {final_score:.3f} | 彩色: {color_score:.3f} | "
                            f"灰度: {gray_score:.3f} | 边缘: {edge_score:.3f} | "
                            f"中心: {center_score:.3f} | 标签: {like_score:.3f} | "
                            f"等级区域: {detail_score:.3f}"
                        )
                        return curr_pos

            return None

        except Exception as e:
            self.log(f"find_image_with_element_multi 异常: {e}")
            return None

    def find_image_with_element_fast(self, main_path, sub_path, region=None, threshold=0.70, sub_threshold=0.70):
        if not self.is_running:
            return None

        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)

            main_tpl = self.load_template_gray(main_path)
            sub_tpl = self.load_template_gray(sub_path)

            if main_tpl is None or sub_tpl is None:
                return None

            h_m, w_m = main_tpl.shape[:2]
            h_s, w_s = sub_tpl.shape[:2]

            if h_m > screen_gray.shape[0] or w_m > screen_gray.shape[1]:
                return None

            res_main = cv2.matchTemplate(screen_gray, main_tpl, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res_main >= threshold)

            checked = set()

            for pt in zip(*loc[::-1]):
                x, y = pt

                # 鍘婚噸锛岄伩鍏嶇浉閭婚噸澶嶇偣澶
                key = (x // 10, y // 10)
                if key in checked:
                    continue
                checked.add(key)

                x1 = max(0, x - 5)
                y1 = max(0, y - 5)
                x2 = min(screen_gray.shape[1], x + w_m + 5)
                y2 = min(screen_gray.shape[0], y + h_m + 5)

                sub_roi = screen_gray[y1:y2, x1:x2]

                if sub_roi.shape[0] < h_s or sub_roi.shape[1] < w_s:
                    continue

                res_sub = cv2.matchTemplate(sub_roi, sub_tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val_sub, _, _ = cv2.minMaxLoc(res_sub)

                if max_val_sub >= sub_threshold:
                    cx = x + w_m // 2
                    cy = y + h_m // 2
                    if region:
                        cx += region[0]
                        cy += region[1]
                    # 输出快速匹配日志。
                    main_score = res_main[y, x]
                    self.log(f"[FastMatch] 命中: {main_path}+{sub_path} | 主图: {main_score:.3f} (需>{threshold}) | 元素: {max_val_sub:.3f} (需>{sub_threshold})")
                    return (cx, cy)

            return None

        except Exception as e:
            self.log(f"find_image_with_element_fast 异常: {e}")
            return None

    def wait_for_image_with_element_multi(self, main_path, sub_path, region=None, fast_mode=True,
        main_threshold=0.60, like_threshold=0.75,
        final_threshold=0.72, timeout=30, interval=0.4):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_multi(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                fast_mode=fast_mode,
                main_threshold=main_threshold,
                like_threshold=like_threshold,
                final_threshold=final_threshold
            )
            if pos:
                return pos

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def get_skillcar_template_names(self):
        configured = self.config.get("skillcar_templates", ["skillcar_r917.png"])
        if isinstance(configured, str):
            configured = [configured]

        names = []
        for item in configured or []:
            name = str(item).strip()
            if name and name not in names:
                names.append(name)
        return names or ["skillcar_r917.png"]

    def get_skillcar_fast_scales(self):
        """Return a small scale set centered on the calibrated 2560px car-card source."""
        full_region = self.regions.get("全界面")
        curr_w = float(full_region[2]) if full_region else float(pyautogui.size()[0])
        calibration = getattr(self, "match_calibration", {}) or {}
        preferred = float(calibration.get("preferred_scale", curr_w / 2560.0) or 1.0)
        expected = curr_w / 2560.0
        scales = []
        for value in (
            preferred,
            expected,
            expected * 0.99,
            expected * 1.01,
            preferred * 0.99,
            preferred * 1.01,
        ):
            value = round(float(value), 3)
            if 0.45 <= value <= 1.8 and value not in scales:
                scales.append(value)
        return scales

    def find_skill_car_with_like_tag(
        self,
        region=None,
        timeout=3.0,
        interval=0.25,
        fast_scan=False,
    ):
        profile = get_recognition_profile(
            self,
            "matcher.skillcar_like_combo",
            timeout=timeout,
            interval=interval,
        )
        template_names = self.get_skillcar_template_names()
        start = time.time()
        attempts = 0
        while self.is_running and time.time() - start < profile["timeout"]:
            attempts += 1
            for template_name in template_names:
                if fast_scan:
                    # 实机日志表明 R917 依赖“先找 liketag、再反查车辆卡片”的路径。
                    # 快速模式只检查校准比例附近的尺度，保留可靠性同时避免全尺度遍历。
                    pos = self.find_skill_car_from_like_tag(
                        region=region,
                        car_template_name=template_name,
                        scale_candidates=self.get_skillcar_fast_scales(),
                    )
                    if pos:
                        return pos
                    continue

                pos = self.find_image_with_element_multi(
                    template_name,
                    "liketag.png",
                    region=region,
                    fast_mode=profile["fast_mode"],
                    main_threshold=profile["main_threshold"],
                    like_threshold=profile["like_threshold"],
                    final_threshold=profile["final_threshold"],
                    detail_box=profile.get("detail_box"),
                    detail_threshold=profile.get("detail_threshold", 0.0),
                )
                if pos:
                    self.log(f"[SkillCar] 命中目标刷图车模板: {template_name}")
                    return pos

                pos = self.find_skill_car_from_like_tag(
                    region=region,
                    car_template_name=template_name,
                )
                if pos:
                    return pos

            if fast_scan and attempts >= 1:
                break
            time.sleep(profile["interval"])
        if not fast_scan and hasattr(self, "capture_diagnostic_snapshot"):
            self.capture_diagnostic_snapshot(
                "miss_skillcar_liketag",
                region=region,
                reason="未找到带 liketag 的刷图车辆",
                level="WARN",
                meta={
                    "timeout": profile["timeout"],
                    "interval": profile["interval"],
                    "templates": template_names,
                },
                dedupe_key="miss:skillcar_liketag",
            )
        return None

    def find_skill_car_from_like_tag(
        self,
        region=None,
        car_template_name=None,
        scale_candidates=None,
    ):
        if not self.is_running:
            return None
        try:
            car_template_name = car_template_name or self.get_skillcar_template_names()[0]
            profile = get_recognition_profile(self, "matcher.skillcar_like_combo")
            screen_bgr = self.capture_region(region)
            scales_to_try = scale_candidates or self.get_scales_to_try(fast_mode=False)
            best_debug = None

            for scale in scales_to_try:
                car_tpl, _ = self.get_scaled_template(car_template_name, scale)
                tag_tpl, _ = self.get_scaled_template("liketag.png", scale)
                if car_tpl is None or tag_tpl is None:
                    continue

                h_c, w_c = car_tpl.shape[:2]
                h_t, w_t = tag_tpl.shape[:2]
                if h_c < 5 or w_c < 5 or h_t < 3 or w_t < 3:
                    continue
                if h_t > screen_bgr.shape[0] or w_t > screen_bgr.shape[1]:
                    continue

                tag_res = cv2.matchTemplate(screen_bgr, tag_tpl, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(tag_res >= 0.70)
                tag_points = [(int(y), int(x), float(tag_res[y, x])) for y, x in zip(ys, xs)]
                tag_points.sort(key=lambda p: (p[0], p[1], -p[2]))
                checked_tags = set()

                for ty, tx, tag_score in tag_points[:80]:
                    key = (tx // 8, ty // 8)
                    if key in checked_tags:
                        continue
                    checked_tags.add(key)

                    sx1 = max(0, int(tx - w_c * 1.10))
                    sy1 = max(0, int(ty - h_c * 1.10))
                    sx2 = min(screen_bgr.shape[1], int(tx + w_t + w_c * 0.45))
                    sy2 = min(screen_bgr.shape[0], int(ty + h_t + h_c * 0.45))
                    search = screen_bgr[sy1:sy2, sx1:sx2]
                    if search.shape[0] < h_c or search.shape[1] < w_c:
                        continue

                    car_res = cv2.matchTemplate(search, car_tpl, cv2.TM_CCOEFF_NORMED)
                    _, car_score, _, car_loc = cv2.minMaxLoc(car_res)
                    card_x = sx1 + car_loc[0]
                    card_y = sy1 + car_loc[1]

                    rel_x = tx - card_x
                    rel_y = ty - card_y
                    if not (-int(w_c * 0.08) <= rel_x <= int(w_c * 1.08) and -int(h_c * 0.08) <= rel_y <= int(h_c * 1.08)):
                        best_debug = f"rel invalid tag:{tag_score:.3f} car:{car_score:.3f} rel:{rel_x},{rel_y} scale:{scale:.3f}"
                        continue
                    if car_score < 0.70:
                        best_debug = f"car low tag:{tag_score:.3f} car:{car_score:.3f} scale:{scale:.3f}"
                        continue

                    card_roi = screen_bgr[card_y:card_y + h_c, card_x:card_x + w_c]
                    detail_score = self.match_normalized_detail_score(
                        card_roi,
                        car_tpl,
                        profile.get("detail_box"),
                    )
                    if detail_score < profile.get("detail_threshold", 0.0):
                        best_debug = (
                            f"detail low tag:{tag_score:.3f} car:{car_score:.3f} "
                            f"detail:{detail_score:.3f} scale:{scale:.3f}"
                        )
                        continue

                    click_x = card_x + w_c // 2 + (region[0] if region else 0)
                    click_y = card_y + h_c // 2 + (region[1] if region else 0)
                    self.log(
                        f"[SkillCar] reverse hit: template={car_template_name} "
                        f"tag={tag_score:.3f} car={car_score:.3f} "
                        f"detail={detail_score:.3f} rel=({rel_x},{rel_y}) scale={scale:.3f}"
                    )
                    return (click_x, click_y)

            if best_debug:
                self.log(f"[SkillCar] reverse miss: {best_debug}")
            return None
        except Exception as e:
            self.log(f"find_skill_car_from_like_tag exception: {e}")
            return None

    def should_switch_skillcar_after_cj(self):
        try:
            return bool(self.var_chk3.get()) and int(self.entry_next3.get()) == 1
        except Exception:
            return bool(self.config.get("chk_3", True)) and int(self.config.get("next_3", 1)) == 1

    def switch_to_liked_skillcar_in_car_list(self):
        self.log("[SkillCar] 超抽后下一步为跑图，准备切换到带 liketag 的刷图车辆。")

        pos_target = None
        for _ in range(30):
            if not self.is_running:
                return False

            pos_target = self.find_skill_car_with_like_tag(
                region=self.regions["全界面"],
                timeout=1.2,
                interval=0.2,
            )
            if pos_target:
                break

            for _ in range(4):
                self.hw_press("right", delay=0.06)
                time.sleep(0.08)
            time.sleep(0.35)

        if not pos_target:
            self.log("[SkillCar] 未找到带 liketag 的刷图车辆，无法切换到跑图车辆。")
            return False

        self.game_click(pos_target)
        time.sleep(1.0)

        profile = get_recognition_profile(self, "matcher.skillcar_switch_rc")
        pos_rc = self.wait_for_image_gray(
            "rc.png",
            region=self.regions["全界面"],
            threshold=profile["threshold"],
            timeout=profile["timeout"],
            interval=profile["interval"],
            fast_mode=profile["fast_mode"],
        )
        if pos_rc:
            self.log("[SkillCar] 点击上车。")
            self.game_click(pos_rc)
        else:
            self.log("[SkillCar] 未找到上车按钮，尝试回车上车。")
            self.hw_press("enter")
            time.sleep(0.8)
            self.hw_press("enter")

        time.sleep(1.5)
        self.hw_press("tab")
        time.sleep(5.0)
        self.log("[SkillCar] 已切换到刷图车辆并返回漫游。")
        return True

    def prepare_skillcar_for_next_race_after_cj(self):
        self.log("[SkillCar] 准备复用超抽车辆列表流程切换刷图车辆。")
        self.log("[SkillCar] 复用当前超抽车辆列表上下文，进入我的车辆。")
        if not self.enter_my_cars_from_vehicle_menu():
            return False
        self.hw_press("backspace")
        time.sleep(1.0)

        brand_pos = None
        for _ in range(30):
            if not self.is_running:
                return False

            profile = get_recognition_profile(self, "matcher.skillcar_brand_entry")
            brand_pos = self.wait_for_image_gray(
                "skillcarbrand.png",
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                timeout=profile["timeout"],
                interval=profile["interval"],
                fast_mode=profile["fast_mode"],
            )
            if brand_pos:
                break

            self.hw_press("up")
            time.sleep(0.25)

        if not brand_pos:
            self.log("[SkillCar] 未找到斯巴鲁品牌。")
            return False

        self.game_click(brand_pos)
        time.sleep(1.0)

        return self.switch_to_liked_skillcar_in_car_list()

    def enter_my_cars_from_vehicle_menu(self):
        pos_uat = None
        for _ in range(12):
            if not self.is_running:
                return False

            profile = get_recognition_profile(self, "matcher.uat_menu")
            pos_uat = self.find_any_image_gray(
                ["UandT-w.png", "UandT-b.png"],
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                fast_mode=profile["fast_mode"],
            )
            if pos_uat:
                break
            time.sleep(0.2)

        if pos_uat:
            self.log("[CJ] 已确认车辆菜单，使用方向键重置到我的车辆。")
        else:
            self.log("[CJ] 未识别到升级与调校，仍尝试用方向键重置到我的车辆。")

        for _ in range(6):
            if not self.is_running:
                return False
            self.hw_press("up", delay=0.05)
            time.sleep(0.05)

        self.hw_press("enter")
        time.sleep(2.0)
        return True

    def return_to_vehicle_menu_after_mastery(self):
        self.hw_press("esc")
        time.sleep(1.4)
        self.hw_press("esc")
        time.sleep(1.0)

        for _ in range(8):
            if not self.is_running:
                return False

            profile = get_recognition_profile(self, "matcher.uat_menu")
            pos_uat = self.find_any_image_gray(
                ["UandT-w.png", "UandT-b.png"],
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                fast_mode=profile["fast_mode"],
            )
            if pos_uat:
                self.log("[CJ] 已返回车辆菜单。")
                return True
            time.sleep(0.2)

        self.log("[CJ] 未确认车辆菜单，继续下一步尝试。")
        return True

    def load_template_transparent(self, template_path):
        """Load a template while preserving its alpha channel."""
        actual_path = get_img_path(template_path)
        cache_key = ("transparent", actual_path)
        if not hasattr(self, "template_transparent_cache"):
            self.template_transparent_cache = {}
        if cache_key in self.template_transparent_cache:
            return self.template_transparent_cache[cache_key]
            
        # 注意这里使用 cv2.IMREAD_UNCHANGED，它会保留透明通道（BGRA）。
        tpl = cv2.imread(actual_path, cv2.IMREAD_UNCHANGED)
        if tpl is not None:
            self.template_transparent_cache[cache_key] = tpl
        return tpl
    def find_image_transparent(self, template_path, region=None, threshold=0.70, fast_mode=True):
        """Match templates with alpha channel while ignoring transparent background."""
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            tpl_bgra = self.load_template_transparent(template_path)
            
            if tpl_bgra is None:
                return None
            # 如果模板没有透明通道（不是 4 通道），则退化为普通模板匹配。
            if tpl_bgra.shape[2] != 4:
                return self.find_image_in_screen(screen_bgr, template_path, region, threshold, fast_mode)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            for scale in scales_to_try:
                # 对带透明通道的模板做缩放。
                if scale == 1.0:
                    tpl_scaled = tpl_bgra.copy()
                else:
                    tpl_scaled = cv2.resize(tpl_bgra, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                h, w = tpl_scaled.shape[:2]
                if h < 5 or w < 5 or h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                    continue
                # 分离 BGR 图层和 Alpha 遮罩层。
                tpl_bgr = tpl_scaled[:, :, :3]
                alpha_mask = tpl_scaled[:, :, 3]
                # 核心：使用带 mask 的模板匹配，透明区域不参与计算。
                res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED, mask=alpha_mask)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    # 输出透明模板匹配日志。
                    self.log(f"[AlphaMatch] 命中(忽略背景): {template_path} | 得分: {max_val:.3f} (阈值 {threshold}) | 缩放比: {scale:.3f}")
                    return (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )
            return None
        except Exception as e:
            self.log(f"find_image_transparent 异常: {e}")
            return None
    def wait_for_image_transparent(self, template_path, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True):
        """Wait for a transparent template to appear."""
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_transparent(template_path, region, threshold, fast_mode)
            if pos:
                return pos
            time.sleep(interval)
        return None
    def wait_for_image_with_element_stable(
        self,
        main_path,
        sub_path,
        region=None,
        main_threshold=0.60,
        verify_threshold=0.72,
        sub_threshold=0.70,
        max_candidates=15,
        timeout=3,
        interval=0.2
    ):
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_stable(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                main_threshold=main_threshold,
                verify_threshold=verify_threshold,
                sub_threshold=sub_threshold,
                max_candidates=max_candidates
            )
            if pos:
                return pos
            time.sleep(interval)
        return None
    def wait_for_image_with_element_fast(
        self,
        main_path,
        sub_path,
        region=None,
        threshold=0.70,
        sub_threshold=0.70,
        timeout=4,
        interval=0.25
    ):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element_fast(
                main_path=main_path,
                sub_path=sub_path,
                region=region,
                threshold=threshold,
                sub_threshold=sub_threshold
            )
            if pos:
                return pos

            time.sleep(interval)

        return None

    # ==========================================
    # --- 终极安全匹配 V5.1：排他校验 + 右下角精细校验 + 强制从左到右 ---
    # ==========================================
    def find_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, mask_areas=None):
        if not self.is_running: return None
        try:
            screen_bgr = self.capture_region(region, mask_areas=mask_areas)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)

            scales_to_try = self.get_scales_to_try(fast_mode=True)

            for scale in scales_to_try:
                main_tpl_bgr, _ = self.get_scaled_template(main_path, scale)
                anti_tpl_bgr = None
                if anti_path:
                    anti_tpl_bgr, _ = self.get_scaled_template(anti_path, scale)
                if main_tpl_bgr is None:
                    continue
                if anti_path and anti_tpl_bgr is None:
                    continue
                
                main_tpl_gray = cv2.cvtColor(main_tpl_bgr, cv2.COLOR_BGR2GRAY)
                h_m, w_m = main_tpl_bgr.shape[:2]
                h_a, w_a = anti_tpl_bgr.shape[:2]

                if h_m < 10 or w_m < 10 or h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue

                # 1. 鍩虹褰╄壊鍒濈瓫
                res_main = cv2.matchTemplate(screen_bgr, main_tpl_bgr, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res_main >= main_threshold)

                
                points = list(zip(*loc[::-1]))
                # 强制按 X 坐标排序，优先从左到右扫描。
                points.sort(key=lambda p: (p[1] // 50, p[0]))
                
                checked = set()
                for pt in points:
                    x, y = pt
                    if (x // 10, y // 10) in checked: continue
                    checked.add((x // 10, y // 10))

                    base_score = res_main[y, x]
                    
                    roi_bgr = screen_bgr[y:y+h_m, x:x+w_m]
                    roi_gray = screen_gray[y:y+h_m, x:x+w_m]
                    if roi_bgr.shape[:2] != main_tpl_bgr.shape[:2]: continue

                    # ==================================
                    # 防线 1：排他校验。
                    # ==================================
                    if anti_path and anti_tpl_bgr is not None:
                        h_a, w_a = anti_tpl_bgr.shape[:2]
                        pad_anti = 10
                        roi_y1, roi_y2 = max(0, y - pad_anti), min(screen_bgr.shape[0], y + h_m + pad_anti)
                        roi_x1, roi_x2 = max(0, x - pad_anti), min(screen_bgr.shape[1], x + w_m + pad_anti)
                        anti_roi = screen_bgr[roi_y1:roi_y2, roi_x1:roi_x2]
                        if anti_roi.shape[0] >= h_a and anti_roi.shape[1] >= w_a:
                            res_anti = cv2.matchTemplate(anti_roi, anti_tpl_bgr, cv2.TM_CCOEFF_NORMED)
                            _, anti_score, _, _ = cv2.minMaxLoc(res_anti)
                            if anti_score >= anti_threshold:
                                self.log(f"[排他拦截] 发现排除图得分 {anti_score:.2f}，放弃该目标。")
                                continue

                    # ==================================
                    # 闃茬嚎 2: 椤堕儴鏂囧瓧
                    # ==================================
                    top_h = int(h_m * 0.25)
                    tpl_top = main_tpl_gray[:top_h, :]
                    
                    score_top = 0.0
                    pad_slide = 5 
                    if top_h > pad_slide*2 and w_m > pad_slide*2:
                        tpl_top_core = tpl_top[pad_slide:-pad_slide, pad_slide:-pad_slide]
                        search_top = roi_gray[:int(h_m * 0.35), :]
                        if search_top.shape[0] >= tpl_top_core.shape[0] and search_top.shape[1] >= tpl_top_core.shape[1]:
                            res_top = cv2.matchTemplate(search_top, tpl_top_core, cv2.TM_CCOEFF_NORMED)
                            _, score_top, _, _ = cv2.minMaxLoc(res_top)

                    # ==================================
                    # 防线 3：右下角区域校验。
                    # ==================================
                    bottom_h = int(h_m * 0.25)
                    right_w = int(w_m * 0.35)
                    tpl_pi_box = main_tpl_bgr[h_m - bottom_h:, w_m - right_w:]

                    score_bot = 0.0
                    if bottom_h > pad_slide*2 and right_w > pad_slide*2:
                        tpl_pi_core = tpl_pi_box[pad_slide:-pad_slide, pad_slide:-pad_slide]
                        search_y1 = h_m - int(h_m * 0.35)
                        search_x1 = w_m - int(w_m * 0.45)
                        search_bot = roi_bgr[search_y1:, search_x1:]
                        
                        if search_bot.shape[0] >= tpl_pi_core.shape[0] and search_bot.shape[1] >= tpl_pi_core.shape[1]:
                            res_bot = cv2.matchTemplate(search_bot, tpl_pi_core, cv2.TM_CCOEFF_NORMED)
                            _, score_bot, _, _ = cv2.minMaxLoc(res_bot)

                    if base_score >= 0.76 and score_top >= 0.75 and score_bot >= 0.85:
                        self.log(f"[终极安全-通过] 锁定目标！总分:{base_score:.3f} | 顶部车名:{score_top:.2f} | 右下调校:{score_bot:.2f}")
                        return (x + w_m // 2 + (region[0] if region else 0), y + h_m // 2 + (region[1] if region else 0))
                    else:
                        pass  # 静默拦截，继续寻找下一个候选点。

            return None
        except Exception as e:
            self.log(f"ultimate_safe 异常: {e}")
            return None
    def wait_for_image_ultimate_safe(self, main_path, anti_path, region=None, main_threshold=0.80, anti_threshold=0.65, timeout=3, interval=0.2, mask_areas=None):
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_ultimate_safe(main_path, anti_path, region, main_threshold, anti_threshold, mask_areas=mask_areas)
            if pos: return pos
            time.sleep(interval)
        return None

    def find_new_tag_by_color(self, screen_bgr, tag_tpl, scale):
        try:
            h_s, w_s = screen_bgr.shape[:2]
            hsv = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2HSV)
            # “全新”标签是高亮黄色，先用颜色把候选区域压缩到较小范围。
            mask = cv2.inRange(hsv, np.array([22, 80, 160]), np.array([42, 255, 255]))
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidates = []
            tag_h, tag_w = tag_tpl.shape[:2]
            card_w = max(180, int(267 * scale))
            card_h = max(130, int(198 * scale))

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if area < 80 or area > 6000:
                    continue
                if w < 12 or h < 8 or w > 90 or h > 70:
                    continue
                if w / max(h, 1) < 0.6:
                    continue

                pad = max(8, int(12 * scale))
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(w_s, x + w + pad)
                y2 = min(h_s, y + h + pad)
                tag_roi = screen_bgr[y1:y2, x1:x2]
                tag_score = self.match_template_score(tag_roi, tag_tpl)
                if tag_score < 0.52:
                    continue

                card_x = int((x + w / 2) - card_w * 0.78)
                card_y = int((y + h / 2) - card_h * 0.78)
                card_x = max(0, min(card_x, w_s - card_w))
                card_y = max(0, min(card_y, h_s - card_h))
                center_x = card_x + card_w // 2
                center_y = card_y + card_h // 2

                candidates.append((tag_score, card_x, card_y, card_w, card_h, center_x, center_y, x, y, w, h))

            if not candidates:
                return []

            candidates.sort(key=lambda item: (-item[0], item[8], item[7]))
            return candidates
        except Exception as e:
            self.log(f"find_new_tag_by_color 异常: {e}")
            return []

    def validate_new_tag_grid_fallback(self, screen_bgr, tx, ty, tw, th):
        try:
            h_s, w_s = screen_bgr.shape[:2]
            if tx < int(w_s * 0.20) or ty < int(h_s * 0.18) or ty > int(h_s * 0.92):
                return None

            # 标签左上方应该能看到白色车卡主体。
            wx1 = max(0, tx - 145)
            wy1 = max(0, ty - 105)
            wx2 = max(0, tx - 12)
            wy2 = max(0, ty - 8)
            white_roi = screen_bgr[wy1:wy2, wx1:wx2]
            if white_roi.size == 0:
                return None
            white_mask = (
                (white_roi[:, :, 0] > 185) &
                (white_roi[:, :, 1] > 185) &
                (white_roi[:, :, 2] > 185)
            )
            white_ratio = float(np.count_nonzero(white_mask)) / max(1, white_mask.size)
            if white_ratio < 0.18:
                return None

            # 标签左下方通常能看到橙色车型信息或等级条，靠底部时适当向上覆盖一些。
            ox1 = max(0, tx - 190)
            oy1 = max(0, ty - 12)
            ox2 = min(w_s, tx + 85)
            oy2 = min(h_s, ty + th + 44)
            orange_roi = screen_bgr[oy1:oy2, ox1:ox2]
            if orange_roi.size == 0:
                return None
            hsv = cv2.cvtColor(orange_roi, cv2.COLOR_BGR2HSV)
            orange_mask = cv2.inRange(hsv, np.array([8, 80, 140]), np.array([32, 255, 255]))
            orange_ratio = float(np.count_nonzero(orange_mask)) / max(1, orange_mask.size)
            if orange_ratio < 0.035:
                return None

            click_x = max(0, min(w_s - 1, tx - 60))
            click_y = max(0, min(h_s - 1, ty - 42))
            return click_x, click_y, white_ratio, orange_ratio
        except Exception as e:
            self.log(f"validate_new_tag_grid_fallback 异常: {e}")
            return None

    def find_new_consumable_car_template(self, region=None, save_miss=False):
        if not self.is_running:
            return None
        try:
            vehicle_mode = self.get_buy_cj_vehicle_mode()
            template_profile = CONSUMABLE_CAR_TEMPLATE_PROFILES.get(
                vehicle_mode,
                CONSUMABLE_CAR_TEMPLATE_PROFILES["subaru"],
            )
            main_template = template_profile["main_template"]
            tag_template = template_profile["tag_template"]
            class_template = template_profile["class_template"]
            class_label = template_profile["class_label"]
            vehicle_name = template_profile["vehicle_name"]
            class_threshold = float(template_profile["class_threshold"])
            car_threshold = float(template_profile["car_threshold"])
            top_threshold = float(template_profile["top_threshold"])
            bottom_threshold = float(template_profile["bottom_threshold"])
            fixed_title_threshold = float(template_profile["fixed_title_threshold"])
            vehicle_detail_threshold = float(template_profile["vehicle_detail_threshold"])
            screen_bgr = self.capture_region(region)
            scales = []
            for s in [1.0, 0.98, 1.02, 0.95, 1.05]:
                if s not in scales:
                    scales.append(s)
            for s in self.get_scales_to_try(fast_mode=False):
                if s not in scales:
                    scales.append(s)

            final_debug = None
            for scale in scales:
                main_tpl, _ = self.get_scaled_template(main_template, scale)
                tag_tpl, _ = self.get_scaled_template(tag_template, scale)
                class_tpl, _ = self.get_scaled_template(class_template, scale)
                if main_tpl is None or tag_tpl is None or class_tpl is None:
                    continue

                h_m, w_m = main_tpl.shape[:2]
                h_t, w_t = tag_tpl.shape[:2]
                h_c, w_c = class_tpl.shape[:2]
                if h_m < 20 or w_m < 20 or h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
                    continue
                if h_t < 8 or w_t < 12 or h_t > screen_bgr.shape[0] or w_t > screen_bgr.shape[1]:
                    continue
                if h_c < 8 or w_c < 20 or h_c > screen_bgr.shape[0] or w_c > screen_bgr.shape[1]:
                    continue

                tag_res = cv2.matchTemplate(screen_bgr, tag_tpl, cv2.TM_CCOEFF_NORMED)
                loc = np.where(tag_res >= 0.72)
                tag_points = list(zip(*loc[::-1]))
                _, max_tag, _, max_loc = cv2.minMaxLoc(tag_res)
                if not tag_points and max_tag >= 0.64:
                    tag_points = [max_loc]

                checked_tags = set()
                tag_candidates = []
                # 同一个标签会产生一簇相邻命中。先按分数降序去重，避免低分辨率下
                # 左上角的弱命中先占用网格、把真正的峰值坐标过滤掉。
                scored_tag_points = sorted(
                    ((float(tag_res[ty, tx]), tx, ty) for tx, ty in tag_points),
                    reverse=True,
                )
                for tag_score, tx, ty in scored_tag_points:
                    if tx < int(screen_bgr.shape[1] * 0.20) or ty < int(screen_bgr.shape[0] * 0.18) or ty > int(screen_bgr.shape[0] * 0.90):
                        continue
                    tag_key = (tx // 18, ty // 14)
                    if tag_key in checked_tags:
                        continue
                    checked_tags.add(tag_key)
                    tag_candidates.append((ty, tx, tag_score))

                tag_candidates.sort()
                if not tag_candidates:
                    self.log(f"[TemplateCar] 缩放 {scale:.3f} 未找到全新标签候选。")
                    continue

                last_debug = None
                for ty, tx, tag_score in tag_candidates:
                    # 验证 2：在 NEW 标签下方继续确认当前车辆方案对应的等级条。
                    cx1 = max(0, int(tx - w_c * 1.45))
                    cy1 = max(0, int(ty - h_c * 0.25))
                    cx2 = min(screen_bgr.shape[1], int(tx + w_t + w_c * 0.40))
                    cy2 = min(screen_bgr.shape[0], int(ty + h_t + h_c * 1.70))
                    class_search = screen_bgr[cy1:cy2, cx1:cx2]
                    if class_search.shape[0] < h_c or class_search.shape[1] < w_c:
                        continue

                    class_res = cv2.matchTemplate(class_search, class_tpl, cv2.TM_CCOEFF_NORMED)
                    _, class_score, _, class_loc = cv2.minMaxLoc(class_res)
                    if class_score < class_threshold:
                        last_debug = {
                            "reason": f"class low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} scale:{scale:.3f}",
                            "boxes": {"new": (tx, ty, w_t, h_t)},
                            "scores": {"new": tag_score, "b600": float(class_score)},
                        }
                        self.log(
                            f"[StrictCar] 全新标签通过，但等级条不达标 NEW:{tag_score:.3f} "
                            f"{class_label}:{class_score:.3f} 缩放:{scale:.3f}"
                        )
                        continue

                    class_x = cx1 + class_loc[0]
                    class_y = cy1 + class_loc[1]

                    # 验证 3：以 NEW 标签为锚点，向左上搜索目标车辆卡片。
                    sx1 = max(0, int(tx - w_m * 1.12))
                    sy1 = max(0, int(ty - h_m * 1.08))
                    sx2 = min(screen_bgr.shape[1], int(tx + w_t + w_m * 0.12))
                    sy2 = min(screen_bgr.shape[0], int(ty + h_t + h_m * 0.18))
                    search = screen_bgr[sy1:sy2, sx1:sx2]
                    if search.shape[0] < h_m or search.shape[1] < w_m:
                        continue

                    near_res = cv2.matchTemplate(search, main_tpl, cv2.TM_CCOEFF_NORMED)
                    _, near_score, _, near_loc = cv2.minMaxLoc(near_res)
                    card_x = sx1 + near_loc[0]
                    card_y = sy1 + near_loc[1]
                    card_roi = screen_bgr[card_y:card_y + h_m, card_x:card_x + w_m]
                    if card_roi.shape[:2] != main_tpl.shape[:2]:
                        continue

                    tag_rel_x = tx - card_x
                    tag_rel_y = ty - card_y
                    boxes = {
                        "new": (tx, ty, w_t, h_t),
                        "b600": (class_x, class_y, w_c, h_c),
                        "car": (card_x, card_y, w_m, h_m),
                    }
                    scores = {
                        "new": tag_score,
                        "b600": float(class_score),
                        "car": float(near_score),
                    }
                    if not (int(w_m * 0.62) <= tag_rel_x <= int(w_m * 1.08) and int(h_m * 0.55) <= tag_rel_y <= int(h_m * 1.08)):
                        last_debug = {
                            "reason": f"rel invalid NEW:{tag_score:.3f} car:{near_score:.3f} rel:{tag_rel_x},{tag_rel_y} scale:{scale:.3f}",
                            "boxes": boxes,
                            "scores": scores,
                        }
                        self.log(
                            f"[StrictCar] 标签附近目标车位置不合理 NEW:{tag_score:.3f} "
                            f"邻近:{near_score:.3f} 相对:({tag_rel_x},{tag_rel_y}) 缩放:{scale:.3f}"
                        )
                        continue

                    if near_score < car_threshold:
                        last_debug = {
                            "reason": f"car low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} car:{near_score:.3f} scale:{scale:.3f}",
                            "boxes": boxes,
                            "scores": scores,
                        }
                        self.log(
                            f"[StrictCar] 标签附近目标车分数不足 NEW:{tag_score:.3f} "
                            f"目标:{near_score:.3f} 相对:({tag_rel_x},{tag_rel_y}) 缩放:{scale:.3f}"
                        )
                        continue

                    pad = max(4, int(5 * scale))
                    top_h = int(h_m * 0.24)
                    tpl_top = cv2.cvtColor(main_tpl[:top_h, :], cv2.COLOR_BGR2GRAY)
                    top_search_h = max(top_h + pad * 2, int(h_m * 0.34))
                    roi_top = cv2.cvtColor(card_roi[:top_search_h, :], cv2.COLOR_BGR2GRAY)
                    top_score = 0.0
                    if tpl_top.shape[0] > pad * 2 and tpl_top.shape[1] > pad * 2:
                        tpl_top_core = tpl_top[pad:-pad, pad:-pad]
                        if roi_top.shape[0] >= tpl_top_core.shape[0] and roi_top.shape[1] >= tpl_top_core.shape[1]:
                            top_res = cv2.matchTemplate(roi_top, tpl_top_core, cv2.TM_CCOEFF_NORMED)
                            _, top_score, _, _ = cv2.minMaxLoc(top_res)
                    if top_score < top_threshold:
                        last_debug = {
                            "reason": f"top low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} car:{near_score:.3f} top:{top_score:.3f}",
                            "boxes": boxes,
                            "scores": {**scores, "top": float(top_score)},
                        }
                        self.log(
                            f"[StrictCar] 车名区域验证失败: NEW:{tag_score:.3f} {class_label}:{class_score:.3f} "
                            f"目标:{near_score:.3f} 车名:{top_score:.3f} 缩放:{scale:.3f}"
                        )
                        continue

                    bottom_h = int(h_m * 0.25)
                    right_w = int(w_m * 0.35)
                    tpl_bottom = main_tpl[h_m - bottom_h:, w_m - right_w:]
                    roi_bottom = card_roi[h_m - int(h_m * 0.36):, w_m - int(w_m * 0.46):]
                    bottom_score = 0.0
                    if tpl_bottom.shape[0] > pad * 2 and tpl_bottom.shape[1] > pad * 2:
                        tpl_bottom_core = tpl_bottom[pad:-pad, pad:-pad]
                        if roi_bottom.shape[0] >= tpl_bottom_core.shape[0] and roi_bottom.shape[1] >= tpl_bottom_core.shape[1]:
                            bottom_res = cv2.matchTemplate(roi_bottom, tpl_bottom_core, cv2.TM_CCOEFF_NORMED)
                            _, bottom_score, _, _ = cv2.minMaxLoc(bottom_res)
                    if bottom_score < bottom_threshold:
                        last_debug = {
                            "reason": f"bottom low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} car:{near_score:.3f} top:{top_score:.3f} bottom:{bottom_score:.3f}",
                            "boxes": boxes,
                            "scores": {**scores, "top": float(top_score), "bottom": float(bottom_score)},
                        }
                        self.log(
                            f"[StrictCar] 底部等级区域验证失败: NEW:{tag_score:.3f} {class_label}:{class_score:.3f} "
                            f"目标:{near_score:.3f} 车名:{top_score:.3f} 底部:{bottom_score:.3f} 缩放:{scale:.3f}"
                        )
                        continue

                    # 马自达卡片的大面积白底会让其他车型也取得较高整卡分数。
                    # 固定对齐验证标题与车辆主体，不允许在邻近区域内滑动寻找相似结构。
                    fixed_title_score = 1.0
                    if fixed_title_threshold > 0:
                        fx1 = int(w_m * 0.05)
                        fx2 = int(w_m * 0.95)
                        fy2 = max(8, int(h_m * 0.28))
                        tpl_fixed_title = cv2.cvtColor(main_tpl[:fy2, fx1:fx2], cv2.COLOR_BGR2GRAY)
                        roi_fixed_title = cv2.cvtColor(card_roi[:fy2, fx1:fx2], cv2.COLOR_BGR2GRAY)
                        fixed_title_score = float(cv2.matchTemplate(
                            roi_fixed_title,
                            tpl_fixed_title,
                            cv2.TM_CCOEFF_NORMED,
                        )[0, 0])
                        if fixed_title_score < fixed_title_threshold:
                            last_debug = {
                                "reason": (
                                    f"fixed title low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} "
                                    f"car:{near_score:.3f} title_fixed:{fixed_title_score:.3f}"
                                ),
                                "boxes": boxes,
                                "scores": {**scores, "title_fixed": fixed_title_score},
                            }
                            self.log(
                                f"[StrictCar] 固定车名验证失败: {vehicle_name} "
                                f"车名固定区域:{fixed_title_score:.3f} 阈值:{fixed_title_threshold:.3f}"
                            )
                            continue

                    vehicle_detail_score = 1.0
                    if vehicle_detail_threshold > 0:
                        vx1 = int(w_m * 0.18)
                        vx2 = int(w_m * 0.83)
                        vy1 = int(h_m * 0.30)
                        vy2 = int(h_m * 0.80)
                        tpl_vehicle = main_tpl[vy1:vy2, vx1:vx2]
                        roi_vehicle = card_roi[vy1:vy2, vx1:vx2]
                        vehicle_detail_score = float(cv2.matchTemplate(
                            roi_vehicle,
                            tpl_vehicle,
                            cv2.TM_CCOEFF_NORMED,
                        )[0, 0])
                        if vehicle_detail_score < vehicle_detail_threshold:
                            last_debug = {
                                "reason": (
                                    f"vehicle detail low NEW:{tag_score:.3f} {class_label}:{class_score:.3f} "
                                    f"car:{near_score:.3f} vehicle:{vehicle_detail_score:.3f}"
                                ),
                                "boxes": boxes,
                                "scores": {**scores, "vehicle_detail": vehicle_detail_score},
                            }
                            self.log(
                                f"[StrictCar] 车辆主体验证失败: {vehicle_name} "
                                f"涂装/车型:{vehicle_detail_score:.3f} 阈值:{vehicle_detail_threshold:.3f}"
                            )
                            continue

                    click_x = card_x + w_m // 2 + (region[0] if region else 0)
                    click_y = card_y + h_m // 2 + (region[1] if region else 0)
                    self.log(
                        f"[StrictCar] {vehicle_name} 全新+{class_label}+目标车验证通过: "
                        f"NEW:{tag_score:.3f} {class_label}:{class_score:.3f} "
                        f"目标:{near_score:.3f} 车名:{top_score:.3f} 底部:{bottom_score:.3f} "
                        f"固定车名:{fixed_title_score:.3f} 涂装/车型:{vehicle_detail_score:.3f} "
                        f"标签相对:({tag_rel_x},{tag_rel_y}) 等级:({class_x},{class_y}) 缩放:{scale:.3f}"
                    )
                    if self.config.get("ai_auto_capture", False):
                        self.save_template_car_debug(
                            screen_bgr,
                            "pass",
                            reason=f"pass scale:{scale:.3f}",
                            boxes=boxes,
                            scores={
                                **scores,
                                "top": float(top_score),
                                "bottom": float(bottom_score),
                                "title_fixed": fixed_title_score,
                                "vehicle_detail": vehicle_detail_score,
                            },
                            click=(click_x - (region[0] if region else 0), click_y - (region[1] if region else 0)),
                            force=True,
                        )
                    return (click_x, click_y)

                if last_debug:
                    final_debug = last_debug

            if save_miss:
                if final_debug:
                    self.save_template_car_debug(
                        screen_bgr,
                        "miss",
                        reason=final_debug.get("reason", ""),
                        boxes=final_debug.get("boxes"),
                        scores=final_debug.get("scores"),
                        force=True,
                    )
                else:
                    self.save_template_car_debug(screen_bgr, "miss", reason="no strict car candidate", force=True)
            if hasattr(self, "capture_diagnostic_snapshot"):
                miss_reason = final_debug.get("reason", "no strict car candidate") if final_debug else "no strict car candidate"
                self.capture_diagnostic_snapshot(
                    "miss_buy_new_car",
                    region=region,
                    image_bgr=screen_bgr,
                    reason="批量买车未识别到目标新车",
                    level="WARN",
                    meta={"detail": miss_reason, "debug": final_debug or {}},
                    dedupe_key="miss:buy_new_car",
                )
            return None
        except Exception as e:
            self.log(f"find_new_consumable_car_template 异常: {e}")
            return None

    def wait_for_new_consumable_car(self, timeout=3, interval=0.2):
        ai_enabled = self.config.get("ai_assist", False)
        ai_first = ai_enabled and self.config.get("ai_prefer", False)
        ai_only = ai_enabled and self.config.get("ai_only", False)
        save_debug = self.config.get("ai_auto_capture", False)

        if self.is_running and (ai_first or ai_only):
            pos = self.find_new_consumable_car_with_ai(
                region=self.regions["全界面"],
                save_miss=save_debug,
            )
            if pos:
                return pos
            if ai_only:
                return None

        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_new_consumable_car_template(region=self.regions["全界面"], save_miss=False)
            if pos:
                return pos
            time.sleep(interval)

        if self.is_running and ai_enabled and not ai_first:
            pos = self.find_new_consumable_car_with_ai(
                region=self.regions["全界面"],
                save_miss=save_debug,
            )
            if pos:
                return pos

        if self.is_running:
            return self.find_new_consumable_car_template(
                region=self.regions["全界面"],
                save_miss=save_debug,
            )
        return None

    def find_image_smart(self, template_path, primary_region=None, fallback_region=None, threshold=0.75, fast_mode=True):
        if primary_region:
            pos = self.find_image(template_path, region=primary_region, threshold=threshold, fast_mode=fast_mode)
            if pos:
                return pos

        if fallback_region:
            return self.find_image(template_path, region=fallback_region, threshold=threshold, fast_mode=fast_mode)

        return None
    def to_gray_image(self, img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    def to_edge_image(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        edge = cv2.Canny(blur, 50, 150)
        return edge
    def crop_center_ratio(self, img, ratio=0.6):
        h, w = img.shape[:2]
        ch = int(h * ratio)
        cw = int(w * ratio)
        y1 = max(0, (h - ch) // 2)
        x1 = max(0, (w - cw) // 2)
        return img[y1:y1 + ch, x1:x1 + cw]

    def match_normalized_detail_score(self, src, tpl, detail_box):
        if not detail_box or len(detail_box) != 4 or src is None or tpl is None:
            return 1.0
        try:
            sh, sw = src.shape[:2]
            th, tw = tpl.shape[:2]
            x1, y1, x2, y2 = [float(v) for v in detail_box]
            src_detail = src[
                max(0, int(sh * y1)):min(sh, int(sh * y2)),
                max(0, int(sw * x1)):min(sw, int(sw * x2)),
            ]
            tpl_detail = tpl[
                max(0, int(th * y1)):min(th, int(th * y2)),
                max(0, int(tw * x1)):min(tw, int(tw * x2)),
            ]
            if src_detail.shape[:2] != tpl_detail.shape[:2]:
                return 0.0
            return self.match_template_score(src_detail, tpl_detail)
        except Exception:
            return 0.0

    def find_reference_crop_gray(self, reference_path, crop_box, region=None,
                                 threshold=0.72, fast_mode=False, invert_mode=False):
        """Match a stable normalized crop from a full reference screenshot."""
        if not self.is_running or not crop_box or len(crop_box) != 4:
            return None
        try:
            cache = getattr(self, "reference_crop_cache", None)
            if cache is None:
                cache = {}
                self.reference_crop_cache = cache
            cache_key = (reference_path, tuple(float(v) for v in crop_box))
            crop_gray = cache.get(cache_key)
            if crop_gray is None:
                reference = cv2.imread(get_img_path(reference_path), cv2.IMREAD_COLOR)
                if reference is None:
                    self.log(f"参考截图读取失败: {reference_path}")
                    return None

                rh, rw = reference.shape[:2]
                x1, y1, x2, y2 = [float(v) for v in crop_box]
                crop = reference[
                    max(0, int(rh * y1)):min(rh, int(rh * y2)),
                    max(0, int(rw * x1)):min(rw, int(rw * x2)),
                ]
                if crop.shape[0] < 5 or crop.shape[1] < 5:
                    return None
                crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                cache[cache_key] = crop_gray

            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            effective_threshold = self.get_calibrated_gray_threshold(threshold)

            for scale in self.get_scales_to_try(fast_mode=fast_mode):
                tpl = crop_gray if scale == 1.0 else cv2.resize(
                    crop_gray,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_AREA,
                )
                th, tw = tpl.shape[:2]
                if th < 5 or tw < 5 or th > screen_gray.shape[0] or tw > screen_gray.shape[1]:
                    continue

                variants = [("normal", tpl)]
                if invert_mode:
                    variants.append(("invert", cv2.bitwise_not(tpl)))
                for mode, candidate in variants:
                    result = cv2.matchTemplate(screen_gray, candidate, cv2.TM_CCOEFF_NORMED)
                    _, score, _, loc = cv2.minMaxLoc(result)
                    if score >= effective_threshold:
                        cx = loc[0] + tw // 2 + (region[0] if region else 0)
                        cy = loc[1] + th // 2 + (region[1] if region else 0)
                        self.log(
                            f"[ReferenceCrop] 命中 {reference_path} mode={mode} "
                            f"score={score:.3f} scale={scale:.3f}"
                        )
                        return (cx, cy)

            return None
        except Exception as e:
            self.log(f"find_reference_crop_gray 异常: {reference_path}: {e}")
            return None

    def score_fixed_reference_crop_gray(self, reference_path, crop_box, screen_bgr=None):
        """Score the same normalized screen location as a reference crop without position search."""
        if not crop_box or len(crop_box) != 4:
            return 0.0
        try:
            cache = getattr(self, "fixed_reference_crop_cache", None)
            if cache is None:
                cache = {}
                self.fixed_reference_crop_cache = cache

            cache_key = (reference_path, tuple(float(v) for v in crop_box))
            reference_gray = cache.get(cache_key)
            if reference_gray is None:
                reference = cv2.imread(get_img_path(reference_path), cv2.IMREAD_COLOR)
                if reference is None:
                    return 0.0
                rh, rw = reference.shape[:2]
                x1, y1, x2, y2 = [float(v) for v in crop_box]
                reference_crop = reference[
                    max(0, int(rh * y1)):min(rh, int(rh * y2)),
                    max(0, int(rw * x1)):min(rw, int(rw * x2)),
                ]
                if reference_crop.shape[0] < 5 or reference_crop.shape[1] < 5:
                    return 0.0
                reference_gray = cv2.cvtColor(reference_crop, cv2.COLOR_BGR2GRAY)
                cache[cache_key] = reference_gray

            if screen_bgr is None:
                screen_bgr = self.capture_region(self.regions.get("全界面"))
            sh, sw = screen_bgr.shape[:2]
            x1, y1, x2, y2 = [float(v) for v in crop_box]
            screen_crop = screen_bgr[
                max(0, int(sh * y1)):min(sh, int(sh * y2)),
                max(0, int(sw * x1)):min(sw, int(sw * x2)),
            ]
            if screen_crop.shape[0] < 5 or screen_crop.shape[1] < 5:
                return 0.0

            screen_gray = cv2.cvtColor(screen_crop, cv2.COLOR_BGR2GRAY)
            template = cv2.resize(
                reference_gray,
                (screen_gray.shape[1], screen_gray.shape[0]),
                interpolation=cv2.INTER_AREA,
            )
            return float(cv2.matchTemplate(
                screen_gray,
                template,
                cv2.TM_CCOEFF_NORMED,
            )[0, 0])
        except Exception as e:
            self.log(f"score_fixed_reference_crop_gray 异常: {reference_path}: {e}")
            return 0.0

    def find_image_gray(self, template_path, region=None, threshold=0.75, fast_mode=True, invert_mode=False):
        """
        灰度模板匹配，支持多分辨率缩放和可选反相匹配。

        参数:
            template_path (str): 模板图片路径。
            region (tuple|list|None): 搜索区域，格式通常为 (x, y, w, h)；None 表示全屏或默认区域。
            threshold (float): 匹配阈值，通常在 0~1 之间，越高越严格。
            fast_mode (bool): 是否使用快速缩放模式；True 表示尝试较少缩放比。
            invert_mode (bool): 是否同时尝试原图和反相模板，适合黑白反转场景。

        返回:
            tuple|None: 命中时返回中心点坐标 `(x, y)`，未命中返回 `None`。
        """
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            effective_threshold = self.get_calibrated_gray_threshold(threshold)
            region_name = next((name for name, rect in self.regions.items() if rect == region), "custom") if region else "全界面"
            started = time.time()
            best_score = 0.0
            best_scale = 1.0
            best_mode = "原图"
            best_position = None

            # 模板只读取一次，避免每个缩放比都重复加载。
            tpl_gray_raw = self.load_template_gray(template_path)
            if tpl_gray_raw is None:
                return None

            for scale in scales_to_try:
                # 始终从原始模板开始缩放，避免多次 resize 造成污染。
                tpl_gray = tpl_gray_raw
                if scale != 1.0:
                    tpl_gray = cv2.resize(tpl_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                h, w = tpl_gray.shape[:2]
                if h < 5 or w < 5 or h > screen_gray.shape[0] or w > screen_gray.shape[1]:
                    continue

                # ==============================
                # 原图灰度匹配
                # ==============================
                res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_score:
                    best_score = float(max_val)
                    best_scale = float(scale)
                    best_mode = "原图"
                    best_position = (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )
                if max_val >= effective_threshold:
                    if hasattr(self, "record_diagnostic_match"):
                        self.record_diagnostic_match(
                            "find_image_gray",
                            template_path,
                            region_name=region_name,
                            threshold=threshold,
                            effective_threshold=effective_threshold,
                            fast_mode=fast_mode,
                            invert_mode=invert_mode,
                            hit=True,
                            score=max_val,
                            scale=scale,
                            mode="原图",
                            template=template_path,
                            position=best_position,
                            elapsed_ms=int((time.time() - started) * 1000),
                        )
                    self.log(f"[GrayMatch] 命中: {template_path} | 模式: 原图 | 灰度得分: {max_val:.3f} (阈值 {effective_threshold}) | 缩放比: {scale:.3f}")
                    return (
                        max_loc[0] + w // 2 + (region[0] if region else 0),
                        max_loc[1] + h // 2 + (region[1] if region else 0),
                    )

                # ==============================
                # 反相模板匹配，用于黑白反转场景。
                # ==============================
                if invert_mode:
                    tpl_inv = 255 - tpl_gray
                    res_inv = cv2.matchTemplate(screen_gray, tpl_inv, cv2.TM_CCOEFF_NORMED)
                    _, max_val_inv, _, max_loc_inv = cv2.minMaxLoc(res_inv)
                    if max_val_inv > best_score:
                        best_score = float(max_val_inv)
                        best_scale = float(scale)
                        best_mode = "反相"
                        best_position = (
                            max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                            max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                        )
                    if max_val_inv >= effective_threshold:
                        if hasattr(self, "record_diagnostic_match"):
                            self.record_diagnostic_match(
                                "find_image_gray",
                                template_path,
                                region_name=region_name,
                                threshold=threshold,
                                effective_threshold=effective_threshold,
                                fast_mode=fast_mode,
                                invert_mode=invert_mode,
                                hit=True,
                                score=max_val_inv,
                                scale=scale,
                                mode="反相",
                                template=template_path,
                                position=best_position,
                                elapsed_ms=int((time.time() - started) * 1000),
                            )
                        self.log(f"[GrayMatch] 命中: {template_path} | 模式: 反相 | 灰度得分: {max_val_inv:.3f} (阈值 {effective_threshold}) | 缩放比: {scale:.3f}")
                        return (
                            max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                            max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                        )

            if hasattr(self, "record_diagnostic_match"):
                self.record_diagnostic_match(
                    "find_image_gray",
                    template_path,
                    region_name=region_name,
                    threshold=threshold,
                    effective_threshold=effective_threshold,
                    fast_mode=fast_mode,
                    invert_mode=invert_mode,
                    hit=False,
                    score=best_score,
                    scale=best_scale,
                    mode=best_mode,
                    template=template_path,
                    position=best_position,
                    elapsed_ms=int((time.time() - started) * 1000),
                )
            self.capture_diagnostic_template_miss(
                template_path,
                region=region,
                screen_bgr=screen_bgr,
                best_score=best_score,
                threshold=effective_threshold,
                extra={"mode": best_mode, "scale": best_scale},
            )
            return None
        except Exception as e:
            self.log(f"find_image_gray 异常: {e}")
            return None
    def find_any_image_gray(self, image_list, region=None, threshold=0.75, fast_mode=True, invert_mode=False):
        """
        灰度多模板匹配，支持多分辨率缩放和可选反相匹配。

        参数:
            image_list (list): 模板路径列表，例如 `["a.png", "b.png", "c.png"]`。
            region (tuple|list|None): 搜索区域，None 表示全屏或默认区域。
            threshold (float): 匹配阈值。
            fast_mode (bool): 是否使用快速缩放模式。
            invert_mode (bool): 是否同时尝试原图和反相模板。

        返回:
            tuple|None: 命中任意一张模板时返回中心点坐标 `(x, y)`，否则返回 `None`。
        """
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)
            effective_threshold = self.get_calibrated_gray_threshold(threshold)
            region_name = next((name for name, rect in self.regions.items() if rect == region), "custom") if region else "全界面"
            started = time.time()
            best_template = None
            best_score = 0.0
            best_scale = 1.0
            best_mode = "原图"
            best_position = None

            for img_path in image_list:
                # 模板只读取一次，避免重复加载。
                tpl_gray_raw = self.load_template_gray(img_path)
                if tpl_gray_raw is None:
                    continue

                for scale in scales_to_try:
                    # 始终从原始模板开始缩放。
                    tpl_gray = tpl_gray_raw
                    if scale != 1.0:
                        tpl_gray = cv2.resize(tpl_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    h, w = tpl_gray.shape[:2]
                    if h < 5 or w < 5 or h > screen_gray.shape[0] or w > screen_gray.shape[1]:
                        continue

                    # ==============================
                    # 原图灰度匹配
                    # ==============================
                    res = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val > best_score:
                        best_template = img_path
                        best_score = float(max_val)
                        best_scale = float(scale)
                        best_mode = "原图"
                        best_position = (
                            max_loc[0] + w // 2 + (region[0] if region else 0),
                            max_loc[1] + h // 2 + (region[1] if region else 0),
                        )
                    if max_val >= effective_threshold:
                        if hasattr(self, "record_diagnostic_match"):
                            self.record_diagnostic_match(
                                "find_any_image_gray",
                                img_path,
                                region_name=region_name,
                                threshold=threshold,
                                effective_threshold=effective_threshold,
                                fast_mode=fast_mode,
                                invert_mode=invert_mode,
                                hit=True,
                                score=max_val,
                                scale=scale,
                                mode="原图",
                                template=img_path,
                                position=best_position,
                                elapsed_ms=int((time.time() - started) * 1000),
                            )
                        self.log(f"[GrayMatchAny] 命中: {img_path} | 模式: 原图 | 灰度得分: {max_val:.3f} (阈值 {effective_threshold}) | 缩放比: {scale:.3f}")
                        return (
                            max_loc[0] + w // 2 + (region[0] if region else 0),
                            max_loc[1] + h // 2 + (region[1] if region else 0),
                        )

                    # ==============================
                    # 反相模板匹配，用于黑白反转场景。
                    # ==============================
                    if invert_mode:
                        tpl_inv = 255 - tpl_gray
                        res_inv = cv2.matchTemplate(screen_gray, tpl_inv, cv2.TM_CCOEFF_NORMED)
                        _, max_val_inv, _, max_loc_inv = cv2.minMaxLoc(res_inv)
                        if max_val_inv > best_score:
                            best_template = img_path
                            best_score = float(max_val_inv)
                            best_scale = float(scale)
                            best_mode = "反相"
                            best_position = (
                                max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                                max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                            )
                        if max_val_inv >= effective_threshold:
                            if hasattr(self, "record_diagnostic_match"):
                                self.record_diagnostic_match(
                                    "find_any_image_gray",
                                    img_path,
                                    region_name=region_name,
                                    threshold=threshold,
                                    effective_threshold=effective_threshold,
                                    fast_mode=fast_mode,
                                    invert_mode=invert_mode,
                                    hit=True,
                                    score=max_val_inv,
                                    scale=scale,
                                    mode="反相",
                                    template=img_path,
                                    position=best_position,
                                    elapsed_ms=int((time.time() - started) * 1000),
                                )
                            self.log(f"[GrayMatchAny] 命中: {img_path} | 模式: 反相 | 灰度得分: {max_val_inv:.3f} (阈值 {effective_threshold}) | 缩放比: {scale:.3f}")
                            return (
                                max_loc_inv[0] + w // 2 + (region[0] if region else 0),
                                max_loc_inv[1] + h // 2 + (region[1] if region else 0),
                            )

            if hasattr(self, "record_diagnostic_match"):
                self.record_diagnostic_match(
                    "find_any_image_gray",
                    best_template or "|".join(image_list),
                    region_name=region_name,
                    threshold=threshold,
                    effective_threshold=effective_threshold,
                    fast_mode=fast_mode,
                    invert_mode=invert_mode,
                    hit=False,
                    score=best_score,
                    scale=best_scale,
                    mode=best_mode,
                    template=best_template,
                    position=best_position,
                    elapsed_ms=int((time.time() - started) * 1000),
                    extra={"candidates": image_list},
                )
            if best_template:
                self.capture_diagnostic_template_miss(
                    best_template,
                    region=region,
                    screen_bgr=screen_bgr,
                    best_score=best_score,
                    threshold=effective_threshold,
                    extra={"mode": best_mode, "scale": best_scale, "candidates": image_list},
                )
            return None
        except Exception as e:
            self.log(f"find_any_image_gray 异常: {e}")
            return None

    def wait_for_any_image_gray(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False):
        """
        等待多张灰度模板中的任意一张出现。

        参数:
            image_list (list): 模板路径列表。
            region (tuple|list|None): 搜索区域。
            threshold (float): 匹配阈值。
            timeout (int|float): 最大等待时间，单位秒。
            interval (int|float): 每次检测失败后的等待间隔，单位秒。
            fast_mode (bool): 是否使用快速缩放模式。
            invert_mode (bool): 是否启用反相模板匹配。

        返回:
            tuple|None: 超时前命中则返回中心点坐标 `(x, y)`，否则返回 `None`。
        """
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_any_image_gray(
                image_list,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode,
                invert_mode=invert_mode
            )
            if pos:
                return pos

            # 分段短睡眠，保持可中断。
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None

    def wait_for_image_gray(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.3, fast_mode=True, invert_mode=False):
        """
        等待单张灰度模板出现。

        参数:
            template_path (str): 模板图片路径。
            region (tuple|list|None): 搜索区域。
            threshold (float): 匹配阈值。
            timeout (int|float): 最大等待时间，单位秒。
            interval (int|float): 每次检测失败后的等待间隔，单位秒。
            fast_mode (bool): 是否使用快速缩放模式。
            invert_mode (bool): 是否启用反相模板匹配。

        返回:
            tuple|None: 超时前命中则返回中心点坐标 `(x, y)`，否则返回 `None`。
        """
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_gray(
                template_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode,
                invert_mode=invert_mode
            )
            if pos:
                return pos

            # 分段短睡眠，保持可中断。
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None

    def find_any_image_transparent(self, image_list, region=None, threshold=0.70, fast_mode=True):
        """Find any transparent template from a list."""
        if not self.is_running:
            return None
        try:
            screen_bgr = self.capture_region(region)
            scales_to_try = self.get_scales_to_try(fast_mode=fast_mode)

            for template_path in image_list:
                tpl_bgra = self.load_template_transparent(template_path)
                if tpl_bgra is None:
                    continue
                
                # 如果模板没有透明通道，则退化为普通模板匹配。
                if tpl_bgra.shape[2] != 4:
                    pos = self.find_image_in_screen(screen_bgr, template_path, region, threshold, fast_mode)
                    if pos: return pos
                    continue

                for scale in scales_to_try:
                    if scale == 1.0:
                        tpl_scaled = tpl_bgra.copy()
                    else:
                        tpl_scaled = cv2.resize(tpl_bgra, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

                    h, w = tpl_scaled.shape[:2]
                    if h < 5 or w < 5 or h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
                        continue

                    tpl_bgr = tpl_scaled[:, :, :3]
                    alpha_mask = tpl_scaled[:, :, 3]

                    res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED, mask=alpha_mask)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    if max_val >= threshold:
                        # 输出多模板透明匹配日志。
                        self.log(f"[AlphaMatchAny] 命中(忽略背景): {template_path} | 得分: {max_val:.3f} (阈值 {threshold}) | 缩放比: {scale:.3f}")
                        return (
                            max_loc[0] + w // 2 + (region[0] if region else 0),
                            max_loc[1] + h // 2 + (region[1] if region else 0),
                        )
            return None
        except Exception as e:
            self.log(f"find_any_image_transparent 异常: {e}")
            return None

    def wait_for_any_image_transparent(self, image_list, region=None, threshold=0.70, timeout=30, interval=0.4, fast_mode=True):
        """Wait for any transparent template from a list to appear."""
        start = time.time()
        while self.is_running and time.time() - start < timeout:
            pos = self.find_any_image_transparent(image_list, region, threshold, fast_mode)
            if pos:
                return pos
            
            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)
        return None
    def wait_for_any_image(self, image_list, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            try:
                screen_bgr = self.capture_region(region)
                for img_path in image_list:
                    pos = self.find_image_in_screen(
                        screen_bgr,
                        img_path,
                        region=region,
                        threshold=threshold,
                        fast_mode=fast_mode
                    )
                    if pos:
                        return pos
            except Exception as e:
                self.log(f"wait_for_any_image 异常: {e}")

            if log_text:
                self.log(log_text)

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def wait_for_image(self, template_path, region=None, threshold=0.75, timeout=30, interval=0.4, fast_mode=True, log_text=None):
        return self.wait_for_any_image(
            [template_path],
            region=region,
            threshold=threshold,
            timeout=timeout,
            interval=interval,
            fast_mode=fast_mode,
            log_text=log_text
        )

    def wait_for_buy_and_used_car(self, timeout=20):
        targets = ["BNandUC.png"]
        gray_profile = get_recognition_profile(self, "matcher.buy_used_gray", timeout=timeout)
        full_profile = get_recognition_profile(self, "matcher.buy_used_full", timeout=timeout)
        fast_profile = get_recognition_profile(self, "matcher.buy_used_fast", timeout=timeout)
        checks = [
            ("gray", lambda: self.wait_for_any_image_gray(targets, region=self.regions["左"], threshold=gray_profile["threshold"], timeout=gray_profile["timeout"], interval=gray_profile["interval"], fast_mode=gray_profile["fast_mode"])),
            ("full", lambda: self.wait_for_any_image(targets, region=self.regions["全界面"], threshold=full_profile["threshold"], timeout=full_profile["timeout"], interval=full_profile["interval"], fast_mode=full_profile["fast_mode"])),
            ("fast", lambda: self.wait_for_any_image(targets, region=self.regions["左"], threshold=fast_profile["threshold"], timeout=fast_profile["timeout"], interval=fast_profile["interval"], fast_mode=fast_profile["fast_mode"])),
        ]

        for label, fn in checks:
            pos = fn()
            if pos:
                self.log(f"[BuyNewUsed] 命中模式: {label}")
                return pos
        return None

    def wait_for_image_with_element(self, main_path, sub_path, region=None, threshold=0.85, timeout=30, interval=0.4, fast_mode=True):
        start = time.time()

        while self.is_running and time.time() - start < timeout:
            pos = self.find_image_with_element(
                main_path,
                sub_path,
                region=region,
                threshold=threshold,
                fast_mode=fast_mode
            )
            if pos:
                return pos

            sleep_end = time.time() + interval
            while self.is_running and time.time() < sleep_end:
                time.sleep(0.05)

        return None

    def match_template_score(self, src, tpl):
        try:
            if tpl is None or src is None:
                return 0.0
            th, tw = tpl.shape[:2]
            sh, sw = src.shape[:2]
            if th < 5 or tw < 5 or th > sh or tw > sw:
                return 0.0
            res = cv2.matchTemplate(src, tpl, cv2.TM_CCOEFF_NORMED)
            return cv2.minMaxLoc(res)[1]
        except Exception:
            return 0.0
    #===============================
    #---娴嬭瘯鍑芥暟-----
    #===============================
    def start_test_find_image(self):
        """F3 test helper: repeatedly search targets without clicking them."""
        if self.is_running:
            self.log("已有任务正在运行，无法执行 F3 测图。")
            return

        self.is_running = True
        self.is_paused = False
        self.save_config()

        self.reset_run_stats()
        self.update_running_state("running")
        self.update_running_ui("F3测图", 0, 12)
        self.ui_call(self.lbl_runtime_loop.configure, text="测试模式")
        self.update_timer()

        self.log("====== 开始 F3 测试原二阶段找图 ======")

        def test_runner():
            try:
                if not self.check_and_focus_game():
                    self.log("未能聚焦游戏窗口，测试结束。")
                    return

                found_positions = []
                mask_areas = []

                for i in range(15):
                    if not self.is_running:
                        return
                    self.check_pause()

                    pos = self.find_image_with_element_multi(
                        "newCC.png",
                        "newcartag.png",
                        region=self.regions["全界面"],
                        main_threshold=0.70,
                        like_threshold=0.70,
                        final_threshold=0.70,
                        fast_mode=True,
                        mask_areas=mask_areas
                    )

                    if not pos:
                        self.log(f"第 {i + 1} 次查找：未找到新的目标，测试结束。")
                        break

                    x, y = int(pos[0]), int(pos[1])

                    duplicated = False
                    for old_x, old_y in found_positions:
                        if abs(x - old_x) <= 80 and abs(y - old_y) <= 80:
                            duplicated = True
                            break

                    region_x, region_y, _, _ = self.regions["全界面"]
                    local_x = x - region_x
                    local_y = y - region_y

                    block_w = 210
                    block_h = 120
                    mask_areas.append((
                        local_x - block_w // 2,
                        local_y - block_h // 2,
                        local_x + block_w // 2,
                        local_y + block_h // 2
                    ))

                    if duplicated:
                        self.log(f"F3 测试：识别到重复目标 ({x}, {y})，已扩大遮罩，继续查找。")
                        continue

                    found_positions.append((x, y))
                    self.update_running_ui("F3测试找图", len(found_positions), 12)
                    self.log(f"F3测试：找到第 {len(found_positions)} 个目标 -> ({x}, {y})")
                    self.hw_mouse_move(x, y)
                    time.sleep(0.5)

                self.log(f"F3 测试完成，共找到 {len(found_positions)} 个目标。")

            except Exception as e:
                self.log(f"F3测试异常: {e}")
            finally:
                self.stop_all()

        self.current_thread = threading.Thread(target=test_runner, daemon=True)
        self.current_thread.start()
    # ==========================================
    # --- 模块：跑图前置与循环跑图 ---

