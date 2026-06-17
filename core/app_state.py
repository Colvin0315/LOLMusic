from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_scan": True,
    "auto_bili": True,
    "volume": 58,
    "ui_size": "medium",
}


class AppStateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._payload = self._load()

    @property
    def favorites(self) -> set[str]:
        raw = self._payload.get("favorites")
        if not isinstance(raw, list):
            return set()
        return {str(item).lower() for item in raw if str(item).strip()}

    @property
    def settings(self) -> dict[str, Any]:
        raw = self._payload.get("settings")
        settings = dict(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            settings.update(raw)
        return settings

    def update(self, favorites: set[str], settings: dict[str, Any]) -> None:
        self._payload = {
            "version": 1,
            "favorites": sorted(favorites),
            "settings": {**DEFAULT_SETTINGS, **settings},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        fallback = {"version": 1, "favorites": [], "settings": dict(DEFAULT_SETTINGS)}
        if not self.path.exists():
            return fallback
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback
        return payload if isinstance(payload, dict) else fallback
