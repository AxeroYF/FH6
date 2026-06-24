import os
import threading
import time
import cv2
import numpy as np
from app_resources import get_app_dir

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

def find_new_consumable_car_with_ai(self, region=None, save_miss=True):
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

def save_template_car_debug(self, screen_bgr, status, reason="", boxes=None, scores=None, click=None, force=False):
    try:
        now = time.time()
        if status == "miss" and not force:
            # wait_for_new_consumable_car 会循环调用，miss 图做节流即可。
            if now - getattr(self, "strict_car_debug_last_miss_save", 0.0) < 1.5:
                return
            self.strict_car_debug_last_miss_save = now

        self.strict_car_debug_seq += 1
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_{self.strict_car_debug_seq:04d}_{status}"
        root = os.path.join(get_app_dir(), "debug", "car_select")
        if status == "pass":
            self.cleanup_recent_template_car_miss(root, keep_seconds=12.0)

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

def cleanup_recent_template_car_miss(self, root, keep_seconds=12.0):
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
        pos_target = self.wait_for_new_consumable_car(timeout=1.5, interval=0.2)

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
            timeout=1.2,
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
                time.sleep(0.8)
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
                time.sleep(0.8)
                self.hw_press("esc")
                time.sleep(0.8)
                if self.should_switch_skillcar_after_cj():
                    if not self.prepare_skillcar_for_next_race_after_cj():
                        return False
                else:
                    self.hw_press("esc")
                    time.sleep(0.8)
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
        time.sleep(0.8)
        self.hw_press("esc")
        time.sleep(0.8)
    return True



