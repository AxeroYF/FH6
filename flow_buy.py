import time

from flow_common import click_if_found, press_with_pause, wait_image_or_log


def logic_buy_car(self, target_count):
    total_limit = getattr(self, "total_car_limit", None)
    total_bought = int(getattr(self, "total_car_bought", 0) or 0)
    if total_limit is not None:
        remaining_total = max(0, int(total_limit) - total_bought)
        if remaining_total <= 0:
            self.stop_after_cj_due_buy_limit = True
            self.log("[BuyLimit] CR exhausted. Skip buy and go to CJ.")
            return True
        if target_count > remaining_total:
            self.stop_after_cj_due_buy_limit = True
            self.log(f"[BuyLimit] Only {remaining_total} buys left. Finish buy then go to CJ.")
            target_count = remaining_total

    if self.car_counter >= target_count:
        return True

    self.update_running_ui("批量买车", self.car_counter, target_count)

    self.log("准备验证/进入菜单...")
    if not self.enter_menu():
        return False

    pos_collectionjournal = wait_image_or_log(
        self,
        "collectionjournal.png",
        region=self.regions["左"],
        threshold=0.7,
        timeout=30,
        interval=0.4,
        fast_mode=True,
        not_found_message="未找到收集簿",
        click=True,
        click_double=True,
        post_delay=1.0,
        transparent=True,
    )
    if not pos_collectionjournal:
        return False

    pos_masterexplorer = wait_image_or_log(
        self,
        "masterexplorer.png",
        region=self.regions["全界面"],
        threshold=0.75,
        timeout=30,
        interval=0.4,
        fast_mode=True,
        not_found_message="未找到探索",
        click=True,
        click_double=True,
        post_delay=0.6,
    )
    if not pos_masterexplorer:
        return False

    pos_carcollection = wait_image_or_log(
        self,
        "carcollection.png",
        region=self.regions["全界面"],
        threshold=0.75,
        timeout=30,
        interval=0.3,
        fast_mode=True,
        not_found_message="未找到车辆收集",
        click=True,
        click_double=True,
        post_delay=1.0,
        transparent=True,
    )
    if not pos_carcollection:
        return False

    press_with_pause(self, "backspace", after=0.5)

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
            fast_mode=True,
        )
        if brand_pos:
            break

        press_with_pause(self, "up", after=0.25)

    if not brand_pos:
        self.log("未找到品牌")
        return False

    click_if_found(self, brand_pos, post_delay=0.8)
    press_with_pause(self, "down", after=0.4)

    pos_22b = wait_image_or_log(
        self,
        "consumablecar.png",
        region=self.regions["全界面"],
        threshold=0.90,
        timeout=8,
        interval=0.3,
        fast_mode=False,
        not_found_message="未找到消耗品车辆",
        click=True,
        click_double=True,
        post_delay=1.0,
    )
    if not pos_22b:
        return False

    while self.car_counter < target_count:
        if not self.is_running:
            return False

        press_with_pause(self, "space", after=0.6)
        self.move_to_game_coord(5, 5)
        press_with_pause(self, "down", after=0.2)
        self.move_to_game_coord(5, 5)
        press_with_pause(self, "enter", after=0.6)
        self.move_to_game_coord(5, 5)
        press_with_pause(self, "enter", after=0.6)
        self.move_to_game_coord(5, 5)
        press_with_pause(self, "enter", after=0.7)

        self.car_counter += 1
        self.total_car_bought = int(getattr(self, "total_car_bought", 0) or 0) + 1
        self.update_running_ui("批量买车", self.car_counter, target_count)

    for _ in range(5):
        if not self.is_running:
            return False
        press_with_pause(self, "esc", after=0.8)

    return True
