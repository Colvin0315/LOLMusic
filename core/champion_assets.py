from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DDRAGON_CDN = "https://ddragon.leagueoflegends.com/cdn"
DDRAGON_VERSION_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DEFAULT_DDRAGON_VERSION = "15.11.1"


@dataclass(frozen=True)
class ChampionAssetPaths:
    icon: Path | None
    splash: Path | None


class ChampionAssetManager:
    def __init__(self, hero_data_file: Path | str, cache_dir: Path | str) -> None:
        self.hero_data_file = Path(hero_data_file)
        self.cache_dir = Path(cache_dir)
        self.icon_dir = self.cache_dir / "icons"
        self.splash_dir = self.cache_dir / "splashes"
        self.version_file = self.cache_dir / "ddragon_version.txt"
        self._riot_ids = self._load_riot_ids()
        self._version: str | None = None

    def riot_id(self, hero_key: str) -> str:
        return self._riot_ids.get(hero_key.lower(), "")

    def icon_path(self, hero_key: str, ensure: bool = True) -> Path | None:
        riot_id = self.riot_id(hero_key)
        if not riot_id:
            return None
        path = self.icon_dir / f"{riot_id}.png"
        if ensure:
            self._ensure_download(path, self._icon_url(riot_id))
        return path if path.exists() else None

    def splash_path(self, hero_key: str, ensure: bool = True) -> Path | None:
        riot_id = self.riot_id(hero_key)
        if not riot_id:
            return None
        path = self.splash_dir / f"{riot_id}_0.jpg"
        if ensure:
            self._ensure_download(path, self._splash_url(riot_id))
        return path if path.exists() else None

    def paths(self, hero_key: str, ensure: bool = True) -> ChampionAssetPaths:
        return ChampionAssetPaths(
            icon=self.icon_path(hero_key, ensure=ensure),
            splash=self.splash_path(hero_key, ensure=ensure),
        )

    def _load_riot_ids(self) -> dict[str, str]:
        try:
            payload = json.loads(self.hero_data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        riot_ids: dict[str, str] = {}
        if not isinstance(payload, dict):
            return riot_ids
        for key, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            riot_id = str(raw.get("riot_id") or raw.get("english_name") or key.title()).strip()
            if riot_id:
                riot_ids[str(key).lower()] = riot_id
        return riot_ids

    def _version_or_default(self) -> str:
        if self._version:
            return self._version

        try:
            with urllib.request.urlopen(DDRAGON_VERSION_URL, timeout=2.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list) and payload:
                self._version = str(payload[0])
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.version_file.write_text(self._version, encoding="utf-8")
                return self._version
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass

        try:
            cached = self.version_file.read_text(encoding="utf-8").strip()
        except OSError:
            cached = ""
        self._version = cached or DEFAULT_DDRAGON_VERSION
        return self._version

    def _icon_url(self, riot_id: str) -> str:
        return f"{DDRAGON_CDN}/{self._version_or_default()}/img/champion/{riot_id}.png"

    @staticmethod
    def _splash_url(riot_id: str) -> str:
        return f"{DDRAGON_CDN}/img/champion/splash/{riot_id}_0.jpg"

    def _ensure_download(self, path: Path, url: str) -> None:
        if path.exists() and path.stat().st_size > 0:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        request = urllib.request.Request(url, headers={"User-Agent": "RiftBGM/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                data = response.read()
            if data:
                temp_path.write_bytes(data)
                temp_path.replace(path)
        except (OSError, urllib.error.URLError):
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
