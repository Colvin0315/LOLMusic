from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_DATA_DIR_NAME = "RiftBGM"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return app_dir()


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    return resource_root().joinpath(*map(Path, parts))


def user_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DATA_DIR_NAME
    return app_dir() / "user_data"


def user_data_path(*parts: str | os.PathLike[str]) -> Path:
    return user_data_root().joinpath(*map(Path, parts))


def ensure_user_resource(relative_path: str | os.PathLike[str]) -> Path:
    relative = Path(relative_path)
    target = user_data_path(relative)
    if target.exists():
        return target

    source = resource_path(relative)
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return target
