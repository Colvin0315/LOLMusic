from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO_MAP_PATH = ROOT / "data" / "hero_music_map.json"
MUSIC_DIR = ROOT / "assets" / "music"
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import licensed local music files for one Rift BGM hero.")
    parser.add_argument("hero_key", help="Hero key in data/hero_music_map.json, for example yasuo or lee_sin.")
    parser.add_argument("files", nargs="+", help="Local audio files to import. Up to 5 tracks are used.")
    parser.add_argument("--artist", default="Local Library", help="Artist value written to hero_music_map.json.")
    args = parser.parse_args()

    payload = json.loads(HERO_MAP_PATH.read_text(encoding="utf-8"))
    hero_key = args.hero_key.lower()
    if hero_key not in payload:
        raise SystemExit(f"Unknown hero key: {hero_key}")

    destination_dir = MUSIC_DIR / hero_key
    destination_dir.mkdir(parents=True, exist_ok=True)

    tracks = []
    for index, raw_file in enumerate(args.files[:5], start=1):
        source = Path(raw_file).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"File not found: {source}")
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise SystemExit(f"Unsupported audio type: {source.suffix}")

        destination = destination_dir / f"{index:02d}_{safe_name(source.stem)}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        tracks.append(
            {
                "name": source.stem,
                "artist": args.artist,
                "path": "./" + destination.relative_to(ROOT).as_posix(),
                "weight": max(1, 6 - index),
            }
        )

    payload[hero_key]["tracks"] = tracks
    HERO_MAP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(tracks)} tracks for {hero_key}.")


def safe_name(value: str) -> str:
    allowed = []
    for char in value.strip().lower().replace(" ", "_"):
        if char.isalnum() or char in {"_", "-"}:
            allowed.append(char)
    return "".join(allowed) or "track"


if __name__ == "__main__":
    main()
