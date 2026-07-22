import os
import shutil
import sys


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_internal_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return get_app_dir()


APP_DIR = get_app_dir()
INTERNAL_DIR = get_internal_dir()
CONFIG_DIR = os.path.join(APP_DIR, "config")
USER_CONFIG_FILE = os.path.join(APP_DIR, "config.json")
LOG_FILE = os.path.join(APP_DIR, "bot_log.txt")
CACHE_DIR = os.path.join(APP_DIR, "cache")
TEMPLATE_CACHE_FILE = os.path.join(CACHE_DIR, "template_cache.pkl")
TEMPLATE_META_FILE = os.path.join(CACHE_DIR, "template_meta.json")
CURRENT_VERSION = "4.4"
DEFAULT_IMAGES_DIRNAME = "1080p"


def get_images_dir(base_dir):
    profiled_dir = os.path.join(base_dir, "images", DEFAULT_IMAGES_DIRNAME)
    if os.path.isdir(profiled_dir):
        return profiled_dir

    legacy_dir = os.path.join(base_dir, "images")
    if os.path.isdir(legacy_dir):
        return legacy_dir

    return None


def auto_extract_configs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    old_configs = [
        os.path.join(APP_DIR, "bot_config.json"),
        os.path.join(APP_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot-config.json"),
        os.path.join(CONFIG_DIR, "bot_config.json"),
        os.path.join(CONFIG_DIR, "config.json"),
    ]
    for old_path in old_configs:
        if os.path.exists(old_path):
            try:
                if not os.path.exists(USER_CONFIG_FILE):
                    shutil.move(old_path, USER_CONFIG_FILE)
                else:
                    os.remove(old_path)
            except Exception:
                pass


def auto_extract_images(folder_name="images"):
    internal_dir = os.path.join(INTERNAL_DIR, folder_name)
    external_dir = os.path.join(APP_DIR, folder_name)

    if not os.path.isdir(internal_dir):
        print(f"[auto_extract_images] missing internal directory: {internal_dir}")
        return

    try:
        os.makedirs(external_dir, exist_ok=True)
        target_base = os.path.join(external_dir, DEFAULT_IMAGES_DIRNAME)
        os.makedirs(target_base, exist_ok=True)

        for root, _, files in os.walk(internal_dir):
            rel_path = os.path.relpath(root, internal_dir)
            if rel_path == ".":
                rel_path = ""
            if rel_path.startswith(f"{DEFAULT_IMAGES_DIRNAME}{os.sep}") or rel_path == DEFAULT_IMAGES_DIRNAME:
                rel_child = rel_path[len(DEFAULT_IMAGES_DIRNAME):].lstrip("\\/")
            else:
                rel_child = rel_path

            target_root = target_base if not rel_child else os.path.join(target_base, rel_child)
            os.makedirs(target_root, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_root, file)
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
    except Exception as e:
        print(f"[auto_extract_images] extract failed: {e}")


def get_img_path(filename):
    rel_name = os.path.normpath(str(filename))
    basename = os.path.basename(rel_name)
    cache = getattr(get_img_path, "_cache", None)
    if cache is None:
        cache = {}
        setattr(get_img_path, "_cache", cache)
    if rel_name in cache:
        return cache[rel_name]

    if os.path.isabs(rel_name) and os.path.exists(rel_name):
        cache[rel_name] = rel_name
        return rel_name

    for candidate_name in (rel_name, basename):
        ext_path = os.path.join(APP_DIR, "images", DEFAULT_IMAGES_DIRNAME, candidate_name)
        if os.path.exists(ext_path):
            cache[rel_name] = ext_path
            return ext_path

        int_path = os.path.join(INTERNAL_DIR, "images", DEFAULT_IMAGES_DIRNAME, candidate_name)
        if os.path.exists(int_path):
            cache[rel_name] = int_path
            return int_path

        ext_legacy = os.path.join(APP_DIR, "images", candidate_name)
        if os.path.exists(ext_legacy):
            cache[rel_name] = ext_legacy
            return ext_legacy

        int_legacy = os.path.join(INTERNAL_DIR, "images", candidate_name)
        if os.path.exists(int_legacy):
            cache[rel_name] = int_legacy
            return int_legacy

    cache[rel_name] = filename
    return filename


def get_asset_path(*parts):
    asset_path = os.path.join(INTERNAL_DIR, "assets", *parts)
    if os.path.exists(asset_path):
        return asset_path

    dev_asset_path = os.path.join(get_app_dir(), "assets", *parts)
    if os.path.exists(dev_asset_path):
        return dev_asset_path

    return None
