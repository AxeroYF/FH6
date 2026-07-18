import copy


DEFAULT_RECOGNITION_PROFILES = {
    "buy.collectionjournal": {"threshold": 0.70, "timeout": 30, "interval": 0.4, "fast_mode": True},
    "buy.masterexplorer": {"threshold": 0.75, "timeout": 30, "interval": 0.4, "fast_mode": True},
    "buy.carcollection": {"threshold": 0.75, "timeout": 30, "interval": 0.3, "fast_mode": True},
    "buy.ccbrand": {"threshold": 0.75, "timeout": 0.8, "interval": 0.2, "fast_mode": True},
    "buy.consumablecar": {"threshold": 0.82, "timeout": 8, "interval": 0.3, "fast_mode": False},
    "race.eventlab": {"threshold": 0.70, "timeout": 5, "interval": 0.25, "fast_mode": True},
    "race.change_car": {"threshold": 0.75, "timeout": 5, "interval": 0.25, "fast_mode": True},
    "race.join_challenge": {"threshold": 0.68, "timeout": 20, "interval": 0.30, "fast_mode": False},
    "race.challenge_options": {
        "threshold": 0.72,
        "timeout": 20,
        "interval": 0.35,
        "fast_mode": False,
        "crop_box": [0.175, 0.905, 0.265, 0.965],
    },
    "race.challenge_success": {
        "threshold": 0.68,
        "decision_margin": 0.10,
        "interval": 0.60,
        "fast_mode": False,
        "crop_box": [0.070, 0.908, 0.112, 0.950],
    },
    "race.challenge_failed": {
        "threshold": 0.68,
        "decision_margin": 0.10,
        "interval": 0.60,
        "fast_mode": False,
        "crop_box": [0.070, 0.908, 0.112, 0.950],
    },
    "race.challenge_rating": {
        "threshold": 0.72,
        "timeout": 6,
        "interval": 0.25,
        "fast_mode": False,
        "crop_box": [0.325, 0.355, 0.675, 0.430],
    },
    "race.playevent": {"threshold": 0.75, "timeout": 40, "interval": 0.3, "fast_mode": True},
    "race.blueprint_not_found": {"threshold": 0.70, "fast_mode": False, "invert_mode": True},
    "race.blueprint_ready": {"threshold": 0.70, "fast_mode": False, "invert_mode": True},
    "race.skillcar_like": {"timeout": 1.0, "interval": 0.25},
    "race.skillcar_brand": {"threshold": 0.80, "timeout": 0.8, "interval": 0.2, "fast_mode": True},
    "race.start_ready": {"threshold": 0.75, "timeout": 4.0, "interval": 0.2, "fast_mode": True},
    "race.start_loop": {"threshold": 0.75, "timeout": 0.7, "interval": 0.2, "fast_mode": True},
    "race.restart_prompt": {"threshold": 0.70, "timeout": 4.0, "interval": 0.3, "fast_mode": True},
    "race.author_prompt": {"threshold": 0.68, "timeout": 2.0, "interval": 0.15, "fast_mode": True, "invert_mode": True},
    "delete.filter_tag": {
        "threshold": 0.68,
        "max_down": 40,
        "interval": 0.08,
        "fast_skip_start": 13,
        "fast_skip_end": 30,
        "fast_key_delay": 0.03,
        "fast_interval": 0.01,
        "settle": 0.22,
        "reset_settle": 0.45,
        "scale_spread": 0.012,
        "selected_dark_ratio": 0.60,
        "selected_mean_max": 100.0,
        "selected_glyph_dice": 0.65,
    },
    "delete.vehicle_verify": {
        "threshold": 0.80,
        "timeout": 4.0,
        "interval": 0.25,
        "consecutive_hits": 2,
        "scale_spread": 0.025,
    },
    "delete.single_action": {
        "open_menu_settle": 0.55,
        "menu_down_delay": 0.08,
        "menu_down_interval": 0.10,
        "select_settle": 0.45,
        "confirm_down_settle": 0.20,
        "finish_settle": 0.80,
    },
    "cj.designpaint": {"threshold": 0.62, "timeout": 10, "interval": 0.25, "fast_mode": False},
    "cj.choosecar_quick": {"threshold": 0.62, "timeout": 2, "interval": 0.25, "fast_mode": False},
    "cj.choosecar_retry": {"threshold": 0.62, "timeout": 10, "interval": 0.25, "fast_mode": False},
    "cj.ccbrand": {"threshold": 0.75, "timeout": 0.8, "interval": 0.2, "fast_mode": True},
    "cj.buyandsell_landing": {"threshold": 0.68, "timeout": 15, "interval": 0.3, "fast_mode": False, "invert_mode": True},
    "cj.rc": {"threshold": 0.70, "timeout": 0.5, "interval": 0.1, "fast_mode": True},
    "cj.spraycar": {"threshold": 0.68, "timeout": 4.0, "interval": 0.2, "fast_mode": False, "invert_mode": True},
    "cj.vehicle_menu": {"threshold": 0.68, "timeout": 4.0, "interval": 0.15, "fast_mode": False, "invert_mode": True},
    "cj.vehicle_menu_retry": {"threshold": 0.68, "timeout": 1.8, "interval": 0.15, "fast_mode": False, "invert_mode": True},
    "cj.vehicle_menu_stable": {"threshold": 0.68, "fast_mode": False, "invert_mode": True},
    "cj.uat_menu": {"threshold": 0.62, "timeout": 1.2, "interval": 0.15, "fast_mode": False},
    "cj.cls": {"threshold": 0.68, "timeout": 8, "interval": 0.25, "fast_mode": False},
    "cj.exp": {"threshold": 0.75, "timeout": 1.2, "interval": 0.3, "fast_mode": True},
    "cj.spne": {"threshold": 0.66, "timeout": 0.35, "interval": 0.08, "fast_mode": True, "invert_mode": True},
    "matcher.skillcar_like_combo": {
        "main_threshold": 0.75,
        "like_threshold": 0.68,
        "detail_box": [0.70, 0.82, 1.00, 1.00],
        "detail_threshold": 0.82,
        "final_threshold": 0.72,
        "fast_mode": True,
    },
    "matcher.skillcar_switch_rc": {"threshold": 0.70, "timeout": 2.0, "interval": 0.2, "fast_mode": True},
    "matcher.skillcar_brand_entry": {"threshold": 0.76, "timeout": 0.8, "interval": 0.2, "fast_mode": True},
    "matcher.uat_menu": {"threshold": 0.62, "fast_mode": False},
    "matcher.buy_used_gray": {"threshold": 0.68, "interval": 0.25, "fast_mode": False},
    "matcher.buy_used_full": {"threshold": 0.65, "interval": 0.25, "fast_mode": False},
    "matcher.buy_used_fast": {"threshold": 0.70, "interval": 0.25, "fast_mode": True},
}


def get_recognition_profile(bot, key, **overrides):
    profile = copy.deepcopy(DEFAULT_RECOGNITION_PROFILES.get(key, {}))
    user_profiles = getattr(bot, "config", {}).get("recognition_profiles", {}) or {}
    user_profile = user_profiles.get(key, {})
    if isinstance(user_profile, dict):
        profile.update(user_profile)
    if overrides:
        profile.update({k: v for k, v in overrides.items() if v is not None})
    return profile
