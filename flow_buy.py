import time

from flow_common import click_if_found, press_with_pause, wait_image_or_log
from recognition_config import get_recognition_profile


BUY_VEHICLE_PROFILES = {
    "subaru": {
        "name": "斯巴鲁 22B",
        "brand_template": "CCbrand.png",
        "car_template": "consumablecar.png",
    },
    "mazda": {
        "name": "马自达 #123 Mad Mike 808 Wagon",
        "brand_template": "CCbrand_Mazda.png",
        "car_template": "consumablecar_Mazda.png",
    },
}


def logic_buy_car(self, target_count):
    vehicle_mode = self.get_buy_cj_vehicle_mode()
    vehicle_profile = BUY_VEHICLE_PROFILES.get(vehicle_mode, BUY_VEHICLE_PROFILES["subaru"])
    vehicle_name = vehicle_profile["name"]
    brand_template = vehicle_profile["brand_template"]
    car_template = vehicle_profile["car_template"]
    unit_price = self.get_buy_cj_vehicle_price(vehicle_mode)
    self.log(f"[BuyVehicle] 当前方案：{vehicle_name}，单价 {unit_price:,} CR")

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

    profile = get_recognition_profile(self, "buy.collectionjournal")
    pos_collectionjournal = wait_image_or_log(
        self,
        "collectionjournal.png",
        region=self.regions["左"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到收集簿",
        click=True,
        click_double=True,
        post_delay=1.0,
        transparent=True,
    )
    if not pos_collectionjournal:
        return False

    profile = get_recognition_profile(self, "buy.masterexplorer")
    pos_masterexplorer = wait_image_or_log(
        self,
        "masterexplorer.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message="未找到探索",
        click=True,
        click_double=True,
        post_delay=0.6,
    )
    if not pos_masterexplorer:
        return False

    profile = get_recognition_profile(self, "buy.carcollection")
    pos_carcollection = wait_image_or_log(
        self,
        "carcollection.png",
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
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
    profile = get_recognition_profile(self, "buy.ccbrand")
    for _ in range(5):
        if not self.is_running:
            return False

        brand_pos = self.wait_for_any_image_gray(
            [brand_template],
            region=self.regions["全界面"],
            threshold=profile["threshold"],
            timeout=profile["timeout"],
            interval=profile["interval"],
            fast_mode=profile["fast_mode"],
        )
        if brand_pos:
            break

        press_with_pause(self, "up", after=0.25)

    if not brand_pos:
        self.log(f"未找到目标品牌：{vehicle_name}")
        return False

    click_if_found(self, brand_pos, post_delay=0.8)
    press_with_pause(self, "down", after=0.4)

    profile = get_recognition_profile(self, "buy.consumablecar")
    pos_target_car = wait_image_or_log(
        self,
        car_template,
        region=self.regions["全界面"],
        threshold=profile["threshold"],
        timeout=profile["timeout"],
        interval=profile["interval"],
        fast_mode=profile["fast_mode"],
        not_found_message=f"未找到目标购买车辆：{vehicle_name}",
        click=True,
        click_double=True,
        post_delay=1.0,
    )
    if not pos_target_car:
        return False

    self.log(f"已锁定目标购买车辆：{vehicle_name}")

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
        self.log(f"[进度] 买车 {self.car_counter}/{target_count} 完成")

    for _ in range(5):
        if not self.is_running:
            return False
        press_with_pause(self, "esc", after=0.8)

    return True
