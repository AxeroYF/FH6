import time

from flow_common import (
    click_if_found,
    press_many,
    press_with_pause,
    wait_image_or_log,
)
from recognition_config import get_recognition_profile


def _interruptible_wait(self, seconds):
    deadline = time.time() + max(0.0, float(seconds))
    while self.is_running and time.time() < deadline:
        if self.is_paused:
            self.check_pause()
        time.sleep(min(0.2, max(0.01, deadline - time.time())))
    return self.is_running


def _find_challenge_reference(self, profile_key, reference_name, region=None):
    profile = get_recognition_profile(self, profile_key)
    return self.find_reference_crop_gray(
        reference_name,
        crop_box=profile["crop_box"],
        region=region or self.regions["左下"],
        threshold=profile["threshold"],
        fast_mode=profile["fast_mode"],
    )


def _wait_for_challenge_options(self):
    profile = get_recognition_profile(self, "race.challenge_options")
    profile_nf = get_recognition_profile(self, "race.blueprint_not_found")
    deadline = time.time() + profile["timeout"]
    last_wait_log = 0.0

    while self.is_running and time.time() < deadline:
        now = time.time()
        if now - last_wait_log >= 2.0:
            self.log(f"挑战搜索结果待确认，继续等待... 剩余 {max(0.0, deadline - now):.1f}s", level="DEBUG")
            last_wait_log = now

        if self.find_image_gray(
            "racenotfound.png",
            region=self.regions["全界面"],
            threshold=profile_nf["threshold"],
            fast_mode=profile_nf["fast_mode"],
            invert_mode=profile_nf["invert_mode"],
        ):
            return self.abort_invalid_blueprint_and_back_to_roam()

        if _find_challenge_reference(self, "race.challenge_options", "challenge_options_full.png"):
            self.log("已识别到【Y 挑战选项】，分享码搜索成功。")
            return True

        time.sleep(profile["interval"])

    if self.is_running:
        self.log("等待挑战选项超时。", level="WARN")
    return False


def _score_challenge_result_once(self):
    success_profile = get_recognition_profile(self, "race.challenge_success")
    failed_profile = get_recognition_profile(self, "race.challenge_failed")
    screen_bgr = self.capture_region(self.regions["全界面"])
    success_score = self.score_fixed_reference_crop_gray(
        "challenge_success_full.png",
        success_profile["crop_box"],
        screen_bgr=screen_bgr,
    )
    failed_score = self.score_fixed_reference_crop_gray(
        "challenge_failed_full.png",
        failed_profile["crop_box"],
        screen_bgr=screen_bgr,
    )
    margin = max(
        float(success_profile.get("decision_margin", 0.10)),
        float(failed_profile.get("decision_margin", 0.10)),
    )

    if (
        success_score >= float(success_profile["threshold"])
        and success_score - failed_score >= margin
    ):
        return "success", success_score, failed_score

    if (
        failed_score >= float(failed_profile["threshold"])
        and failed_score - success_score >= margin
    ):
        return "failed", success_score, failed_score
    return None, success_score, failed_score


def _find_challenge_result(self):
    candidate, success_score, failed_score = _score_challenge_result_once(self)
    if candidate == "success":
        self.log(
            f"[ChallengeResultScore] success={success_score:.3f} "
            f"failed={failed_score:.3f} -> success"
        )
        return "success"

    if candidate == "failed":
        self.log(
            f"[ChallengeResultScore] success={success_score:.3f} "
            f"failed={failed_score:.3f} -> failed candidate"
        )
        # 失败会触发 Enter，误判的破坏性高于漏判。等待一帧后再次优先确认成功，
        # 只有连续两次命中失败专属的“重试”文字才返回 failed。
        if not _interruptible_wait(self, 0.25):
            return None
        confirmed, confirm_success, confirm_failed = _score_challenge_result_once(self)
        if confirmed == "success":
            self.log("失败候选复核为挑战完成，已阻止错误按 Enter。", level="WARN")
            return "success"
        if confirmed == "failed":
            self.log(
                f"[ChallengeResultScore] confirm success={confirm_success:.3f} "
                f"failed={confirm_failed:.3f} -> failed"
            )
            return "failed"
        self.log("挑战失败候选未通过二次确认，继续等待结算稳定。", level="DEBUG")
    return None


def _confirm_challenge_action(self, state, key):
    self.hw_press(key)
    if not _interruptible_wait(self, 1.0):
        return False
    if _find_challenge_result(self) == state:
        self.log(f"结算按钮仍可见，重按 {key.upper()} 确认。", level="WARN")
        self.hw_press(key)
        return _interruptible_wait(self, 0.8)
    return True


def _handle_optional_challenge_rating(self, continuation_text="继续重试"):
    """Handle the optional rating popup shown after leaving a failed challenge."""
    profile = get_recognition_profile(self, "race.challenge_rating")
    deadline = time.time() + profile["timeout"]

    while self.is_running and time.time() < deadline:
        if _find_challenge_reference(
            self,
            "race.challenge_rating",
            "challenge_rating_full.png",
            region=self.regions["中间"],
        ):
            self.log(
                f"识别到【为挑战评分？】，按 Down 选择点踩，再按 Enter 确认后{continuation_text}。"
            )
            self.hw_press("down")
            if not _interruptible_wait(self, 0.2):
                return True
            self.hw_press("enter")
            if not _interruptible_wait(self, 0.8):
                return True

            if _find_challenge_reference(
                self,
                "race.challenge_rating",
                "challenge_rating_full.png",
                region=self.regions["中间"],
            ):
                self.log("挑战评分弹窗仍可见，保持点踩选项并重按 Enter 确认。", level="WARN")
                self.hw_press("enter")
                _interruptible_wait(self, 0.8)
            return True

        time.sleep(profile["interval"])

    self.log("失败后未出现挑战评分弹窗，直接继续重试。", level="DEBUG")
    return False


def _prepare_skillcar_for_race(self):
    self.log("新版挑战流程：先确认当前驾驶车辆。")
    if not self.enter_menu():
        return False

    press_with_pause(self, "pagedown", after=0.8)
    profile = get_recognition_profile(self, "race.change_car")
    pos_change = wait_image_or_log(
        self,
        "changecar.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到更换车辆",
        click=True,
        post_delay=1.0,
    )
    if not pos_change:
        return False

    profile = get_recognition_profile(self, "race.skillcar_like")
    pos_target = self.find_skill_car_with_like_tag(
        region=self.regions["全界面"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_scan=True,
    )

    if not pos_target:
        self.log("当前页未找到 R917 刷图车辆，重新选择斯巴鲁品牌。", level="WARN")
        press_with_pause(self, "backspace", after=0.8)
        brand_profile = get_recognition_profile(self, "race.skillcar_brand")
        pos_brand = None
        for _ in range(3):
            if not self.is_running:
                return False
            pos_brand = self.wait_for_image_gray(
                "skillcarbrand.png",
                region=self.regions["全界面"],
                threshold=brand_profile["threshold"],
                timeout=brand_profile["timeout"],
                interval=brand_profile["interval"],
                fast_mode=brand_profile["fast_mode"],
            )
            if pos_brand:
                click_if_found(self, pos_brand, post_delay=1.0)
                break
            press_with_pause(self, "up", after=0.25)
        if not pos_brand:
            self.log("未找到斯巴鲁品牌。", level="WARN")
            return False

        for _ in range(20):
            if not self.is_running:
                return False
            pos_target = self.find_skill_car_with_like_tag(
                region=self.regions["全界面"],
                timeout=0.5,
                interval=0.1,
                fast_scan=True,
            )
            if pos_target:
                break
            if not press_many(self, "right", 4, delay=0.08, after=0.12):
                return False

    if not pos_target:
        self.log("翻页后仍未找到 R917 刷图车辆。", level="WARN")
        return False

    full_w = self.regions["全界面"][2]
    full_h = self.regions["全界面"][3]
    driving_tag = self.find_image(
        "drivingtag.png",
        region=(pos_target[0], pos_target[1], int(full_w * 0.20), int(full_h * 0.20)),
        threshold=0.75,
        fast_mode=True,
    )
    if driving_tag:
        self.log("R917 已是当前驾驶车辆，保留菜单上下文直接前往 EventLab。")
        press_with_pause(self, "esc", after=0.7)
        return "car_menu"

    click_if_found(self, pos_target, post_delay=0.5)
    press_with_pause(self, "enter", after=1.0)
    press_with_pause(self, "enter", after=4.0)
    self.log("已切换到 R917 刷图车辆。")
    if not _interruptible_wait(self, 1.0):
        return False
    return "roam"


def _navigate_to_eventlab_challenge(self, navigation_state="roam"):
    self.log("准备进入 EventLab 挑战。")
    if navigation_state == "car_menu":
        self.log("沿用车辆菜单：PageDown 三次进入创意中心。")
        page_count = 3
    else:
        if not self.enter_menu():
            return False
        page_count = 4

    if not press_many(self, "pagedown", page_count, delay=0.15, after=0.3):
        return False
    if not _interruptible_wait(self, 0.8):
        return False

    profile = get_recognition_profile(self, "race.eventlab")
    pos_eventlab = wait_image_or_log(
        self,
        "eventlab.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到 EventLab",
        click=True,
        post_delay=2.0,
    )
    if not pos_eventlab:
        return False

    profile = get_recognition_profile(self, "race.join_challenge")
    pos_join = wait_image_or_log(
        self,
        "joinchallenge.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到参加挑战",
        click=True,
        post_delay=2.0,
    )
    if not pos_join:
        return False

    press_with_pause(self, "backspace", after=0.8)
    press_with_pause(self, "up", after=0.4)
    press_with_pause(self, "enter", after=4.0)

    code_text = "".join(c for c in self.entry_share.get() if c.isdigit())
    if not code_text:
        self.log("分享码为空，无法搜索挑战。", level="WARN")
        return False
    self.log(f"输入挑战分享码: {code_text}")
    for char in code_text:
        if not self.is_running:
            return False
        self.hw_press(char, delay=0.08)
        time.sleep(0.05)

    press_with_pause(self, "enter", after=0.8)
    press_with_pause(self, "down", after=0.3)
    press_with_pause(self, "enter", after=1.5)
    if not _wait_for_challenge_options(self):
        return False

    self.hw_press("enter")
    self.log("已选择挑战，等待自动发车。")
    return _interruptible_wait(self, 2.0)


def logic_race(self, target_count):
    if self.race_counter >= target_count:
        return True
    self.update_running_ui("循环跑图", self.race_counter, target_count)

    navigation_state = _prepare_skillcar_for_race(self)
    if not navigation_state:
        return False
    if not _navigate_to_eventlab_challenge(self, navigation_state):
        return False
    self.log("新版挑战入口完成，开始循环跑图。")

    while self.race_counter < target_count:
        if not self.is_running:
            return False
        is_last = self.race_counter == target_count - 1
        try:
            load_seconds = max(5, int(self.config.get("challenge_load_seconds", 15)))
        except Exception:
            load_seconds = 15
        self.log(f"跑图 {self.race_counter + 1}/{target_count}{'（末轮）' if is_last else ''}: 等待自动发车 {load_seconds}s...")
        if not _interruptible_wait(self, load_seconds):
            return False

        self.hw_key_down("w")
        self.hw_key_down("up")
        driving_keys_held = True
        race_start_time = time.time()
        last_health_check = race_start_time
        last_result_check = 0.0
        result_state = None
        timeout_triggered = False
        try:
            race_timeout = max(60, int(self.config.get("race_timeout", 300)))
        except Exception:
            race_timeout = 300

        while self.is_running:
            if self.is_paused:
                if driving_keys_held:
                    self.hw_key_up("w")
                    self.hw_key_up("up")
                    driving_keys_held = False
                self.check_pause()
                if self.is_running:
                    self.hw_key_down("w")
                    self.hw_key_down("up")
                    driving_keys_held = True
                race_start_time = time.time()
                last_health_check = race_start_time
                last_result_check = 0.0
                continue

            now = time.time()
            if now - race_start_time > race_timeout:
                self.log(f"跑图超时（超过 {race_timeout}s），触发重开恢复。", level="WARN")
                timeout_triggered = True
                break
            if now - last_health_check >= 3.0:
                vram_result = self.check_vramne_during_race()
                if vram_result is True or vram_result is False:
                    return False
                last_health_check = now
            if now - race_start_time >= 8.0 and now - last_result_check >= 0.6:
                result_state = _find_challenge_result(self)
                last_result_check = now
                if result_state:
                    break
            time.sleep(0.2)

        self.hw_key_up("w")
        self.hw_key_up("up")
        if not self.is_running:
            return False

        if timeout_triggered:
            press_with_pause(self, "esc", after=1.5)
            profile = get_recognition_profile(self, "race.restart_prompt")
            pos_restart = self.wait_for_image_gray(
                "restarta.png",
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                timeout=profile["timeout"],
                interval=profile["interval"],
                fast_mode=profile["fast_mode"],
            )
            if pos_restart:
                click_if_found(self, pos_restart, post_delay=1.0)
                press_with_pause(self, "enter", after=4.0)
                continue
            self.log("超时后未找到重开赛事按钮，交给全局恢复处理。", level="WARN")
            return False

        if result_state == "failed":
            self.race_counter += 1
            self.update_running_ui("循环跑图", self.race_counter, target_count)
            if is_last:
                self.log("最后一轮识别到挑战失败，本轮计数并按 ESC 退出循环。", level="WARN")
                if not _confirm_challenge_action(self, "failed", "esc"):
                    return False
                _handle_optional_challenge_rating(self, continuation_text="退出循环")
                if not self.is_running:
                    return False
                continue

            self.log("识别到挑战失败，本轮计数并按 Enter 进入下一轮。", level="WARN")
            if not _confirm_challenge_action(self, "failed", "enter"):
                return False
            _handle_optional_challenge_rating(self)
            if not self.is_running:
                return False
            continue
        if result_state != "success":
            return False

        action_key = "enter" if is_last else "esc"
        self.log(f"识别到挑战完成，按 {action_key.upper()} {'继续退出' if is_last else '重试'}。")
        if not _confirm_challenge_action(self, "success", action_key):
            return False
        self.race_counter += 1
        self.update_running_ui("循环跑图", self.race_counter, target_count)
        if is_last:
            self.handle_author_prompt(release_drive_keys=False)
            if not self.is_running:
                return False
    return True


def abort_invalid_blueprint_and_back_to_roam(self):
    self.invalid_blueprint_abort = True
    if hasattr(self, "capture_diagnostic_snapshot"):
        self.capture_diagnostic_snapshot(
            "invalid_blueprint",
            region=self.regions["全界面"],
            reason="挑战分享码搜索后识别到 racenotfound",
            level="WARN",
            meta={"share_code": "".join(c for c in self.entry_share.get() if c.isdigit())},
            dedupe_key="invalid_blueprint",
        )
    self.log("该挑战分享码已失效。", level="WARN")
    for _ in range(3):
        if not self.is_running:
            return False
        press_with_pause(self, "esc", after=0.35)
    return False


def handle_author_prompt(self, release_drive_keys=False):
    profile = get_recognition_profile(self, "race.author_prompt")
    self.log(f"正在检测赛事评价弹窗（最多 {profile['timeout']:.1f}s）...", level="DEBUG")
    pos_author = self.wait_for_any_image_gray(
        ["likeauthor.png", "dislikeauthor.png"],
        region=self.regions["中间"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        invert_mode=profile["invert_mode"],
    )
    if not pos_author:
        self.log("未出现赛事评价弹窗，继续后续流程。", level="DEBUG")
        return False
    if release_drive_keys:
        self.hw_key_up("w")
        self.hw_key_up("up")
    self.log("已识别赛事评价弹窗，执行点赞确认。")
    for _ in range(2):
        if not self.is_running:
            return True
        press_with_pause(self, "enter", after=0.35)
    time.sleep(0.8)
    return True
