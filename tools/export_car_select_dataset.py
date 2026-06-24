import argparse
import json
import re
import shutil
from pathlib import Path

import cv2
import numpy as np


CLASSES = ["new_tag", "class_b600", "target_car"]


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def load_template(path: Path):
    img = read_image(path)
    if img is None:
        raise FileNotFoundError(path)
    return img


def scaled(img, scale):
    if abs(scale - 1.0) < 1e-6:
        return img
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def filename_key(path: Path):
    match = re.match(r"(.+?)_(pass|miss)\.png$", path.name)
    if not match:
        return path.stem
    return match.group(1)


def yolo_line(cls_id, box, img_w, img_h):
    x, y, w, h = box
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    nw = w / img_w
    nh = h / img_h
    return f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def nms_points(res, threshold, cell_w, cell_h):
    ys, xs = np.where(res >= threshold)
    points = [(int(y), int(x), float(res[y, x])) for y, x in zip(ys, xs)]
    points.sort(key=lambda p: (p[0], p[1], -p[2]))
    seen = set()
    out = []
    for y, x, score in points:
        key = (x // max(1, cell_w), y // max(1, cell_h))
        if key in seen:
            continue
        seen.add(key)
        out.append((y, x, score))
    return out


def box_iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def dedupe_boxes(items, iou_threshold=0.35):
    # items: list[(score, [x,y,w,h])]
    items = sorted(items, key=lambda item: item[0], reverse=True)
    kept = []
    for score, box in items:
        if any(box_iou(box, kept_box) >= iou_threshold for _, kept_box in kept):
            continue
        kept.append((score, box))
    return kept


def detect_template_boxes(img, tpl_raw, scales, threshold, class_name):
    all_boxes = []
    for scale in scales:
        tpl = scaled(tpl_raw, scale)
        h, w = tpl.shape[:2]
        if h < 5 or w < 5 or h > img.shape[0] or w > img.shape[1]:
            continue
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        points = nms_points(res, threshold, max(8, w // 2), max(8, h // 2))
        for y, x, score in points:
            if class_name in {"new_tag", "class_b600"}:
                if x < int(img.shape[1] * 0.16) or y < int(img.shape[0] * 0.14) or y > int(img.shape[0] * 0.94):
                    continue
            all_boxes.append((score, [x, y, w, h]))
    return dedupe_boxes(all_boxes)


def validate_target_car_box(img, car_tpl, box, top_threshold=0.62, bottom_threshold=0.62):
    x, y, w, h = box
    roi = img[y:y + h, x:x + w]
    if roi.shape[:2] != car_tpl.shape[:2]:
        return False, 0.0, 0.0

    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray_tpl = cv2.cvtColor(car_tpl, cv2.COLOR_BGR2GRAY)
    pad = 5

    top_h = int(h * 0.24)
    tpl_top = gray_tpl[:top_h, :]
    roi_top = gray_roi[:max(top_h + pad * 2, int(h * 0.34)), :]
    top_score = 0.0
    if tpl_top.shape[0] > pad * 2 and tpl_top.shape[1] > pad * 2:
        tpl_top_core = tpl_top[pad:-pad, pad:-pad]
        if roi_top.shape[0] >= tpl_top_core.shape[0] and roi_top.shape[1] >= tpl_top_core.shape[1]:
            res = cv2.matchTemplate(roi_top, tpl_top_core, cv2.TM_CCOEFF_NORMED)
            _, top_score, _, _ = cv2.minMaxLoc(res)

    bottom_h = int(h * 0.25)
    right_w = int(w * 0.35)
    tpl_bottom = car_tpl[h - bottom_h:, w - right_w:]
    roi_bottom = roi[h - int(h * 0.36):, w - int(w * 0.46):]
    bottom_score = 0.0
    if tpl_bottom.shape[0] > pad * 2 and tpl_bottom.shape[1] > pad * 2:
        tpl_bottom_core = tpl_bottom[pad:-pad, pad:-pad]
        if roi_bottom.shape[0] >= tpl_bottom_core.shape[0] and roi_bottom.shape[1] >= tpl_bottom_core.shape[1]:
            res = cv2.matchTemplate(roi_bottom, tpl_bottom_core, cv2.TM_CCOEFF_NORMED)
            _, bottom_score, _, _ = cv2.minMaxLoc(res)

    return top_score >= top_threshold and bottom_score >= bottom_threshold, float(top_score), float(bottom_score)


def detect_all_draft_boxes(img, car_tpl_raw, tag_tpl_raw, class_tpl_raw, scales):
    labels = {name: [] for name in CLASSES}

    labels["new_tag"] = detect_template_boxes(img, tag_tpl_raw, scales, 0.50, "new_tag")
    labels["class_b600"] = detect_template_boxes(img, class_tpl_raw, scales, 0.78, "class_b600")

    car_candidates = []
    for scale in scales:
        car_tpl = scaled(car_tpl_raw, scale)
        raw_boxes = detect_template_boxes(img, car_tpl_raw, [scale], 0.72, "target_car")
        for score, box in raw_boxes:
            ok, top_score, bottom_score = validate_target_car_box(img, car_tpl, box)
            if ok:
                car_candidates.append((score + top_score * 0.15 + bottom_score * 0.15, box))
    labels["target_car"] = dedupe_boxes(car_candidates)

    return labels


def detect_one(img, car_tpl_raw, tag_tpl_raw, class_tpl_raw, scales):
    for scale in scales:
        car_tpl = scaled(car_tpl_raw, scale)
        tag_tpl = scaled(tag_tpl_raw, scale)
        class_tpl = scaled(class_tpl_raw, scale)
        h_m, w_m = car_tpl.shape[:2]
        h_t, w_t = tag_tpl.shape[:2]
        h_c, w_c = class_tpl.shape[:2]

        if min(h_m, w_m, h_t, w_t, h_c, w_c) < 5:
            continue
        if h_m > img.shape[0] or w_m > img.shape[1]:
            continue

        tag_res = cv2.matchTemplate(img, tag_tpl, cv2.TM_CCOEFF_NORMED)
        tag_candidates = nms_points(tag_res, 0.52, max(12, w_t // 2), max(10, h_t // 2))
        for ty, tx, tag_score in tag_candidates:
            if tx < int(img.shape[1] * 0.20) or ty < int(img.shape[0] * 0.18) or ty > int(img.shape[0] * 0.90):
                continue

            cx1 = max(0, int(tx - w_c * 1.45))
            cy1 = max(0, int(ty - h_c * 0.25))
            cx2 = min(img.shape[1], int(tx + w_t + w_c * 0.40))
            cy2 = min(img.shape[0], int(ty + h_t + h_c * 1.70))
            class_search = img[cy1:cy2, cx1:cx2]
            if class_search.shape[0] < h_c or class_search.shape[1] < w_c:
                continue
            class_res = cv2.matchTemplate(class_search, class_tpl, cv2.TM_CCOEFF_NORMED)
            _, class_score, _, class_loc = cv2.minMaxLoc(class_res)
            if class_score < 0.58:
                continue
            class_x = cx1 + class_loc[0]
            class_y = cy1 + class_loc[1]

            sx1 = max(0, int(tx - w_m * 1.12))
            sy1 = max(0, int(ty - h_m * 1.08))
            sx2 = min(img.shape[1], int(tx + w_t + w_m * 0.12))
            sy2 = min(img.shape[0], int(ty + h_t + h_m * 0.18))
            car_search = img[sy1:sy2, sx1:sx2]
            if car_search.shape[0] < h_m or car_search.shape[1] < w_m:
                continue
            car_res = cv2.matchTemplate(car_search, car_tpl, cv2.TM_CCOEFF_NORMED)
            _, car_score, _, car_loc = cv2.minMaxLoc(car_res)
            if car_score < 0.56:
                continue
            card_x = sx1 + car_loc[0]
            card_y = sy1 + car_loc[1]

            tag_rel_x = tx - card_x
            tag_rel_y = ty - card_y
            if not (int(w_m * 0.62) <= tag_rel_x <= int(w_m * 1.08) and int(h_m * 0.55) <= tag_rel_y <= int(h_m * 1.08)):
                continue

            return {
                "scale": scale,
                "scores": {
                    "new_tag": tag_score,
                    "class_b600": float(class_score),
                    "target_car": float(car_score),
                },
                "boxes": {
                    "new_tag": [tx, ty, w_t, h_t],
                    "class_b600": [class_x, class_y, w_c, h_c],
                    "target_car": [card_x, card_y, w_m, h_m],
                },
            }
    return None


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Export car-select debug captures to a YOLO-style draft dataset.")
    parser.add_argument("--debug-dir", default="debug/car_select")
    parser.add_argument("--output", default="datasets/fh6_car_select")
    parser.add_argument("--car-template", default="images/1080p/newCC.png")
    parser.add_argument("--tag-template", default="images/1080p/newcartag.png")
    parser.add_argument("--class-template", default="images/1080p/classB600.png")
    parser.add_argument("--scales", default="1.0,0.98,1.02,0.95,1.05")
    args = parser.parse_args()

    debug_dir = Path(args.debug_dir)
    output = Path(args.output)
    raw_dir = debug_dir / "raw"
    pass_dir = debug_dir / "pass"
    miss_dir = debug_dir / "miss"
    images_dir = output / "images" / "draft"
    labels_dir = output / "labels" / "draft"
    meta_dir = output / "meta"

    car_tpl = load_template(Path(args.car_template))
    tag_tpl = load_template(Path(args.tag_template))
    class_tpl = load_template(Path(args.class_template))
    scales = [float(x.strip()) for x in args.scales.split(",") if x.strip()]

    status_by_key = {}
    for p in pass_dir.glob("*.png"):
        status_by_key[filename_key(p)] = "pass"
    for p in miss_dir.glob("*.png"):
        status_by_key.setdefault(filename_key(p), "miss")

    rows = []
    for key, status in sorted(status_by_key.items()):
        raw_name = f"{key}_{status}.png"
        raw_path = raw_dir / raw_name
        if not raw_path.exists():
            continue
        img = read_image(raw_path)
        if img is None:
            continue

        out_img = images_dir / raw_name
        out_label = labels_dir / f"{Path(raw_name).stem}.txt"
        out_meta = meta_dir / f"{Path(raw_name).stem}.json"
        out_img.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, out_img)

        meta = {
            "source": str(raw_path),
            "status": status,
            "classes": CLASSES,
            "image": {"width": int(img.shape[1]), "height": int(img.shape[0])},
            "note": "Auto-generated draft labels. Review before training.",
        }

        if status == "pass":
            det = detect_one(img, car_tpl, tag_tpl, class_tpl, scales)
            all_labels = detect_all_draft_boxes(img, car_tpl, tag_tpl, class_tpl, scales)
            meta["detection"] = det
            meta["draft_labels"] = {
                cls_name: [{"score": float(score), "box": box} for score, box in all_labels[cls_name]]
                for cls_name in CLASSES
            }
            if any(all_labels[cls_name] for cls_name in CLASSES):
                lines = []
                for cls_id, cls_name in enumerate(CLASSES):
                    for _, box in all_labels[cls_name]:
                        lines.append(yolo_line(cls_id, box, img.shape[1], img.shape[0]))
                write_text(out_label, "\n".join(lines) + "\n")
            else:
                write_text(out_label, "")
                meta["warning"] = "pass image did not produce draft boxes"
        else:
            write_text(out_label, "")

        out_meta.parent.mkdir(parents=True, exist_ok=True)
        out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append((raw_name, status))

    yaml_text = (
        f"path: {output.resolve().as_posix()}\n"
        "train: images/draft\n"
        "val: images/draft\n"
        "names:\n"
        + "\n".join(f"  {i}: {name}" for i, name in enumerate(CLASSES))
        + "\n"
    )
    write_text(output / "fh6_car_select.yaml", yaml_text)
    write_text(output / "README.md", "# FH6 Car Select Draft Dataset\n\nAuto-exported draft dataset. Review labels before training.\n")

    print(f"exported {len(rows)} images to {output}")
    print(f"pass: {sum(1 for _, s in rows if s == 'pass')}")
    print(f"miss: {sum(1 for _, s in rows if s == 'miss')}")


if __name__ == "__main__":
    main()
