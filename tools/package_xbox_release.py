"""Build the standalone Xbox test package without touching the Steam package."""

import argparse
import shutil
import subprocess
from pathlib import Path

from package_release import (
    AI_PYTHON,
    FALLBACK_PYTHON,
    RELEASE_DIR,
    ROOT,
    clean_path,
    copy_common_files,
    copy_current_runtime_state,
    copy_tree,
    make_zip,
    read_release_version,
    require_file,
)


XBOX_SPEC = ROOT / "FH6Auto-Xbox.spec"
XBOX_EXE = ROOT / "dist" / "FH6Auto-Xbox.exe"


def build_xbox_exe():
    python = AI_PYTHON if AI_PYTHON.exists() else FALLBACK_PYTHON
    require_file(python)
    require_file(XBOX_SPEC)
    subprocess.run(
        [str(python), "-m", "PyInstaller", "--clean", "-y", str(XBOX_SPEC)],
        cwd=ROOT,
        check=True,
    )


def package_xbox(version):
    require_file(XBOX_EXE)
    target = RELEASE_DIR / f"FH6Auto-{version}-Xbox-PureAI"
    clean_path(target)
    target.mkdir(parents=True)
    shutil.copy2(XBOX_EXE, target / "FH6Auto-Xbox.exe")
    copy_common_files(target)
    shutil.copy2(ROOT / "XBOX-TEST.md", target / "XBOX-TEST.md")
    copy_tree(ROOT / "models", target / "models")
    copy_current_runtime_state(target)
    return target


def main():
    parser = argparse.ArgumentParser(description="Build the Xbox FH6Auto test release.")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()

    if args.build:
        build_xbox_exe()
    target = package_xbox(read_release_version())
    print(target)
    if not args.no_zip:
        print(make_zip(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
