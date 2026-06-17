from __future__ import annotations

import json
import re
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HERO_MAP_PATH = DATA_DIR / "hero_music_map.json"
CHAMPION_ID_MAP_PATH = DATA_DIR / "champion_id_map.json"
META_PATH = DATA_DIR / "champion_data_meta.json"

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"
PLACEHOLDER_TRACKS = [
    {
        "name": "Rift Pulse",
        "artist": "Rift BGM",
        "path": "./assets/music/common/rift_pulse.wav",
        "weight": 3,
        "license": "local-generated-placeholder",
    },
    {
        "name": "Night Drive Cut",
        "artist": "Rift BGM",
        "path": "./assets/music/common/night_drive_cut.wav",
        "weight": 2,
        "license": "local-generated-placeholder",
    },
    {
        "name": "Battle Edit",
        "artist": "Rift BGM",
        "path": "./assets/music/common/battle_edit.wav",
        "weight": 2,
        "license": "local-generated-placeholder",
    },
    {
        "name": "Lonely Highlight",
        "artist": "Rift BGM",
        "path": "./assets/music/common/lonely_highlight.wav",
        "weight": 1.5,
        "license": "local-generated-placeholder",
    },
    {
        "name": "Final Lock In",
        "artist": "Rift BGM",
        "path": "./assets/music/common/final_lock_in.wav",
        "weight": 1.5,
        "license": "local-generated-placeholder",
    },
]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    version = fetch_json(f"{DDRAGON_BASE}/api/versions.json")[0]
    zh_payload = fetch_json(f"{DDRAGON_BASE}/cdn/{version}/data/zh_CN/champion.json")
    en_payload = fetch_json(f"{DDRAGON_BASE}/cdn/{version}/data/en_US/champion.json")
    old_map = load_json(HERO_MAP_PATH, {})

    hero_map: dict[str, dict[str, Any]] = {}
    champion_id_map: dict[str, str] = {}

    for champion_id in sorted(en_payload["data"], key=lambda value: int(en_payload["data"][value]["key"])):
        en = en_payload["data"][champion_id]
        zh = zh_payload["data"].get(champion_id, en)
        hero_key = to_snake_case(champion_id)
        previous = old_map.get(hero_key, {})

        champion_numeric_id = int(en["key"])
        champion_id_map[str(champion_numeric_id)] = hero_key

        display_name = build_display_name(str(zh.get("name", en["name"])), str(zh.get("title", "")))
        aliases = merge_unique(
            [
                str(zh.get("name", "")),
                str(zh.get("title", "")),
                str(en.get("name", "")),
                champion_id,
                hero_key,
                hero_key.replace("_", " "),
            ],
            previous.get("aliases", []),
        )

        tags = merge_unique([str(tag).lower() for tag in en.get("tags", [])], previous.get("tags", []))
        tracks = build_tracks(hero_key, previous.get("tracks", []))

        hero_map[hero_key] = {
            "champion_id": champion_numeric_id,
            "riot_id": champion_id,
            "display_name": display_name,
            "english_name": str(en.get("name", champion_id)),
            "aliases": aliases,
            "tags": tags,
            "tracks": tracks,
        }

    HERO_MAP_PATH.write_text(json.dumps(hero_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CHAMPION_ID_MAP_PATH.write_text(json.dumps(champion_id_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    META_PATH.write_text(
        json.dumps(
            {
                "source": "Riot Data Dragon",
                "version": version,
                "champion_count": len(hero_map),
                "note": "Tracks are local generated placeholders. Replace them with music you own or have licensed.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Generated {len(hero_map)} champions from Data Dragon {version}.")
    print(f"Wrote {HERO_MAP_PATH}")
    print(f"Wrote {CHAMPION_ID_MAP_PATH}")


def fetch_json(url: str) -> Any:
    context = ssl._create_unverified_context()
    request = Request(url, headers={"User-Agent": "Rift-BGM/1.0"})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=20, context=context) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def to_snake_case(value: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return value.lower()


def build_display_name(name: str, title: str) -> str:
    name = name.strip()
    title = title.strip()
    if not title:
        return name
    return f"{name} {title}"


def build_tracks(hero_key: str, previous_tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for track in previous_tracks:
        path = str(track.get("path", "")).strip()
        if not path:
            continue
        tracks.append(
            {
                "name": str(track.get("name") or Path(path).stem),
                "artist": str(track.get("artist") or "Rift BGM"),
                "path": path,
                "weight": float(track.get("weight", 1)),
            }
        )
        if len(tracks) >= 5:
            return tracks[:5]

    used_paths = {str(track["path"]) for track in tracks}
    for template in PLACEHOLDER_TRACKS:
        if str(template["path"]) in used_paths:
            continue
        track = dict(template)
        track["name"] = f"{track['name']} - {hero_key.replace('_', ' ').title()}"
        tracks.append(track)
        if len(tracks) >= 5:
            break

    return tracks


def merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for value in [*primary, *secondary]:
        text = str(value).strip()
        key = normalize(text)
        if not text or key in seen:
            continue
        seen.add(key)
        values.append(text)
    return values


def normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()


if __name__ == "__main__":
    main()
