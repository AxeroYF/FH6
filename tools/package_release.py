import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
STANDARD_SPEC = ROOT / "FH6Auto.spec"
AI_SPEC = ROOT / "FH6Auto-AI.spec"
STANDARD_EXE = DIST_DIR / "FH6Auto.exe"
AI_EXE = DIST_DIR / "FH6Auto-AI.exe"

STANDARD_PYTHON = ROOT / ".packstdvenv" / "Scripts" / "python.exe"
AI_PYTHON = ROOT / ".packaicpuvenv" / "Scripts" / "python.exe"
FALLBACK_PYTHON = Path(r"D:\anaconda\python.exe")


def read_release_version() -> str:
    version_file = ROOT / "version.json"
    if not version_file.exists():
        return "3.0"
    with version_file.open("r", encoding="utf-8-sig") as fh:
        value = json.load(fh).get("version", "3.0")
    return str(value)


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")


def copy_tree(src: Path, dst: Path) -> None:
    require_file(src)
    if dst.exists():
        shutil.rmtree(dst)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(src, dst, ignore=ignore)


def copy_common_files(target: Path) -> None:
    copy_tree(ROOT / "images", target / "images")
    copy_tree(ROOT / "assets", target / "assets")
    for name in ("version.json",):
        shutil.copy2(ROOT / name, target / name)


def copy_current_runtime_state(target: Path) -> None:
    """Package the current settings; runtime cache is generated on first launch."""
    config_file = ROOT / "config.json"
    require_file(config_file)
    shutil.copy2(config_file, target / "config.json")


def clean_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def build_exe(python: Path, spec: Path) -> None:
    if not python.exists():
        python = FALLBACK_PYTHON
    require_file(python)
    require_file(spec)
    subprocess.run(
        [str(python), "-m", "PyInstaller", "--clean", "-y", str(spec)],
        cwd=ROOT,
        check=True,
    )


def package_standard(version: str) -> Path:
    require_file(STANDARD_EXE)
    target = RELEASE_DIR / f"FH6Auto-{version}-Standard"
    clean_path(target)
    target.mkdir(parents=True)
    shutil.copy2(STANDARD_EXE, target / "FH6Auto.exe")
    copy_common_files(target)
    return target


def ai_default_config(*, pure_ai: bool = False) -> dict:
    return {
        "race_count": 99,
        "buy_count": 30,
        "cj_count": 30,
        "chk_1": True,
        "chk_2": True,
        "chk_3": True,
        "route_cj_delete": True,
        "route_delete_race": True,
        "global_loops": 10,
        "skill_dirs": ["right", "up", "up", "up", "left"],
        "share_code": "890169683",
        "auto_restart": False,
        "restart_cmd": "start steam://run/2483190",
        "race_timeout": 300,
        "ai_assist": True,
        "ai_prefer": True,
        "ai_only": pure_ai,
        "ai_auto_capture": False,
        "smart_page": False,
        "ai_model_path": "models/fh6_car_select_yolo.pt",
    }


def package_ai(version: str) -> Path:
    require_file(AI_EXE)
    target = RELEASE_DIR / f"FH6Auto-{version}-AI"
    clean_path(target)
    target.mkdir(parents=True)
    shutil.copy2(AI_EXE, target / "FH6Auto.exe")
    copy_common_files(target)
    copy_tree(ROOT / "models", target / "models")
    with (target / "config.json").open("w", encoding="utf-8") as fh:
        json.dump(ai_default_config(), fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return target


def package_pure_ai(version: str) -> Path:
    require_file(AI_EXE)
    target = RELEASE_DIR / f"FH6Auto-{version}-PureAI"
    clean_path(target)
    target.mkdir(parents=True)
    shutil.copy2(AI_EXE, target / "FH6Auto.exe")
    copy_common_files(target)
    copy_tree(ROOT / "models", target / "models")
    copy_current_runtime_state(target)
    return target


def make_zip(folder: Path) -> Path:
    zip_path = folder.with_suffix(".zip")
    clean_path(zip_path)
    archive = shutil.make_archive(str(folder), "zip", root_dir=folder.parent, base_dir=folder.name)
    return Path(archive)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and package FH6Auto release variants.")
    parser.add_argument(
        "--variant",
        choices=("standard", "ai", "pure-ai", "all"),
        default="all",
        help="release variant to package",
    )
    parser.add_argument("--build", action="store_true", help="run PyInstaller before packaging")
    parser.add_argument("--no-zip", action="store_true", help="skip zip archive creation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = read_release_version()

    if args.build:
        clean_path(BUILD_DIR)
        if args.variant in ("standard", "all"):
            build_exe(STANDARD_PYTHON, STANDARD_SPEC)
        if args.variant in ("ai", "pure-ai", "all"):
            build_exe(AI_PYTHON, AI_SPEC)

    targets = []
    if args.variant in ("standard", "all"):
        targets.append(package_standard(version))
    if args.variant in ("ai", "all"):
        targets.append(package_ai(version))
    if args.variant in ("pure-ai", "all"):
        targets.append(package_pure_ai(version))

    for target in targets:
        print(target)
        if not args.no_zip:
            print(make_zip(target))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
