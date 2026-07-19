"""Xbox-only race entry adapter.  The Steam flow remains untouched."""

import flow_race

from flow_common import press_many, press_with_pause, wait_image_or_log
from recognition_config import get_recognition_profile
from xbox_share_input import enter_share_code_xbox


def _navigate_to_eventlab_challenge_xbox(self, navigation_state="roam"):
    self.log("准备进入 EventLab 挑战（Xbox 输入兼容模式）。")
    if navigation_state == "car_menu":
        self.log("沿用车辆菜单：PageDown 三次进入创意中心。")
        page_count = 3
    else:
        if not self.enter_menu():
            return False
        page_count = 4

    if not press_many(self, "pagedown", page_count, delay=0.15, after=0.3):
        return False
    if not flow_race._interruptible_wait(self, 0.8):
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
    press_with_pause(self, "enter", after=1.0)

    code_text = "".join(c for c in self.entry_share.get() if c.isdigit())
    if not code_text:
        self.log("分享码为空，无法搜索挑战。", level="WARN")
        return False
    self.log(f"[XboxInput] 准备输入挑战分享码: {code_text}")
    if not enter_share_code_xbox(self, code_text, dialog_timeout=10.0):
        return False

    # The Xbox system dialog replaces the first Steam Enter.  Once it closes,
    # resume the unchanged game-side menu sequence.
    press_with_pause(self, "down", after=0.3)
    press_with_pause(self, "enter", after=1.5)
    if not flow_race._wait_for_challenge_options(self):
        return False

    self.hw_press("enter")
    self.log("已选择挑战，等待自动发车。")
    return flow_race._interruptible_wait(self, 2.0)


def logic_race_xbox(self, target_count):
    """Run the original race logic with only the Xbox navigation step replaced."""
    original_navigation = flow_race._navigate_to_eventlab_challenge
    flow_race._navigate_to_eventlab_challenge = _navigate_to_eventlab_challenge_xbox
    try:
        return flow_race.logic_race(self, target_count)
    finally:
        flow_race._navigate_to_eventlab_challenge = original_navigation
