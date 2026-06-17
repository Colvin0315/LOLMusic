from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.bilibili import BilibiliClient, BilibiliError
from core.music_manager import HeroMusic


class BilibiliSearchSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)


class BilibiliHeroSearchTask(QRunnable):
    def __init__(self, client: BilibiliClient, hero: HeroMusic, limit: int = 5) -> None:
        super().__init__()
        self.client = client
        self.hero = hero
        self.limit = limit
        self.signals = BilibiliSearchSignals()

    @Slot()
    def run(self) -> None:
        try:
            videos = self.client.search_hero_bgm(self.hero, limit=self.limit)
            resolved = self.client.resolve_first_playable_audio(videos)
            self.signals.finished.emit((self.hero.key, videos, resolved))
        except BilibiliError as exc:
            self.signals.failed.emit((self.hero.key, str(exc)))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit((self.hero.key, f"B站搜索失败：{exc}"))
