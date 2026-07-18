"""Standalone Mazda vehicle deletion flow under incremental validation."""

import time

import cv2

from flow_common import press_with_pause
from flow_race import _prepare_skillcar_for_race
from recognition_config import get_recognition_profile


DELETE_VEHICLE_PROFILE = {
    "vehicle_mode": "mazda",
    "vehicle_name": "马自达 #123 Mad Mike 808 Wagon",
}

DELETE_FILTER_SEQUENCE = (
    ("重复项", "delete_filter_duplicate.png", 0.82),
    ("S1", "delete_filter_s1.png", 0.82),
    ("漂移赛车", "delete_filter_drift.png", 0.82),
    ("传奇", "delete_filter_legendary.png", 0.82),
)


def _to_gray_2d(image):
    """Normalize captures and cached templates to a two-dimensional gray image."""
    if image is None:
        return None
    if image.ndim == 2:
        return image
    if image.ndim == 3:
        channels = image.shape[2]
        if channels == 1:
            return image[:, :, 0]
        if channels == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    raise ValueError(f"Unsupported image shape for gray conversion: {image.shape}")


def _get_delete_template_scales(self, scale_spread):
    """Return robust scales for deletion templates captured at 2560px width.

    Global calibration can legitimately fall back to 1.0 when a task starts on
    a screen without a reliable anchor.  Deletion templates are known to come
    from a 2560px capture, so always include the scale implied by the current
    game-window width instead of relying exclusively on calibration.
    """
    full_region = self.regions.get("全界面")
    current_width = float(full_region[2]) if full_region else 2560.0
    expected = current_width / 2560.0
    calibrated = float(
        (getattr(self, "match_calibration", {}) or {}).get("preferred_scale", expected)
        or expected
    )
    spread = max(0.002, float(scale_spread))
    scales = []
    for base in (expected, calibrated):
        for scale in (base, base * (1.0 - spread), base * (1.0 + spread)):
            scale = round(max(0.45, min(1.8, scale)), 3)
            if scale not in scales:
                scales.append(scale)
    return scales


def _find_filter_tag_fast(
    self,
    template_name,
    threshold,
    scale_spread,
    selected_dark_ratio,
    selected_mean_max,
    selected_glyph_dice,
):
    """Match text and require the candidate to be a black selected row."""
    region = self.regions.get("左", self.regions["全界面"])
    started = time.time()
    screen_gray = _to_gray_2d(self.capture_region(region))
    template_gray = _to_gray_2d(self.load_template_gray(template_name))
    if template_gray is None:
        return None

    scales = _get_delete_template_scales(self, scale_spread)
    calibrated = scales[0]

    effective_threshold = self.get_calibrated_gray_threshold(threshold)
    best_score = 0.0
    best_scale = calibrated
    best_position = None
    best_dark_ratio = 0.0
    best_mean = 255.0
    best_glyph_dice = 0.0

    for scale in scales:
        template = template_gray
        if scale != 1.0:
            template = cv2.resize(
                template_gray,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )
        template = _to_gray_2d(template)
        height, width = template.shape[:2]
        if height < 5 or width < 5 or height > screen_gray.shape[0] or width > screen_gray.shape[1]:
            continue

        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        position = (
            location[0] + width // 2 + region[0],
            location[1] + height // 2 + region[1],
        )
        is_new_best = score > best_score
        if is_new_best:
            best_score = float(score)
            best_scale = scale
            best_position = position
        candidate_roi = screen_gray[
            location[1]:location[1] + height,
            location[0]:location[0] + width,
        ]
        dark_ratio = float((candidate_roi < 80).mean())
        mean_brightness = float(candidate_roi.mean())
        template_glyph = template > 140
        candidate_glyph = candidate_roi > 140
        glyph_intersection = int((template_glyph & candidate_glyph).sum())
        glyph_total = int(template_glyph.sum() + candidate_glyph.sum())
        glyph_dice = (2.0 * glyph_intersection / glyph_total) if glyph_total else 0.0
        if is_new_best:
            best_dark_ratio = dark_ratio
            best_mean = mean_brightness
            best_glyph_dice = glyph_dice

        is_selected_row = (
            dark_ratio >= float(selected_dark_ratio)
            and mean_brightness <= float(selected_mean_max)
            and glyph_dice >= float(selected_glyph_dice)
        )
        if score >= effective_threshold and is_selected_row:
            if hasattr(self, "record_diagnostic_match"):
                self.record_diagnostic_match(
                    "delete_filter_fast",
                    template_name,
                    region_name="左",
                    threshold=threshold,
                    effective_threshold=effective_threshold,
                    hit=True,
                    score=score,
                    scale=scale,
                    position=position,
                    elapsed_ms=int((time.time() - started) * 1000),
                    extra={
                        "selected_dark_ratio": dark_ratio,
                        "selected_mean": mean_brightness,
                        "selected_glyph_dice": glyph_dice,
                    },
                )
            self.log(
                f"[删车筛选识别] {template_name} score={score:.3f} "
                f"dark={dark_ratio:.3f} mean={mean_brightness:.1f} "
                f"glyph={glyph_dice:.3f} scale={scale:.3f}",
                level="DEBUG",
            )
            return position

    if hasattr(self, "record_diagnostic_match"):
        self.record_diagnostic_match(
            "delete_filter_fast",
            template_name,
            region_name="左",
            threshold=threshold,
            effective_threshold=effective_threshold,
            hit=False,
            score=best_score,
            scale=best_scale,
            position=best_position,
            elapsed_ms=int((time.time() - started) * 1000),
            extra={
                "selected_dark_ratio": best_dark_ratio,
                "selected_mean": best_mean,
                "selected_glyph_dice": best_glyph_dice,
            },
        )
    return None


def _select_filter_tag(self, display_name, template_name, threshold):
    """Move down until the requested highlighted filter tag is visible."""
    profile = get_recognition_profile(self, "delete.filter_tag")
    max_down = max(1, int(profile["max_down"]))
    fast_skip_start = int(profile.get("fast_skip_start", 13))
    fast_skip_end = int(profile.get("fast_skip_end", 30))

    for down_count in range(max_down + 1):
        if not self.is_running:
            return False
        if self.is_paused:
            self.check_pause()

        # No current deletion filter target exists in this fixed list segment.
        # Skip costly image matching here while still sending every Down once.
        if fast_skip_start <= down_count <= fast_skip_end:
            if down_count == fast_skip_start:
                self.log(
                    f"[删车筛选] 第 {fast_skip_start}～{fast_skip_end} 项进入快速导航。",
                    level="DEBUG",
                )
            if down_count < max_down:
                press_with_pause(
                    self,
                    "down",
                    delay=float(profile.get("fast_key_delay", 0.03)),
                    after=float(profile.get("fast_interval", 0.01)),
                )
            continue

        pos = _find_filter_tag_fast(
            self,
            template_name,
            threshold,
            profile["scale_spread"],
            profile["selected_dark_ratio"],
            profile["selected_mean_max"],
            profile["selected_glyph_dice"],
        )
        if pos:
            self.log(
                f"[删车筛选] 已选中 {display_name}（向下 {down_count} 次），按 Enter 确认。"
            )
            press_with_pause(self, "enter", after=profile["settle"])
            return True

        if down_count < max_down:
            press_with_pause(self, "down", after=profile["interval"])

    self.log(
        f"[删车筛选] 连续向下 {max_down} 次仍未识别到 {display_name}。",
        level="WARN",
    )
    return False


def _open_and_apply_delete_filters(self):
    profile = get_recognition_profile(self, "delete.filter_tag")
    self.log("[删车筛选] 按 Y 打开车辆筛选。")
    press_with_pause(self, "y", after=0.5)

    self.log("[删车筛选] 按 X 重置历史筛选，确保四项目标均从未勾选状态开始。")
    press_with_pause(self, "x", after=profile["reset_settle"])

    for display_name, template_name, threshold in DELETE_FILTER_SEQUENCE:
        if not _select_filter_tag(self, display_name, template_name, threshold):
            return False

    self.log("[删车筛选] 四项条件已全部确认，按 Esc 返回车辆列表。")
    press_with_pause(self, "esc", after=0.8)
    return True


def _find_mazda_808_in_delete_list(self, threshold, scale_spread):
    """Find the distinctive Mad Mike 808 body without requiring the NEW tag."""
    region = self.regions["全界面"]
    screen_gray = _to_gray_2d(self.capture_region(region))
    source_template = _to_gray_2d(self.load_template_gray("consumablecar_Mazda.png"))
    if screen_gray is None or source_template is None:
        return None, 0.0, 1.0

    # The purchase card and deletion card use different layouts.  Keep only the
    # distinctive blue 808 body/livery, excluding NEW, rarity and class labels.
    template_h, template_w = source_template.shape[:2]
    template = source_template[
        int(template_h * 0.174):int(template_h * 0.710),
        int(template_w * 0.105):int(template_w * 0.932),
    ]

    screen_h, screen_w = screen_gray.shape[:2]
    search_left = int(screen_w * 0.20)
    search_top = int(screen_h * 0.12)
    search_bottom = int(screen_h * 0.92)
    search_gray = screen_gray[search_top:search_bottom, search_left:]

    scales = _get_delete_template_scales(self, scale_spread)
    calibrated = scales[0]

    best_score = 0.0
    best_scale = calibrated
    best_position = None
    effective_threshold = self.get_calibrated_gray_threshold(threshold)
    for scale in scales:
        scaled_template = template
        if scale != 1.0:
            scaled_template = cv2.resize(
                template,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )
        scaled_template = _to_gray_2d(scaled_template)
        height, width = scaled_template.shape[:2]
        if (
            height < 5
            or width < 5
            or height > search_gray.shape[0]
            or width > search_gray.shape[1]
        ):
            continue
        result = cv2.matchTemplate(search_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if score > best_score:
            best_score = float(score)
            best_scale = scale
            best_position = (
                region[0] + search_left + location[0] + width // 2,
                region[1] + search_top + location[1] + height // 2,
            )

    if best_score >= effective_threshold:
        return best_position, best_score, best_scale
    return None, best_score, best_scale


def _verify_mazda_808_delete_candidates(self):
    """Safety gate: require the target Mazda on consecutive frames before deletion."""
    profile = get_recognition_profile(self, "delete.vehicle_verify")
    threshold = float(profile["threshold"])
    required_hits = max(1, int(profile["consecutive_hits"]))
    deadline = time.time() + max(0.5, float(profile["timeout"]))
    consecutive_hits = 0
    best_score = 0.0
    best_scale = 1.0

    self.log("[删车验证] 正在确认筛选结果中存在 Mazda #123 Mad Mike 808 Wagon。")
    while self.is_running and time.time() < deadline:
        if self.is_paused:
            self.check_pause()
        position, score, scale = _find_mazda_808_in_delete_list(
            self,
            threshold,
            profile["scale_spread"],
        )
        if score > best_score:
            best_score = score
            best_scale = scale
        if position:
            consecutive_hits += 1
            if consecutive_hits >= required_hits:
                if hasattr(self, "record_diagnostic_match"):
                    self.record_diagnostic_match(
                        "delete_vehicle_verify",
                        "consumablecar_Mazda.png",
                        region_name="全界面",
                        threshold=threshold,
                        effective_threshold=self.get_calibrated_gray_threshold(threshold),
                        hit=True,
                        score=score,
                        scale=scale,
                        position=position,
                    )
                self.log(
                    f"[删车验证] 已连续 {required_hits} 帧确认目标 Mazda，允许进入后续删除流程。"
                )
                return True
        else:
            consecutive_hits = 0
        time.sleep(max(0.05, float(profile["interval"])))

    if hasattr(self, "record_diagnostic_match"):
        self.record_diagnostic_match(
            "delete_vehicle_verify",
            "consumablecar_Mazda.png",
            region_name="全界面",
            threshold=threshold,
            effective_threshold=self.get_calibrated_gray_threshold(threshold),
            hit=False,
            score=best_score,
            scale=best_scale,
            position=None,
        )
    self.log(
        f"[删车验证] 未确认到目标 Mazda（最高分 {best_score:.3f}），为避免误删已停止流程。",
        level="WARN",
    )
    return False


def _delete_one_mazda(self, target_count):
    """Delete one verified Mazda using the tested menu sequence."""
    profile = get_recognition_profile(self, "delete.single_action")
    next_count = int(getattr(self, "delete_counter", 0) or 0) + 1
    self.log(f"[删车执行] 开始删除第 {next_count}/{target_count} 辆 Mazda。")

    press_with_pause(self, "enter", after=float(profile["open_menu_settle"]))
    for _ in range(4):
        if not self.is_running:
            return False
        press_with_pause(
            self,
            "down",
            delay=float(profile["menu_down_delay"]),
            after=float(profile["menu_down_interval"]),
        )
    press_with_pause(self, "enter", after=float(profile["select_settle"]))
    press_with_pause(self, "down", after=float(profile["confirm_down_settle"]))
    press_with_pause(self, "enter", after=float(profile["finish_settle"]))

    if not self.is_running:
        return False
    self.delete_counter = next_count
    self.update_delete_progress(self.delete_counter, target_count)
    self.log(f"[删车执行] 第 {self.delete_counter}/{target_count} 辆删除完成。")
    return True


def _return_to_freeroam_after_delete(self):
    """Mirror CJ's no-next-step ending: two Esc presses, then return success."""
    self.log("[删车执行] 目标数量已全部完成，正在返回漫游模式。")
    if not self.is_running:
        return False
    press_with_pause(self, "esc", after=0.7)
    if not self.is_running:
        return False
    press_with_pause(self, "esc", after=0.7)
    self.log("[删车执行] 已执行返回漫游指令。")
    return True


def logic_delete_car(self, target_count):
    """Validate skillcar state and apply the four Mazda deletion filters."""
    target_count = max(1, int(target_count))
    self.delete_counter = int(getattr(self, "delete_counter", 0) or 0)
    self.update_delete_progress(self.delete_counter, target_count)
    if self.delete_counter >= target_count:
        return True
    self.log(
        f"[Delete] start target={DELETE_VEHICLE_PROFILE['vehicle_name']} count={target_count}",
        level="DEBUG",
    )
    navigation_state = _prepare_skillcar_for_race(self, stay_in_car_list=True)
    if navigation_state != "car_list":
        self.log("[流程] 未能在车辆列表确认 R917，停止删除车辆任务。", level="WARN")
        return False

    if not _open_and_apply_delete_filters(self):
        return False

    if not _verify_mazda_808_delete_candidates(self):
        return False

    first_delete_this_attempt = True
    while self.delete_counter < target_count:
        # The first vehicle was verified above.  Re-verify the refreshed list
        # before every subsequent destructive action so an exhausted/changed
        # list can never receive the deletion key sequence.
        if not first_delete_this_attempt and not _verify_mazda_808_delete_candidates(self):
            return False
        if not _delete_one_mazda(self, target_count):
            return False
        first_delete_this_attempt = False

    if not _return_to_freeroam_after_delete(self):
        return False

    self.log(
        f"[Delete] completed {self.delete_counter}/{target_count}",
        level="DEBUG",
    )
    return True
