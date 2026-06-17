from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from generate_bgm_recommendations_md import HERO_MAP_PATH, HERO_TO_SONG, SONGS, choose_default, escape_md


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_PATH = ROOT / "data" / "bgm_authorized_manifest.json"
DEFAULT_MD_PATH = ROOT / "docs" / "bgm_authorized_manifest.md"
RECOMMENDED_MUSIC_DIR = ROOT / "assets" / "music" / "recommended"
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local acquisition manifest from docs/hero_bgm_recommendations.md data. "
            "This script creates search links and local file targets only; it does not download media."
        )
    )
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Manifest JSON output path.")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD_PATH, help="Readable Markdown output path.")
    args = parser.parse_args()

    heroes = json.loads(HERO_MAP_PATH.read_text(encoding="utf-8"))
    tracks = build_tracks(heroes)
    payload = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "docs/hero_bgm_recommendations.md",
        "copyright_note": (
            "This manifest is for organizing music you own, created yourself, received permission to use, "
            "or obtained from a source that explicitly allows offline use. It does not grant rights or "
            "download audio from Bilibili."
        ),
        "naming_contract": {
            "destination_dir": "./assets/music/recommended",
            "accepted_extensions": AUDIO_EXTENSIONS,
            "preferred_filename": "<track_id><extension>, for example ignite.mp3",
        },
        "tracks": tracks,
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    RECOMMENDED_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.md.write_text(render_markdown(payload), encoding="utf-8")

    print(f"Wrote {args.json}")
    print(f"Wrote {args.md}")
    print(f"Unique tracks: {len(tracks)}")


def build_tracks(heroes: dict[str, dict]) -> list[dict]:
    tracks_by_id: dict[str, dict] = {}

    for hero_key, hero in heroes.items():
        song_key = HERO_TO_SONG.get(hero_key) or choose_default(hero.get("tags", []))
        title, artist, vibe = SONGS[song_key]
        record = tracks_by_id.setdefault(
            song_key,
            {
                "id": song_key,
                "title": title,
                "artist": artist,
                "vibe": vibe,
                "local_target_stem": f"./assets/music/recommended/{song_key}",
                "accepted_local_files": [f"./assets/music/recommended/{song_key}{ext}" for ext in AUDIO_EXTENSIONS],
                "bilibili_search_url": build_bilibili_search_url(title, artist),
                "license_status": "needs_user_authorized_local_file",
                "heroes": [],
            },
        )
        record["heroes"].append(
            {
                "hero_key": hero_key,
                "display_name": hero.get("display_name", hero_key),
                "english_name": hero.get("english_name", hero_key),
            }
        )

    return sorted(tracks_by_id.values(), key=lambda track: (-len(track["heroes"]), track["id"]))


def build_bilibili_search_url(title: str, artist: str) -> str:
    query = re.sub(r"\s+", " ", f"{title} {artist}".strip())
    return f"https://search.bilibili.com/all?keyword={quote_plus(query)}"


def render_markdown(payload: dict) -> str:
    lines = [
        "# BGM 授权音频整理清单",
        "",
        f"- 生成时间：{payload['generated_at']}",
        "- 用途：把推荐表里的重复曲目合并成唯一曲目清单，方便你整理已购买、已授权、原创或平台明确允许离线使用的音频文件。",
        "- 说明：这里提供 B 站搜索入口和本地目标文件名，不抓取、不下载、不绕过平台限制。",
        "",
        "## 文件命名",
        "",
        "把音频放到 `assets/music/recommended/`，文件名优先用 `曲目 ID + 扩展名`，例如 `ignite.mp3`。",
        "",
        "| # | 曲目 ID | 推荐曲 | 歌手 | 英雄数 | 本地目标 | B 站搜索 |",
        "|---:|---|---|---|---:|---|---|",
    ]

    for index, track in enumerate(payload["tracks"], start=1):
        first_target = track["accepted_local_files"][0]
        lines.append(
            "| {index} | `{track_id}` | {title} | {artist} | {hero_count} | `{target}` | [搜索]({url}) |".format(
                index=index,
                track_id=escape_md(track["id"]),
                title=escape_md(track["title"]),
                artist=escape_md(track["artist"]),
                hero_count=len(track["heroes"]),
                target=escape_md(first_target),
                url=track["bilibili_search_url"],
            )
        )

    lines.extend(
        [
            "",
            "## 接入步骤",
            "",
            "1. 从你有权使用的来源取得音频文件。",
            "2. 按上表曲目 ID 放到 `assets/music/recommended/`。",
            "3. 运行 `python utils/apply_authorized_bgm_manifest.py` 生成 `data/hero_music_map.authorized.json`。",
            "4. 确认无误后，再决定是否用它替换 `data/hero_music_map.json`。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
