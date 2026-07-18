"""Hidden F9 developer editor for live CustomTkinter text adjustments."""

from dataclasses import dataclass

import customtkinter as ctk

CONFIG_KEY = "developer_ui_text_overrides"


@dataclass
class EditableText:
    key: str
    widget: object
    kind: str
    option: str
    value: object
    owner: object


TEXT_WIDGET_TYPES = (
    (ctk.CTkButton, "按钮"),
    (ctk.CTkLabel, "文本"),
    (ctk.CTkCheckBox, "复选框"),
    (ctk.CTkSwitch, "开关"),
)


def _walk_widgets(root, prefix):
    for child_index, child in enumerate(root.winfo_children()):
        child_key = f"{prefix}/{child.__class__.__name__}[{child_index}]"
        yield child_key, child
        if isinstance(
            child,
            (
                ctk.CTkButton,
                ctk.CTkLabel,
                ctk.CTkCheckBox,
                ctk.CTkSwitch,
                ctk.CTkSegmentedButton,
                ctk.CTkEntry,
            ),
        ):
            continue
        yield from _walk_widgets(child, child_key)


def _read_editable(bot, key, widget):
    if isinstance(widget, ctk.CTkSegmentedButton):
        values = list(widget.cget("values") or [])
        if values:
            return EditableText(key, widget, "分段按钮", "values", values, bot)
        return None

    if isinstance(widget, ctk.CTkEntry):
        placeholder = str(widget.cget("placeholder_text") or "")
        if placeholder:
            return EditableText(key, widget, "输入框提示", "placeholder_text", placeholder, bot)
        return None

    for widget_type, kind in TEXT_WIDGET_TYPES:
        if isinstance(widget, widget_type):
            text = str(widget.cget("text") or "")
            if text:
                return EditableText(key, widget, kind, "text", text, bot)
            return None
    return None


def collect_editable_texts(bot):
    """Collect app-owned text widgets, excluding the editor window itself."""
    roots = []
    for name in ("main_container", "compact_container"):
        root = getattr(bot, name, None)
        if root is not None:
            roots.append((name, root))

    records = []
    seen = set()
    for root_name, root in roots:
        for key, widget in _walk_widgets(root, root_name):
            identity = id(widget)
            if identity in seen:
                continue
            seen.add(identity)
            record = _read_editable(bot, key, widget)
            if record is not None:
                records.append(record)
    return records


def _editor_string(record):
    if record.option == "values":
        return " | ".join(str(value) for value in record.value)
    return str(record.value).replace("\n", "\\n")


def _apply_editor_string(record, raw_value):
    if record.option == "values":
        values = [part.strip() for part in raw_value.split("|") if part.strip()]
        if not values:
            raise ValueError("分段按钮至少需要一个非空选项")
        vehicle_segment = getattr(record.owner, "seg_buy_cj_vehicle", None)
        if record.widget is vehicle_segment and len(values) != 2:
            raise ValueError("车辆切换按钮必须保留两个选项")
        current = str(record.widget.get() or "")
        vehicle_mode = None
        if record.widget is vehicle_segment:
            vehicle_mode = str(record.owner.config.get("buy_cj_vehicle", "subaru")).lower()
        record.widget.configure(values=values)
        if vehicle_mode in ("subaru", "mazda"):
            record.owner._buy_cj_vehicle_labels = {
                "subaru": values[0],
                "mazda": values[1],
            }
            record.widget.set(values[1] if vehicle_mode == "mazda" else values[0])
        elif current in values:
            record.widget.set(current)
        else:
            record.widget.set(values[0])
        return

    value = raw_value.replace("\\n", "\n")
    record.widget.configure(**{record.option: value})


def _serialized_editor_value(record, raw_value):
    if record.option == "values":
        return [part.strip() for part in raw_value.split("|") if part.strip()]
    return raw_value.replace("\\n", "\n")


def apply_saved_text_overrides(bot):
    """Apply persisted developer text overrides after the UI is constructed."""
    overrides = bot.config.get(CONFIG_KEY, {}) or {}
    if not isinstance(overrides, dict):
        return 0

    applied = 0
    for record in collect_editable_texts(bot):
        saved = overrides.get(record.key)
        if not isinstance(saved, dict) or saved.get("option") != record.option:
            continue
        value = saved.get("value")
        if record.option == "values":
            if not isinstance(value, list):
                continue
            raw_value = " | ".join(str(item) for item in value)
        else:
            raw_value = str(value).replace("\n", "\\n")
        try:
            _apply_editor_string(record, raw_value)
            applied += 1
        except Exception:
            continue
    return applied


def open_developer_text_editor(bot):
    existing = getattr(bot, "_developer_editor_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except Exception:
            pass

    records = collect_editable_texts(bot)
    window = ctk.CTkToplevel(bot)
    bot._developer_editor_window = window
    window.title("开发者 UI 文本调试器 · F9")
    window.geometry("980x720")
    window.minsize(900, 560)
    window.configure(fg_color="#0B0B0C")
    window.attributes("-topmost", True)

    def close_window():
        bot._developer_editor_window = None
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close_window)

    header = ctk.CTkFrame(window, fg_color="#111112", corner_radius=8)
    header.pack(fill="x", padx=14, pady=(14, 8))
    ctk.CTkLabel(
        header,
        text="开发者 UI 文本调试器",
        font=ctk.CTkFont(family="Microsoft YaHei UI", size=18, weight="bold"),
    ).pack(anchor="w", padx=14, pady=(10, 0))
    ctk.CTkLabel(
        header,
        text="可永久保存到用户配置；分段按钮使用 | 分隔选项，\\n 表示换行。",
        text_color="#A7B0BC",
        font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
    ).pack(anchor="w", padx=14, pady=(2, 10))

    scroll = ctk.CTkScrollableFrame(
        window,
        fg_color="#111112",
        corner_radius=8,
        border_width=1,
        border_color="#30363D",
    )
    scroll.pack(fill="both", expand=True, padx=14, pady=(0, 8))
    scroll.grid_columnconfigure(1, weight=1)

    editor_rows = []
    kind_counts = {}
    for row_index, record in enumerate(records):
        kind_counts[record.kind] = kind_counts.get(record.kind, 0) + 1
        preview = _editor_string(record).strip() or "（空）"
        if len(preview) > 22:
            preview = preview[:22] + "…"
        descriptor = f"{record.kind} {kind_counts[record.kind]:02d}  {preview}"
        ctk.CTkLabel(
            scroll,
            text=descriptor,
            width=225,
            anchor="w",
            text_color="#A7B0BC",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        ).grid(row=row_index, column=0, sticky="w", padx=(10, 8), pady=4)
        editor = ctk.CTkEntry(
            scroll,
            height=31,
            fg_color="#21262D",
            border_color="#30363D",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
        )
        editor.insert(0, _editor_string(record))
        editor.grid(row=row_index, column=1, sticky="ew", padx=(0, 10), pady=4)
        editor_rows.append((record, editor))

    footer = ctk.CTkFrame(window, fg_color="transparent")
    footer.pack(fill="x", padx=14, pady=(0, 14))
    status = ctk.CTkLabel(
        footer,
        text=f"已扫描 {len(records)} 项可编辑文本",
        text_color="#7D8590",
        font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
    )
    status.pack(side="left")

    def apply_all(persist=False):
        applied = 0
        try:
            saved_overrides = bot.config.get(CONFIG_KEY, {}) or {}
            overrides = dict(saved_overrides) if isinstance(saved_overrides, dict) else {}
            for record, editor in editor_rows:
                raw_value = editor.get()
                _apply_editor_string(record, raw_value)
                if persist:
                    serialized = _serialized_editor_value(record, raw_value)
                    if serialized != record.value or record.key in overrides:
                        overrides[record.key] = {
                            "option": record.option,
                            "value": serialized,
                        }
                applied += 1
            if persist:
                bot.config[CONFIG_KEY] = overrides
                bot.save_config()
                status.configure(
                    text=f"已应用 {applied} 项，并永久保存 {len(overrides)} 项修改",
                    text_color="#30D158",
                )
            else:
                status.configure(text=f"已应用 {applied} 项修改（仅当前运行）", text_color="#0A84FF")
        except Exception as exc:
            status.configure(text=f"应用失败：{exc}", text_color="#FF453A")

    def clear_saved_values():
        try:
            bot.config.pop(CONFIG_KEY, None)
            bot.save_config()
            status.configure(text="已清除永久修改；重启程序后恢复代码默认文本", text_color="#FFD60A")
        except Exception as exc:
            status.configure(text=f"清除失败：{exc}", text_color="#FF453A")

    def restore_open_values():
        restored = 0
        try:
            for record, editor in editor_rows:
                editor.delete(0, "end")
                editor.insert(0, _editor_string(record))
                _apply_editor_string(record, _editor_string(record))
                restored += 1
            status.configure(text=f"已恢复打开编辑器时的 {restored} 项文本", text_color="#FFD60A")
        except Exception as exc:
            status.configure(text=f"恢复失败：{exc}", text_color="#FF453A")

    ctk.CTkButton(
        footer,
        text="关闭",
        width=82,
        fg_color="#2C2C2E",
        hover_color="#3A3A3C",
        command=close_window,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="清除永久修改",
        width=116,
        fg_color="#9A6700",
        hover_color="#7A5200",
        command=clear_saved_values,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="恢复打开时文本",
        width=128,
        fg_color="#2C2C2E",
        hover_color="#3A3A3C",
        command=restore_open_values,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="仅本次应用",
        width=104,
        fg_color="#2C2C2E",
        hover_color="#3A3A3C",
        command=lambda: apply_all(False),
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="应用并永久保存",
        width=136,
        fg_color="#0A84FF",
        hover_color="#006EDB",
        command=lambda: apply_all(True),
    ).pack(side="right")

    window.after(80, window.focus_force)
    return window
