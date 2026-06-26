import time

from flow_common import click_if_found, press_many, press_with_pause, wait_any_image_or_log, wait_image_or_log
from recognition_config import get_recognition_profile


def logic_race(self, target_count):
    if self.race_counter >= target_count:
        return True

    self.update_running_ui("循环跑图", self.race_counter, target_count)

    self.log("准备验证/进入菜单...")
    if not self.enter_menu():
        return False

    self.log("切换到创意中心...")
    if not press_many(self, "pagedown", 4, delay=0.15, after=0.3):
        return False
    time.sleep(0.8)

    profile = get_recognition_profile(self, "race.eventlab")
    pos_el = wait_image_or_log(
        self,
        "eventlab.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到 eventlab",
        click=True,
    )
    if not pos_el:
        return False

    profile = get_recognition_profile(self, "race.playevent")
    pos_yg = wait_image_or_log(
        self,
        "playenent.png",
        region=self.regions["中间"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到游玩赛事",
        click=True,
        post_delay=1.5,
    )
    if not pos_yg:
        return False

    press_with_pause(self, "backspace", after=0.8)
    press_with_pause(self, "up", after=0.4)
    press_with_pause(self, "enter")
    time.sleep(4.0)

    code_text = "".join(c for c in self.entry_share.get() if c.isdigit())
    for char in code_text:
        if not self.is_running:
            return False
        self.hw_press(char, delay=0.05)
        time.sleep(0.05)

    time.sleep(0.4)
    press_with_pause(self, "enter", after=0.8)
    press_with_pause(self, "down", after=0.3)
    press_with_pause(self, "enter")
    self.log("搜索蓝图中", level="DEBUG")
    blueprint_result = None
    blueprint_wait_deadline = time.time() + 20
    blueprint_last_wait_log = 0.0
    profile_nf = get_recognition_profile(self, "race.blueprint_not_found")
    profile_ready = get_recognition_profile(self, "race.blueprint_ready")
    while self.is_running and time.time() < blueprint_wait_deadline:
        now = time.time()
        if now - blueprint_last_wait_log >= 2.0:
            remaining = max(0.0, blueprint_wait_deadline - now)
            self.log(f"蓝图搜索结果待确认，继续等待... 剩余 {remaining:.1f}s", level="DEBUG")
            blueprint_last_wait_log = now

        if self.find_image_gray(
            "racenotfound.png",
            region=self.regions["全界面"],
            threshold=profile_nf["threshold"],
            fast_mode=profile_nf["fast_mode"],
            invert_mode=profile_nf["invert_mode"],
        ):
            return self.abort_invalid_blueprint_and_back_to_roam()

        blueprint_result = self.find_image_gray(
            "VEI.png",
            region=self.regions["下"],
            threshold=profile_ready["threshold"],
            fast_mode=profile_ready["fast_mode"],
            invert_mode=profile_ready["invert_mode"],
        )
        if blueprint_result:
            self.log("已识别到目标赛事信息")
            break

        time.sleep(0.25)

    if not blueprint_result:
        return self.abort_invalid_blueprint_and_back_to_roam()

    self.hw_press("enter")
    time.sleep(1.5)
    self.hw_press("enter")
    time.sleep(0.8)

    profile = get_recognition_profile(self, "race.skillcar_like")
    pos_target = self.find_skill_car_with_like_tag(
        region=self.regions["全界面"],
        timeout=profile["timeout"],
        interval=profile["interval"],
    )

    if not pos_target:
        self.log("未找到带 liketag 的目标车辆，重新选品牌...", level="WARN")
        self.hw_press("backspace")
        time.sleep(0.7)

        found_brand = False
        profile = get_recognition_profile(self, "race.skillcar_brand")
        for _ in range(3):
            if not self.is_running:
                return False

            pos_brand = self.wait_for_image_gray(
                "skillcarbrand.png",
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                timeout=profile["timeout"],
                interval=profile["interval"],
                fast_mode=profile["fast_mode"],
            )
            if pos_brand:
                click_if_found(self, pos_brand, post_delay=0.8)
                found_brand = True
                break

            press_with_pause(self, "up", after=0.25)

        if not found_brand:
            self.log("三次尝试未找到刷图车辆品牌。", level="WARN")
            return False

        for _ in range(20):
            if not self.is_running:
                return False

            profile = get_recognition_profile(self, "race.skillcar_like")
            pos_target = self.find_skill_car_with_like_tag(
                region=self.regions["全界面"],
                timeout=profile["timeout"],
                interval=profile["interval"],
            )
            if pos_target:
                break

            if not press_many(self, "right", 4, delay=0.08, after=0.08):
                return False
            time.sleep(0.25)

    if not pos_target:
        self.log("翻页未能找到带有 liketag 的刷图车辆！", level="WARN")
        return False

    click_if_found(self, pos_target, post_delay=0.5)
    press_with_pause(self, "enter")
    profile = get_recognition_profile(self, "race.start_ready")
    start_ready = wait_any_image_or_log(
        self,
        ["start.png", "startw.png"],
        region=self.regions["左下"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="",
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

            profile = get_recognition_profile(self, "race.start_loop")
            pos = self.wait_for_any_image_gray(
                ["start.png", "startw.png"],
                region=self.regions["左下"],
                threshold=profile["threshold"],
                timeout=profile["timeout"],
                interval=profile["interval"],
                fast_mode=profile["fast_mode"],
            )
            if pos:
                break

            press_with_pause(self, "down", after=0.25)

        if not pos:
            self.log("找不到赛事起点，退出跑图。")
            return False

        self.game_click(pos)
        time.sleep(4.0)
        self.hw_key_down("w")
        self.hw_key_down("up")

        race_start_time = time.time()
        last_like_chk = time.time()
        last_chk = 0
        finished = False
        timeout_triggered = False

        driving_keys_held = True
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
                last_like_chk = time.time()
                last_chk = time.time()
                continue

            now = time.time()

            if now - race_start_time > race_timeout:
                self.log(f"跑图超时(已超过{race_timeout}秒)！触发强制重开赛事逻辑...")
                timeout_triggered = True
                break

            if now - last_like_chk >= 3.0:
                vram_result = self.check_vramne_during_race()
                if vram_result is True:
                    self.log("VRAM恢复完成，结束当前跑图流程，交给外层重新恢复。")
                    return False
                if vram_result is False:
                    self.log("VRAM恢复失败。")
                    return False
                last_like_chk = now

            if now - last_chk >= 1.0:
                found_restart = self.find_image_gray("restart.png", region=self.regions["下"], threshold=0.75, fast_mode=True)
                if found_restart:
                    finished = True
                    break
                last_chk = now

            time.sleep(0.3)

        self.hw_key_up("w")
        self.hw_key_up("up")

        if not self.is_running:
            return False

        if timeout_triggered:
            time.sleep(0.5)
            press_with_pause(self, "esc", after=1.5)

            profile = get_recognition_profile(self, "race.restart_prompt")
            pos_restarta = self.wait_for_image_gray(
                "restarta.png",
                region=self.regions["全界面"],
                threshold=profile["threshold"],
                timeout=profile["timeout"],
                interval=profile["interval"],
                fast_mode=profile["fast_mode"],
            )
            if pos_restarta:
                self.log("找到 restarta.png，点击重开赛事...")
                click_if_found(self, pos_restarta, post_delay=1.0)
                self.hw_press("enter")
                time.sleep(4.0)
            else:
                self.log("未找到 restarta.png，尝试直接继续...")

            continue

        if not finished:
            return False

        if self.race_counter == target_count - 1:
            self.hw_press("enter")
            # 首次完成蓝图时，评价弹窗会在离开结算页后才出现。
            time.sleep(0.4)
            self.handle_author_prompt(release_drive_keys=False)
            if not self.is_running:
                return False
            time.sleep(0.5)
        else:
            self.hw_press("x")
            time.sleep(0.8)
            self.hw_press("enter")
            time.sleep(2.0)

        self.race_counter += 1
        self.update_running_ui("循环跑图", self.race_counter, target_count)

    return True


def abort_invalid_blueprint_and_back_to_roam(self):
    self.invalid_blueprint_abort = True
    if hasattr(self, "capture_diagnostic_snapshot"):
        self.capture_diagnostic_snapshot(
            "invalid_blueprint",
            region=self.regions["全界面"],
            reason="蓝图搜索后识别到 racenotfound，判定该蓝图已失效",
            level="WARN",
            meta={"share_code": "".join(c for c in self.entry_share.get() if c.isdigit())},
            dedupe_key="invalid_blueprint",
        )
    self.log("该蓝图已失效", level="WARN")
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
