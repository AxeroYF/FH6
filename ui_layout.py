import customtkinter as ctk


def setup_ui(bot):
    ctk.set_appearance_mode("Dark")
    bot.configure(fg_color="#0B0B0C")

    colors = {
        "bg": "#0D1117",
        "panel": "#111112",
        "panel_2": "#21262D",
        "panel_3": "#272E38",
        "line": "#30363D",
        "text": "#F0F3F6",
        "muted": "#A7B0BC",
        "muted_2": "#7D8590",
        "blue": "#0A84FF",
        "blue_hover": "#006EDB",
        "green": "#30D158",
        "green_hover": "#27B84D",
        "purple": "#BF5AF2",
        "purple_hover": "#A84DDD",
        "yellow": "#FFD60A",
        "red": "#FF453A",
        "red_hover": "#D9362E",
        "button": "#2C2C2E",
        "button_hover": "#3A3A3C",
    }
    bot.ui_colors = colors

    ui_font = "Microsoft YaHei UI"
    font_title = ctk.CTkFont(family=ui_font, size=18, weight="bold")
    font_section = ctk.CTkFont(family=ui_font, size=15, weight="bold")
    font_body = ctk.CTkFont(family=ui_font, size=13)
    font_small = ctk.CTkFont(family=ui_font, size=12)

    def card(parent, **kwargs):
        opts = {
            "fg_color": colors["panel"],
            "corner_radius": 8,
            "border_width": 1,
            "border_color": colors["line"],
        }
        opts.update(kwargs)
        return ctk.CTkFrame(parent, **opts)

    def label(parent, text, *, color=None, font=None, **kwargs):
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=color or colors["text"],
            font=font or font_body,
            **kwargs,
        )

    def entry(parent, width=76, height=32, **kwargs):
        widget = ctk.CTkEntry(
            parent,
            width=width,
            height=height,
            corner_radius=8,
            fg_color=colors["panel_2"],
            border_color=colors["line"],
            text_color=colors["text"],
            placeholder_text_color=colors["muted_2"],
            font=font_body,
            justify=kwargs.pop("justify", "center"),
            **kwargs,
        )
        return widget

    def button(parent, text, command, *, color=None, hover=None, width=96, height=34, text_color="#FFFFFF"):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=8,
            fg_color=color or colors["button"],
            hover_color=hover or colors["button_hover"],
            text_color=text_color,
            font=ctk.CTkFont(family=ui_font, size=13, weight="bold"),
        )

    bot.var_chk1 = ctk.BooleanVar(value=bot.config["chk_1"])
    bot.var_chk2 = ctk.BooleanVar(value=bot.config["chk_2"])
    bot.var_chk3 = ctk.BooleanVar(value=bot.config["chk_3"])
    bot.var_race_to_delete = ctk.BooleanVar(value=bot.config.get("route_race_delete", False))
    bot.var_delete_to_race = ctk.BooleanVar(value=bot.config.get("route_delete_race", False))
    bot.var_ai_assist = ctk.BooleanVar(value=bot.config.get("ai_assist", False))
    bot.var_smart_page = ctk.BooleanVar(value=bot.config.get("smart_page", False))
    bot.var_ai_only = ctk.BooleanVar(value=bot.config.get("ai_only", False))
    bot.var_ai_auto_capture = ctk.BooleanVar(value=bot.config.get("ai_auto_capture", False))
    bot.var_diagnostic_mode = ctk.BooleanVar(value=bot.config.get("diagnostic_mode", False))
    bot.var_background_mouse = ctk.BooleanVar(value=bot.config.get("background_mouse_enabled", True))
    bot.var_compact_on_run = ctk.BooleanVar(value=bot.config.get("compact_on_run", False))
    configured_buy_cj_vehicle = str(bot.config.get("buy_cj_vehicle", "subaru")).lower()
    buy_cj_vehicle_label = "马自达" if configured_buy_cj_vehicle == "mazda" else "斯巴鲁"
    configured_prices = bot.config.get("buy_cj_vehicle_prices", {})
    default_vehicle_prices = {"subaru": 330000, "mazda": 95000}
    selected_vehicle_price = int(configured_prices.get(configured_buy_cj_vehicle, default_vehicle_prices.get(configured_buy_cj_vehicle, 330000))) if isinstance(configured_prices, dict) else default_vehicle_prices.get(configured_buy_cj_vehicle, 330000)
    bot.var_buy_cj_vehicle = ctk.StringVar(value=buy_cj_vehicle_label)
    bot.var_auto_restart = ctk.BooleanVar(value=False)

    bot.main_container = ctk.CTkFrame(bot, fg_color="transparent")
    bot.main_container.pack(fill="both", expand=True, padx=16, pady=14)

    bot.config_frame = ctk.CTkFrame(bot.main_container, fg_color="transparent", height=348)
    bot.config_frame.pack(fill="x")
    bot.config_frame.grid_propagate(False)
    bot.config_frame.grid_rowconfigure(0, minsize=270, weight=0)
    bot.config_frame.grid_rowconfigure(1, minsize=68, weight=0)
    bot.config_frame.grid_columnconfigure(0, weight=2, minsize=215)
    bot.config_frame.grid_columnconfigure(1, weight=2, minsize=200)
    bot.config_frame.grid_columnconfigure(2, weight=4, minsize=424)
    bot.config_frame.grid_columnconfigure(3, weight=2, minsize=185)

    top_card_height = 270

    def create_task_card(parent, col, title, subtitle, btn_text, btn_cmd, btn_color, btn_hover, count_value):
        box = card(parent, height=top_card_height)
        box.grid(row=0, column=col, sticky="nsew", padx=(0, 10 if col < 4 else 0))
        box.grid_propagate(False)
        box.grid_columnconfigure(0, weight=1)

        label(box, title, color=btn_color, font=font_title).grid(row=0, column=0, pady=(14, 0))
        label(box, subtitle, color=colors["muted"], font=font_small).grid(row=1, column=0, pady=(0, 8))

        btn = button(box, btn_text, btn_cmd, color=btn_color, hover=btn_hover, width=118, height=36)
        btn.grid(row=2, column=0, pady=(0, 10))

        fields = ctk.CTkFrame(box, fg_color="transparent")
        fields.grid(row=3, column=0, pady=(0, 8))
        label(fields, "次数", color=colors["muted"], font=font_small).grid(row=0, column=0, sticky="w", padx=(0, 8))
        count_entry = entry(fields, width=82, height=30)
        count_entry.insert(0, str(count_value))
        count_entry.grid(row=0, column=1, sticky="w")

        progress = label(box, f"执行: 0 / {count_value}", color=colors["muted"], font=font_small)
        progress.grid(row=4, column=0, pady=(2, 0))
        return box, btn, count_entry, progress

    box_race, bot.btn_race, bot.entry_race, bot.lbl_race = create_task_card(
        bot.config_frame,
        0,
        "1. 循环跑图",
        "蓝图代码与赛事循环",
        "开始",
        lambda: bot.start_pipeline("race"),
        colors["blue"],
        colors["blue_hover"],
        bot.config.get("race_count", 99),
    )
    bot.entry_share = entry(box_race, width=190, height=32, placeholder_text="蓝图数字代码")
    bot.entry_share.insert(0, bot.config.get("share_code", "890169683"))
    bot.entry_share.place(relx=0.5, y=250, anchor="s")
    box_race.grid_rowconfigure(6, minsize=18)

    box_car, bot.btn_car, bot.entry_car, bot.lbl_car = create_task_card(
        bot.config_frame,
        1,
        "2. 批量买车",
        "收藏簿车辆购买",
        "开始",
        lambda: bot.start_pipeline("buy"),
        colors["green"],
        colors["green_hover"],
        bot.config.get("buy_count", 30),
    )
    bot.car_limit_row = ctk.CTkFrame(box_car, fg_color="transparent")
    bot.car_limit_row.place(relx=0.5, y=250, anchor="s")
    label(bot.car_limit_row, "CR", color=colors["muted"], font=font_small).grid(row=0, column=0, sticky="w", padx=(0, 8))
    bot.entry_cr_amount = entry(bot.car_limit_row, width=124, height=30, placeholder_text="输入CR数量")
    bot.entry_cr_amount.insert(0, str(bot.config.get("cr_amount", 0) or ""))
    bot.entry_cr_amount.grid(row=0, column=1, sticky="w")

    box_cj, bot.btn_cj, bot.entry_cj, bot.lbl_cj = create_task_card(
        bot.config_frame,
        2,
        "3. 超级抽奖",
        "技能点与抽奖流程",
        "开始",
        lambda: bot.start_pipeline("cj"),
        colors["purple"],
        colors["purple_hover"],
        bot.config.get("cj_count", 30),
    )
    bot.box_cj = box_cj

    box_cj.grid_columnconfigure(0, weight=1, minsize=236)
    box_cj.grid_columnconfigure(1, weight=0, minsize=188)

    bot.assist_row = ctk.CTkFrame(box_cj, fg_color="transparent")
    assist_row = bot.assist_row
    assist_row.place(x=14, y=250, anchor="sw")
    bot.sw_ai_assist = ctk.CTkSwitch(
        assist_row,
        text="AI辅助",
        variable=bot.var_ai_assist,
        command=bot.on_ai_assist_changed,
        progress_color=colors["purple"],
        font=font_small,
    )
    bot.sw_ai_assist.pack(side="left", padx=(0, 6))
    bot.sw_smart_page = ctk.CTkSwitch(
        assist_row,
        text="智能页码",
        variable=bot.var_smart_page,
        command=bot.on_smart_page_changed,
        progress_color=colors["purple"],
        font=font_small,
    )
    bot.sw_smart_page.pack(side="left", padx=(0, 6))
    bot.sw_ai_only = ctk.CTkSwitch(
        assist_row,
        text="纯AI",
        variable=bot.var_ai_only,
        command=bot.on_ai_only_changed,
        progress_color=colors["purple"],
        font=font_small,
    )
    bot.sw_ai_only.pack(side="left", padx=(0, 6))
    bot.sw_ai_auto_capture = ctk.CTkSwitch(
        assist_row,
        text="自动截图",
        variable=bot.var_ai_auto_capture,
        command=bot.on_ai_auto_capture_changed,
        progress_color=colors["purple"],
        font=font_small,
    )
    bot.sw_ai_auto_capture.pack(side="left")

    skill_area = ctk.CTkFrame(box_cj, fg_color="transparent", width=176, height=190)
    skill_area.place(relx=1.0, x=-10, y=18, anchor="ne")
    skill_area.grid_propagate(False)
    skill_area.grid_columnconfigure(0, weight=1)
    skill_area.grid_rowconfigure(0, weight=0)
    skill_area.grid_rowconfigure(1, weight=0)

    bot.grid_frame = ctk.CTkFrame(skill_area, fg_color="transparent")
    bot.grid_frame.grid(row=0, column=0, sticky="n", padx=0)
    bot.grid_labels = [[None] * 4 for _ in range(4)]
    for r in range(4):
        for c in range(4):
            lbl = ctk.CTkLabel(bot.grid_frame, text="", width=21, height=21, corner_radius=4, fg_color=colors["panel_3"])
            lbl.grid(row=r, column=c, padx=2, pady=2)
            bot.grid_labels[r][c] = lbl

    dir_frame = ctk.CTkFrame(skill_area, fg_color="transparent")
    dir_frame.grid(row=1, column=0, sticky="n", pady=(10, 0))
    for idx, (text, val) in enumerate([("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right")]):
        button(dir_frame, text, lambda x=val: bot.add_skill_dir(x), width=30, height=28).grid(
            row=0,
            column=idx,
            padx=2,
            pady=2,
        )
    button(dir_frame, "清除", bot.clear_skill_dir, color=colors["red"], hover=colors["red_hover"], width=72, height=28).grid(
        row=1,
        column=0,
        columnspan=4,
        sticky="ew",
        padx=2,
        pady=(8, 2),
    )

    box_delete, bot.btn_delete, bot.entry_delete, bot.lbl_delete = create_task_card(
        bot.config_frame,
        3,
        "4. 删除车辆",
        "独立功能 · 仅 Mazda",
        "开始",
        lambda: bot.start_pipeline("delete"),
        colors["red"],
        colors["red_hover"],
        bot.config.get("delete_count", 30),
    )
    bot.box_delete = box_delete
    bot.lbl_delete_note = label(
        box_delete,
        "已加入大循环",
        color=colors["muted_2"],
        font=ctk.CTkFont(family=ui_font, size=11),
    )
    bot.lbl_delete_note.place(relx=0.5, y=250, anchor="s")

    bot.side_panel = card(bot.config_frame, height=68, fg_color=colors["panel"])
    bot.side_panel.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
    bot.side_panel.pack_propagate(False)
    next_grid = ctk.CTkFrame(bot.side_panel, fg_color="transparent")
    next_grid.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=2)
    next_row = ctk.CTkFrame(next_grid, fg_color="transparent")
    next_row.pack(anchor="w", expand=True)
    for idx, (text, var, default, command) in enumerate([
        ("跑图➡买车", bot.var_chk1, bot.config.get("next_1", 2), lambda: bot.on_flow_route_changed("race_buy")),
        ("买车➡抽奖", bot.var_chk2, bot.config.get("next_2", 3), bot.save_config),
        ("抽奖➡跑图", bot.var_chk3, bot.config.get("next_3", 1), bot.save_config),
        ("跑图➡删车", bot.var_race_to_delete, None, lambda: bot.on_flow_route_changed("race_delete")),
        ("删车➡跑图", bot.var_delete_to_race, None, bot.save_config),
    ]):
        row = ctk.CTkFrame(next_row, fg_color="transparent", width=108, height=38)
        row.pack(side="left", padx=(0, 2))
        row.pack_propagate(False)
        ctk.CTkCheckBox(row, text=text, variable=var, command=command, font=font_small).pack(
            fill="both", expand=True, padx=4, pady=5
        )
        if default is not None:
            nxt = entry(row, width=42, height=26)
            nxt.insert(0, str(default))
            if idx == 0:
                bot.entry_next1 = nxt
            elif idx == 1:
                bot.entry_next2 = nxt
            elif idx == 2:
                bot.entry_next3 = nxt

    bot.chk1 = bot.var_chk1
    bot.chk2 = bot.var_chk2
    bot.chk3 = bot.var_chk3

    vehicle_selector = ctk.CTkFrame(bot.side_panel, fg_color="transparent", width=440)
    vehicle_selector.pack(side="right", fill="y", padx=14, pady=8)
    vehicle_selector.pack_propagate(False)
    vehicle_info = ctk.CTkFrame(vehicle_selector, fg_color="transparent", width=180)
    vehicle_info.pack(side="left", fill="y")
    vehicle_info.pack_propagate(False)
    label(vehicle_info, "专精车辆", color=colors["muted"], font=font_small).pack(anchor="w")
    bot.seg_buy_cj_vehicle = ctk.CTkSegmentedButton(
        vehicle_selector,
        values=["斯巴鲁 22B", "马自达"],
        variable=bot.var_buy_cj_vehicle,
        command=bot.on_buy_cj_vehicle_changed,
        height=30,
        corner_radius=7,
        fg_color=colors["panel_2"],
        selected_color=colors["green"],
        selected_hover_color=colors["green_hover"],
        unselected_color=colors["button"],
        unselected_hover_color=colors["button_hover"],
        text_color=colors["text"],
        font=font_small,
    )
    bot._buy_cj_vehicle_labels = {"subaru": "斯巴鲁 22B", "mazda": "马自达"}
    bot.seg_buy_cj_vehicle.pack(side="right", fill="x", expand=True, padx=(10, 0), pady=10)
    price_suffix = " · 需要通行证" if configured_buy_cj_vehicle == "mazda" else ""
    bot.lbl_buy_cj_vehicle_price = label(
        vehicle_info,
        f"单价 {selected_vehicle_price:,} CR{price_suffix}",
        color=colors["muted_2"],
        font=ctk.CTkFont(family=ui_font, size=11),
    )
    bot.lbl_buy_cj_vehicle_price.pack(anchor="w", pady=(2, 0))

    bot.global_settings_frame = card(bot.main_container, height=52, fg_color="#111112")
    bot.global_settings_frame.pack(fill="x", pady=(12, 0))
    bot.global_settings_frame.pack_propagate(False)
    label(bot.global_settings_frame, "守护设置", font=font_section).pack(side="left", padx=(16, 18))
    label(bot.global_settings_frame, "大循环", color=colors["muted"], font=font_small).pack(side="left", padx=(0, 6))
    bot.entry_global_loop = entry(bot.global_settings_frame, width=62, height=30)
    bot.entry_global_loop.insert(0, str(bot.config.get("global_loops", 10)))
    bot.entry_global_loop.pack(side="left", padx=(0, 16))
    label(bot.global_settings_frame, "单局超时", color=colors["muted"], font=font_small).pack(side="left", padx=(0, 6))
    bot.entry_race_timeout = entry(bot.global_settings_frame, width=68, height=30)
    bot.entry_race_timeout.insert(0, str(bot.config.get("race_timeout", 300)))
    bot.entry_race_timeout.pack(side="left", padx=(0, 16))
    bot.sw_diagnostic_mode = ctk.CTkSwitch(
        bot.global_settings_frame,
        text="诊断模式",
        variable=bot.var_diagnostic_mode,
        command=bot.on_diagnostic_mode_changed,
        progress_color=colors["blue"],
        font=font_small,
    )
    bot.sw_diagnostic_mode.pack(side="right", padx=(0, 12))
    bot.sw_background_mouse = ctk.CTkSwitch(
        bot.global_settings_frame,
        text="后台鼠标",
        variable=bot.var_background_mouse,
        command=bot.on_background_mouse_changed,
        progress_color=colors["green"],
        font=font_small,
    )
    bot.sw_background_mouse.pack(side="right", padx=(0, 12))
    bot.sw_compact_on_run = ctk.CTkSwitch(
        bot.global_settings_frame,
        text="自动缩小",
        variable=bot.var_compact_on_run,
        command=bot.on_compact_on_run_changed,
        progress_color=colors["green"],
        font=font_small,
    )
    bot.sw_compact_on_run.pack(side="right", padx=(0, 12))

    bot.runtime_frame = card(bot.main_container, height=66, fg_color="#111112")
    bot.runtime_frame.pack(fill="x", pady=(10, 0))
    bot.runtime_frame.pack_propagate(False)

    bot.lbl_run_state = ctk.CTkLabel(
        bot.runtime_frame,
        text="待机",
        width=76,
        height=34,
        corner_radius=8,
        fg_color=colors["panel_3"],
        text_color=colors["text"],
        font=font_section,
    )
    bot.lbl_run_state.pack(side="left", padx=(14, 12), pady=14)

    def make_runtime_label(title, value="--"):
        frame = ctk.CTkFrame(bot.runtime_frame, fg_color="transparent")
        frame.pack(side="left", padx=(0, 18), pady=9)
        label(frame, title, color=colors["muted_2"], font=ctk.CTkFont(family=ui_font, size=11)).pack(anchor="w")
        lbl = label(frame, value, font=font_small)
        lbl.pack(anchor="w")
        return lbl

    bot.lbl_runtime_task = make_runtime_label("当前任务", "等待中")
    bot.lbl_runtime_progress = make_runtime_label("任务进度", "0 / 0")
    bot.lbl_runtime_loop = make_runtime_label("大循环", "0 / 0")
    bot.lbl_runtime_task_time = make_runtime_label("本任务耗时", "00:00:00")
    bot.lbl_runtime_total_time = make_runtime_label("总运行时间", "00:00:00")
    bot.lbl_runtime_totals = make_runtime_label("模块累计", "跑图 00:00:00 | 买车 00:00:00 | 超抽 00:00:00")

    bot.btn_runtime_stop = button(
        bot.runtime_frame,
        "停止 F8",
        bot.stop_all,
        color=colors["red"],
        hover=colors["red_hover"],
        width=82,
        height=34,
    )
    bot.btn_runtime_stop.configure(state="disabled")
    bot.btn_runtime_stop.pack(side="right", padx=(0, 8), pady=14)

    bot.log_header = ctk.CTkFrame(bot.main_container, fg_color="transparent")
    bot.log_header.pack(fill="x", pady=(10, 0))
    bot.lbl_log_title = label(bot.log_header, "运行日志", font=font_section)
    bot.lbl_log_title.pack(side="left")
    bot.btn_toggle_log = button(bot.log_header, "收起日志", bot.toggle_log_panel, width=82, height=28)
    bot.btn_toggle_log.pack(side="right")

    bot.calibration_frame = ctk.CTkFrame(
        bot.main_container,
        fg_color=colors["panel"],
        corner_radius=8,
        border_width=1,
        border_color=colors["line"],
        height=38,
    )
    bot.calibration_frame.pack(fill="x", pady=(8, 0))
    bot.calibration_frame.pack_propagate(False)
    label(bot.calibration_frame, "自适应校准", color=colors["muted"], font=font_small).pack(side="left", padx=(12, 8))
    bot.lbl_calibration_status = label(bot.calibration_frame, "未校准", color=colors["yellow"], font=font_small)
    bot.lbl_calibration_status.pack(side="left", padx=(0, 12))
    bot.lbl_calibration_detail = label(bot.calibration_frame, "等待游戏窗口", color=colors["text"], font=font_small)
    bot.lbl_calibration_detail.pack(side="left")

    bot.bottom_frame = ctk.CTkFrame(bot.main_container, fg_color="transparent", height=236)
    bot.bottom_frame.pack(fill="both", expand=True, pady=(8, 0))

    bot.btn_stop = button(
        bot.bottom_frame,
        "等待指令 (F8)",
        bot.stop_all,
        color=colors["button"],
        hover=colors["button_hover"],
        width=150,
        height=58,
    )
    bot.btn_stop.pack(side="left", fill="y", padx=(0, 10))

    bot.log_box = ctk.CTkTextbox(
        bot.bottom_frame,
        state="disabled",
        wrap="word",
        corner_radius=8,
        height=220,
        fg_color=colors["panel"],
        border_width=1,
        border_color=colors["line"],
        text_color=colors["text"],
        font=ctk.CTkFont(family=ui_font, size=14),
    )
    bot.log_box.pack(side="left", fill="both", expand=True)

    # Compact running layout, modelled after self_search's 522x398 window.
    # It is a sibling of main_container so the full configuration UI can be
    # hidden without destroying or re-parenting any widgets.
    bot.compact_container = ctk.CTkFrame(bot, fg_color="transparent")
    compact_panel = card(bot.compact_container)
    compact_panel.pack(fill="both", expand=True)

    compact_header = ctk.CTkFrame(compact_panel, fg_color="transparent")
    compact_header.pack(fill="x", padx=16, pady=(14, 8))
    label(compact_header, "FH6 Auto", font=font_title).pack(side="left")
    bot.lbl_compact_state = ctk.CTkLabel(
        compact_header,
        text="运行中",
        width=66,
        height=28,
        corner_radius=7,
        fg_color=colors["green"],
        text_color="#FFFFFF",
        font=font_small,
    )
    bot.lbl_compact_state.pack(side="right")

    compact_action = ctk.CTkFrame(compact_panel, fg_color="transparent")
    compact_action.pack(fill="x", padx=16, pady=(0, 10))
    bot.btn_compact_stop = button(
        compact_action,
        "停止 F8",
        bot.stop_all,
        color=colors["red"],
        hover=colors["red_hover"],
        width=92,
        height=38,
    )
    bot.btn_compact_stop.pack(side="left")
    compact_time_box = ctk.CTkFrame(compact_action, fg_color="transparent")
    compact_time_box.pack(side="right")
    label(compact_time_box, "总运行时间", color=colors["muted"], font=font_small).pack(anchor="e")
    bot.lbl_compact_total_time = label(
        compact_time_box,
        "00:00:00",
        font=ctk.CTkFont(family=ui_font, size=17, weight="bold"),
    )
    bot.lbl_compact_total_time.pack(anchor="e")

    compact_status = ctk.CTkFrame(compact_panel, fg_color=colors["panel_2"], corner_radius=8)
    compact_status.pack(fill="x", padx=16, pady=(0, 10))
    for column in range(3):
        compact_status.grid_columnconfigure(column, weight=1)

    def compact_value(column, title, value):
        holder = ctk.CTkFrame(compact_status, fg_color="transparent")
        holder.grid(row=0, column=column, sticky="ew", padx=10, pady=8)
        label(holder, title, color=colors["muted_2"], font=ctk.CTkFont(family=ui_font, size=11)).pack(anchor="w")
        widget = label(holder, value, font=font_small)
        widget.pack(anchor="w")
        return widget

    bot.lbl_compact_task = compact_value(0, "当前任务", "初始化中...")
    bot.lbl_compact_progress = compact_value(1, "任务进度", "0 / 0")
    bot.lbl_compact_loop = compact_value(2, "大循环", "0 / 0")

    label(compact_panel, "运行日志", color=colors["muted"], font=font_small).pack(
        anchor="w", padx=16, pady=(0, 4)
    )
    bot.compact_log_box = ctk.CTkTextbox(
        compact_panel,
        state="disabled",
        wrap="word",
        corner_radius=8,
        height=170,
        fg_color=colors["bg"],
        border_width=1,
        border_color=colors["line"],
        text_color=colors["text"],
        font=font_body,
    )
    bot.compact_log_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    bot.entry_next1.bind("<FocusOut>", lambda e: bot.normalize_step_entry(bot.entry_next1, 2))
    bot.entry_next2.bind("<FocusOut>", lambda e: bot.normalize_step_entry(bot.entry_next2, 3))
    bot.entry_next3.bind("<FocusOut>", lambda e: bot.normalize_step_entry(bot.entry_next3, 1))

