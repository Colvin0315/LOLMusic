from __future__ import annotations

import json
import math
import random
import re
import struct
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Track:
    name: str
    path: Path
    artist: str
    weight: float
    hero_key: str
    hero_name: str


@dataclass(frozen=True)
class HeroMusic:
    key: str
    display_name: str
    english_name: str
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    tracks: tuple[Track, ...]


class MusicManager:
    def __init__(self, data_file: Path | str) -> None:
        self.data_file = Path(data_file)
        self.project_root = self.data_file.parent.parent
        self.heroes: dict[str, HeroMusic] = {}
        self.champion_id_to_key: dict[int, str] = {}
        self.load()

    def load(self) -> None:
        if not self.data_file.exists():
            self.heroes = {}
            return

        with self.data_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        heroes: dict[str, HeroMusic] = {}
        champion_id_to_key: dict[int, str] = {}
        for key, raw in payload.items():
            hero_key = str(key).lower()
            display_name = raw.get("display_name") or raw.get("name") or key.title()
            english_name = raw.get("english_name") or key.title()
            tags = tuple(str(tag) for tag in raw.get("tags", ()))
            aliases = self._build_aliases(hero_key, display_name, english_name, raw.get("aliases", ()))

            tracks = []
            for raw_track in raw.get("tracks", ()):
                track_path = self._resolve_track_path(raw_track.get("path", ""))
                tracks.append(
                    Track(
                        name=str(raw_track.get("name") or track_path.stem),
                        path=track_path,
                        artist=str(raw_track.get("artist") or "Rift BGM"),
                        weight=float(raw_track.get("weight", 1)),
                        hero_key=hero_key,
                        hero_name=display_name,
                    )
                )

            heroes[hero_key] = HeroMusic(
                key=hero_key,
                display_name=display_name,
                english_name=english_name,
                tags=tags,
                aliases=aliases,
                tracks=tuple(tracks),
            )

            champion_id = raw.get("champion_id")
            if champion_id is not None:
                champion_id_to_key[int(champion_id)] = hero_key

        champion_id_to_key.update(self._load_champion_id_map())
        self.heroes = heroes
        self.champion_id_to_key = champion_id_to_key

    def ensure_demo_audio_assets(self) -> None:
        """Create short local WAV placeholders so the app can play immediately."""
        frequency = 196
        seen_paths: set[Path] = set()
        for index, track in enumerate(self.all_tracks()):
            if track.path in seen_paths:
                continue
            seen_paths.add(track.path)
            if track.path.exists() or track.path.suffix.lower() != ".wav":
                continue
            try:
                track.path.parent.mkdir(parents=True, exist_ok=True)
                self._write_demo_wav(track.path, frequency + index * 37)
            except OSError:
                continue

    def all_tracks(self) -> list[Track]:
        return [track for hero in self.heroes.values() for track in hero.tracks]

    def list_heroes(self) -> list[HeroMusic]:
        return list(self.heroes.values())

    def get_hero(self, hero_key: str) -> HeroMusic | None:
        return self.heroes.get(hero_key.lower())

    def get_hero_by_champion_id(self, champion_id: int) -> HeroMusic | None:
        hero_key = self.champion_id_to_key.get(int(champion_id))
        if hero_key is None:
            return None
        return self.get_hero(hero_key)

    def choose_track(self, hero_key: str, exclude: Path | None = None) -> Track | None:
        hero = self.get_hero(hero_key)
        if hero is None or not hero.tracks:
            return None

        candidates = list(hero.tracks)
        if exclude is not None and len(candidates) > 1:
            candidates = [track for track in candidates if track.path != exclude] or candidates

        weights = [max(0.01, track.weight) for track in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def recommendations(self, limit: int = 4) -> list[Track]:
        tracks = self.all_tracks()
        return tracks[:limit]

    def match_hero(self, text: str, min_score: float = 0.72) -> tuple[HeroMusic, float] | None:
        normalized = self._normalize(text)
        if not normalized:
            return None

        tokens = [self._normalize(token) for token in re.split(r"[\s,，。:：;；|/\\\-_\n\r]+", text)]
        tokens = [token for token in tokens if token]

        best: tuple[HeroMusic, float] | None = None
        for hero in self.heroes.values():
            for alias in hero.aliases:
                score = self._score_alias(self._normalize(alias), normalized, tokens)
                if best is None or score > best[1]:
                    best = (hero, score)

        if best and best[1] >= min_score:
            return best
        return None

    def _resolve_track_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _load_champion_id_map(self) -> dict[int, str]:
        path = self.data_file.with_name("champion_id_map.json")
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        return {int(champion_id): str(hero_key).lower() for champion_id, hero_key in payload.items()}

    def _build_aliases(
        self, key: str, display_name: str, english_name: str, aliases: list[str] | tuple[str, ...]
    ) -> tuple[str, ...]:
        values = [key, key.replace("_", " "), display_name, english_name, *aliases]
        unique: list[str] = []
        seen = set()
        for value in values:
            text = str(value).strip()
            normalized = self._normalize(text)
            if text and normalized not in seen:
                unique.append(text)
                seen.add(normalized)
        return tuple(unique)

    def _score_alias(self, alias: str, text: str, tokens: list[str]) -> float:
        if not alias:
            return 0.0
        if alias in text:
            return 1.0

        candidates = tokens + [text]
        if len(text) > len(alias) * 2:
            width = max(len(alias), 2)
            step = max(1, width // 2)
            candidates.extend(text[start : start + width] for start in range(0, len(text) - width + 1, step))

        return max(SequenceMatcher(None, alias, candidate).ratio() for candidate in candidates if candidate)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()

    @staticmethod
    def _write_demo_wav(path: Path, frequency: int) -> None:
        sample_rate = 44_100
        duration_seconds = 16
        amplitude = 0.22
        fade_samples = int(sample_rate * 0.35)
        total_samples = sample_rate * duration_seconds

        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            frames = bytearray()
            for index in range(total_samples):
                t = index / sample_rate
                envelope = 1.0
                if index < fade_samples:
                    envelope = index / fade_samples
                elif index > total_samples - fade_samples:
                    envelope = (total_samples - index) / fade_samples

                beat = 0.72 + 0.28 * math.sin(2 * math.pi * 2.0 * t)
                lead = math.sin(2 * math.pi * frequency * t)
                sub = math.sin(2 * math.pi * (frequency / 2) * t) * 0.45
                harmony = math.sin(2 * math.pi * (frequency * 1.5) * t) * 0.18
                sample = int(32767 * amplitude * envelope * beat * (lead + sub + harmony))
                frames.extend(struct.pack("<hh", sample, sample))

            wav_file.writeframes(frames)
