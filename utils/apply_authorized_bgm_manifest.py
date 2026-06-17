from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "data" / "bgm_authorized_manifest.json"
DEFAULT_HERO_MAP_PATH = ROOT / "data" / "hero_music_map.json"
DEFAULT_OUTPUT_MAP_PATH = ROOT / "data" / "hero_music_map.authorized.json"
DEFAULT_DESTINATION_DIR = ROOT / "assets" / "music" / "recommended"
SUPPORTED_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Wire user-provided authorized local audio files into a generated hero music map. "
            "This script copies local files only; it does not download from Bilibili or any other site."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--hero-map", type=Path, default=DEFAULT_HERO_MAP_PATH)
    parser.add_argument("--output-map", type=Path, default=DEFAULT_OUTPUT_MAP_PATH)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_DESTINATION_DIR,
        help="Directory containing authorized audio files. Filenames should start with the track ID.",
    )
    parser.add_argument(
        "--destination-dir",
        type=Path,
        default=DEFAULT_DESTINATION_DIR,
        help="Directory where matched audio files are stored for the app.",
    )
    parser.add_argument(
        "--replace-tracks",
        action="store_true",
        help="Replace each matched hero's track list instead of prepending the authorized track.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    hero_map = json.loads(args.hero_map.read_text(encoding="utf-8"))
    source_dir = args.source_dir.expanduser().resolve()
    destination_dir = args.destination_dir.expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)

    available_files = index_audio_files(source_dir)
    matched: dict[str, Path] = {}
    missing: list[str] = []

    for track in manifest["tracks"]:
        source = find_track_file(track, available_files)
        if source is None:
            missing.append(track["id"])
            continue
        destination = destination_dir / f"{track['id']}{source.suffix.lower()}"
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        matched[track["id"]] = destination

    hero_to_track = {
        hero["hero_key"]: track
        for track in manifest["tracks"]
        if track["id"] in matched
        for hero in track["heroes"]
    }

    wired_heroes = 0
    for hero_key, track in hero_to_track.items():
        if hero_key not in hero_map:
            continue
        audio_path = matched[track["id"]]
        authorized_track = {
            "name": track["title"],
            "artist": track["artist"],
            "path": "./" + audio_path.relative_to(ROOT).as_posix(),
            "weight": 10,
            "license": "user-provided-authorized-local-file",
        }
        if args.replace_tracks:
            hero_map[hero_key]["tracks"] = [authorized_track]
        else:
            existing = [
                item
                for item in hero_map[hero_key].get("tracks", [])
                if str(item.get("path", "")) != authorized_track["path"]
            ]
            hero_map[hero_key]["tracks"] = [authorized_track, *existing][:5]
        wired_heroes += 1

    args.output_map.parent.mkdir(parents=True, exist_ok=True)
    args.output_map.write_text(json.dumps(hero_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Matched tracks: {len(matched)}")
    print(f"Wired heroes: {wired_heroes}")
    print(f"Wrote {args.output_map}")
    if missing:
        print(f"Missing authorized files: {len(missing)}")
        print("First missing IDs: " + ", ".join(missing[:20]))


def index_audio_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def find_track_file(track: dict[str, Any], files: list[Path]) -> Path | None:
    track_id = normalize_key(track["id"])
    title_key = normalize_key(track["title"])
    artist_key = normalize_key(str(track["artist"]).split("/")[0])

    for path in files:
        stem_key = normalize_key(path.stem)
        if stem_key == track_id or stem_key.startswith(f"{track_id}_") or stem_key.startswith(f"{track_id}-"):
            return path

    for path in files:
        stem_key = normalize_key(path.stem)
        if title_key and title_key in stem_key and (not artist_key or artist_key in stem_key):
            return path

    return None


def normalize_key(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", value).strip("_").lower()


if __name__ == "__main__":
    main()
