import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass
class Detection:
    image: Path
    ok: bool
    reason: str
    click_x: int | None = None
    click_y: int | None = None
    tag_score: float = 0.0
    class_score: float = 0.0
    car_score: float = 0.0
    scale: float = 1.0
    tag_box: tuple[int, int, int, int] | None = None
    class_box: tuple[int, int, int, int] | None = None
    car_box: tuple[int, int, int, int] | None = None


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def load_template(path: Path):
    img = read_image(path)
    if img is None:
        raise FileNotFoundError(f"Cannot read template: {path}")
    return img


def scaled(img, scale: float):
    if abs(scale - 1.0) < 1e-6:
        return img
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def nms_points(res, threshold: float, cell_w: int, cell_h: int):
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


def find_strict_car(
    screen_bgr,
    car_tpl_raw,
    tag_tpl_raw,
    class_tpl_raw,
    scales,
    tag_threshold,
    class_threshold,
    car_threshold,
    top_threshold,
    bottom_threshold,
    car_right_pad_ratio,
    car_down_pad_ratio,
    max_debug_failures=5,
):
    failures = []

    for scale in scales:
        car_tpl = scaled(car_tpl_raw, scale)
        tag_tpl = scaled(tag_tpl_raw, scale)
        class_tpl = scaled(class_tpl_raw, scale)
        h_m, w_m = car_tpl.shape[:2]
        h_t, w_t = tag_tpl.shape[:2]
        h_c, w_c = class_tpl.shape[:2]

        if min(h_m, w_m, h_t, w_t, h_c, w_c) < 5:
            continue
        if h_m > screen_bgr.shape[0] or w_m > screen_bgr.shape[1]:
            continue

        tag_res = cv2.matchTemplate(screen_bgr, tag_tpl, cv2.TM_CCOEFF_NORMED)
        tag_candidates = nms_points(
            tag_res,
            tag_threshold,
            max(12, w_t // 2),
            max(10, h_t // 2),
        )

        if not tag_candidates:
            failures.append(f"scale {scale:.3f}: no new tag")
            continue

        for ty, tx, tag_score in tag_candidates:
            cx1 = max(0, int(tx - w_c * 1.45))
            cy1 = max(0, int(ty - h_c * 0.25))
            cx2 = min(screen_bgr.shape[1], int(tx + w_t + w_c * 0.40))
            cy2 = min(screen_bgr.shape[0], int(ty + h_t + h_c * 1.70))
            class_search = screen_bgr[cy1:cy2, cx1:cx2]
            if class_search.shape[0] < h_c or class_search.shape[1] < w_c:
                failures.append(f"scale {scale:.3f}: class roi too small near tag {tx},{ty}")
                continue

            class_res = cv2.matchTemplate(class_search, class_tpl, cv2.TM_CCOEFF_NORMED)
            _, class_score, _, class_loc = cv2.minMaxLoc(class_res)
            if class_score < class_threshold:
                failures.append(
                    f"scale {scale:.3f}: class low tag={tag_score:.3f} b600={class_score:.3f} at {tx},{ty}"
                )
                continue

            class_x = cx1 + class_loc[0]
            class_y = cy1 + class_loc[1]

            sx1 = max(0, int(tx - w_m * 1.12))
            sy1 = max(0, int(ty - h_m * 1.08))
            sx2 = min(screen_bgr.shape[1], int(tx + w_t + w_m * car_right_pad_ratio))
            sy2 = min(screen_bgr.shape[0], int(ty + h_t + h_m * car_down_pad_ratio))
            car_search = screen_bgr[sy1:sy2, sx1:sx2]
            if car_search.shape[0] < h_m or car_search.shape[1] < w_m:
                failures.append(f"scale {scale:.3f}: car roi too small near tag {tx},{ty}")
                continue

            car_res = cv2.matchTemplate(car_search, car_tpl, cv2.TM_CCOEFF_NORMED)
            _, car_score, _, car_loc = cv2.minMaxLoc(car_res)
            card_x = sx1 + car_loc[0]
            card_y = sy1 + car_loc[1]
            card_roi = screen_bgr[card_y:card_y + h_m, card_x:card_x + w_m]
            if card_roi.shape[:2] != car_tpl.shape[:2]:
                failures.append(f"scale {scale:.3f}: card roi clipped")
                continue

            tag_rel_x = tx - card_x
            tag_rel_y = ty - card_y
            valid_rel = (
                int(w_m * 0.62) <= tag_rel_x <= int(w_m * 1.08)
                and int(h_m * 0.55) <= tag_rel_y <= int(h_m * 1.08)
            )
            if not valid_rel:
                failures.append(
                    f"scale {scale:.3f}: rel invalid tag={tag_score:.3f} car={car_score:.3f} rel={tag_rel_x},{tag_rel_y}"
                )
                continue

            if car_score < car_threshold:
                failures.append(
                    f"scale {scale:.3f}: car low tag={tag_score:.3f} b600={class_score:.3f} car={car_score:.3f}"
                )
                continue

            top_h = int(h_m * 0.24)
            top_pad = max(4, int(5 * scale))
            tpl_top = cv2.cvtColor(car_tpl[:top_h, :], cv2.COLOR_BGR2GRAY)
            roi_top = cv2.cvtColor(card_roi[:max(top_h + top_pad * 2, int(h_m * 0.34)), :], cv2.COLOR_BGR2GRAY)
            top_score = 0.0
            if tpl_top.shape[0] > top_pad * 2 and tpl_top.shape[1] > top_pad * 2:
                tpl_top_core = tpl_top[top_pad:-top_pad, top_pad:-top_pad]
                if roi_top.shape[0] >= tpl_top_core.shape[0] and roi_top.shape[1] >= tpl_top_core.shape[1]:
                    top_res = cv2.matchTemplate(roi_top, tpl_top_core, cv2.TM_CCOEFF_NORMED)
                    _, top_score, _, _ = cv2.minMaxLoc(top_res)
            if top_score < top_threshold:
                failures.append(
                    f"scale {scale:.3f}: top low tag={tag_score:.3f} b600={class_score:.3f} car={car_score:.3f} top={top_score:.3f}"
                )
                continue

            bottom_h = int(h_m * 0.25)
            right_w = int(w_m * 0.35)
            tpl_bottom = car_tpl[h_m - bottom_h:, w_m - right_w:]
            roi_bottom = card_roi[h_m - int(h_m * 0.36):, w_m - int(w_m * 0.46):]
            bottom_score = 0.0
            if tpl_bottom.shape[0] > top_pad * 2 and tpl_bottom.shape[1] > top_pad * 2:
                tpl_bottom_core = tpl_bottom[top_pad:-top_pad, top_pad:-top_pad]
                if roi_bottom.shape[0] >= tpl_bottom_core.shape[0] and roi_bottom.shape[1] >= tpl_bottom_core.shape[1]:
                    bottom_res = cv2.matchTemplate(roi_bottom, tpl_bottom_core, cv2.TM_CCOEFF_NORMED)
                    _, bottom_score, _, _ = cv2.minMaxLoc(bottom_res)
            if bottom_score < bottom_threshold:
                failures.append(
                    f"scale {scale:.3f}: bottom low tag={tag_score:.3f} b600={class_score:.3f} car={car_score:.3f} top={top_score:.3f} bottom={bottom_score:.3f}"
                )
                continue

            return Detection(
                image=Path(),
                ok=True,
                reason="pass",
                click_x=card_x + w_m // 2,
                click_y=card_y + h_m // 2,
                tag_score=tag_score,
                class_score=float(class_score),
                car_score=float(car_score),
                scale=scale,
                tag_box=(tx, ty, w_t, h_t),
                class_box=(class_x, class_y, w_c, h_c),
                car_box=(card_x, card_y, w_m, h_m),
            )

    reason = failures[-1] if failures else "no candidates"
    if len(failures) > max_debug_failures:
        reason = reason + f" (+{len(failures) - max_debug_failures} more)"
    return Detection(image=Path(), ok=False, reason=reason)


def collect_images(path: Path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)


def draw_detection(img, det: Detection):
    out = img.copy()
    if det.tag_box:
        x, y, w, h = det.tag_box
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cv2.putText(out, f"NEW {det.tag_score:.2f}", (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    if det.class_box:
        x, y, w, h = det.class_box
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 128, 255), 2)
        cv2.putText(out, f"B600 {det.class_score:.2f}", (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 128, 255), 2)
    if det.car_box:
        x, y, w, h = det.car_box
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(out, f"CAR {det.car_score:.2f}", (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    if det.click_x is not None and det.click_y is not None:
        cv2.drawMarker(out, (det.click_x, det.click_y), (0, 0, 255), cv2.MARKER_CROSS, 28, 2)
        cv2.putText(out, f"CLICK {det.click_x},{det.click_y}", (det.click_x + 8, det.click_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return out


def write_image(path: Path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix, img)
    if not ok:
        raise RuntimeError(f"Cannot encode image: {path}")
    buf.tofile(str(path))


def main():
    parser = argparse.ArgumentParser(description="Offline strict wheelspin car detection tester.")
    parser.add_argument("--input", default="screenshot", help="Image file or directory.")
    parser.add_argument("--car-template", default="images/1080p/newCC.png")
    parser.add_argument("--tag-template", default="images/1080p/newcartag.png")
    parser.add_argument("--class-template", default="images/1080p/classB600.png")
    parser.add_argument("--scales", default="1.0,0.98,1.02,0.95,1.05")
    parser.add_argument("--tag-threshold", type=float, default=0.52)
    parser.add_argument("--class-threshold", type=float, default=0.58)
    parser.add_argument("--car-threshold", type=float, default=0.56)
    parser.add_argument("--top-threshold", type=float, default=0.72)
    parser.add_argument("--bottom-threshold", type=float, default=0.72)
    parser.add_argument("--car-right-pad-ratio", type=float, default=0.12)
    parser.add_argument("--car-down-pad-ratio", type=float, default=0.18)
    parser.add_argument("--output-dir", default="debug/strict_car_test")
    parser.add_argument("--save-debug", action="store_true", help="Save annotated result images.")
    parser.add_argument("--csv", default="", help="Optional CSV output path.")
    args = parser.parse_args()

    images = [
        p for p in collect_images(Path(args.input))
        if p.name not in {
            Path(args.car_template).name,
            Path(args.tag_template).name,
            Path(args.class_template).name,
            "target_car.png",
            "new_target_car.png",
        }
    ]
    car_tpl = load_template(Path(args.car_template))
    tag_tpl = load_template(Path(args.tag_template))
    class_tpl = load_template(Path(args.class_template))
    scales = [float(x.strip()) for x in args.scales.split(",") if x.strip()]

    rows = []
    print("image, result, click, scores, scale, reason")
    for img_path in images:
        img = read_image(img_path)
        if img is None:
            det = Detection(image=img_path, ok=False, reason="cannot read image")
        else:
            det = find_strict_car(
                img,
                car_tpl,
                tag_tpl,
                class_tpl,
                scales,
                args.tag_threshold,
                args.class_threshold,
                args.car_threshold,
                args.top_threshold,
                args.bottom_threshold,
                args.car_right_pad_ratio,
                args.car_down_pad_ratio,
            )
            det.image = img_path

        click = "-" if det.click_x is None else f"{det.click_x},{det.click_y}"
        result = "PASS" if det.ok else "MISS"
        score_text = f"new={det.tag_score:.3f} b600={det.class_score:.3f} car={det.car_score:.3f}"
        print(f"{img_path.name}, {result}, {click}, {score_text}, {det.scale:.3f}, {det.reason}")

        rows.append({
            "image": str(img_path),
            "result": result,
            "click_x": det.click_x if det.click_x is not None else "",
            "click_y": det.click_y if det.click_y is not None else "",
            "tag_score": f"{det.tag_score:.4f}",
            "class_score": f"{det.class_score:.4f}",
            "car_score": f"{det.car_score:.4f}",
            "scale": f"{det.scale:.4f}",
            "reason": det.reason,
        })

        if args.save_debug and img is not None:
            annotated = draw_detection(img, det)
            out_name = f"{result.lower()}_{img_path.stem}.png"
            write_image(Path(args.output_dir) / out_name, annotated)

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)


if __name__ == "__main__":
    main()
