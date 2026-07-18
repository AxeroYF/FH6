import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="Train a YOLO model for FH6 car-select UI detection.")
    parser.add_argument("--data", default="datasets/fh6_car_select/fh6_car_select.yaml")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="fh6_car_select")
    parser.add_argument("--name", default="yolo11n_draft")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_path}")
    project_path = Path(args.project)
    if not project_path.is_absolute():
        project_path = Path.cwd() / project_path

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        # Resolve explicitly so stale Ultralytics user settings cannot redirect
        # runs back to an old checkout path.
        project=str(project_path.resolve()),
        name=args.name,
        workers=args.workers,
        patience=25,
        seed=42,
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
