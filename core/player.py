from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from core.music_manager import Track


class AudioPlayer(QObject):
    track_changed = Signal(object)
    playback_state_changed = Signal(bool)
    position_changed = Signal(int, int)
    error_occurred = Signal(str)
    track_finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._players = [QMediaPlayer(self), QMediaPlayer(self)]
        self._outputs = [QAudioOutput(self), QAudioOutput(self)]
        self._active_index: int | None = None
        self._current_track: Track | None = None
        self._volume = 0.58
        self._fade_ms = 1500
        self._fade_elapsed = 0
        self._fade_from: int | None = None
        self._fade_to: int | None = None

        for index, (player, output) in enumerate(zip(self._players, self._outputs, strict=True)):
            player.setAudioOutput(output)
            output.setVolume(0.0)
            player.positionChanged.connect(lambda value, i=index: self._on_position_changed(i, value))
            player.durationChanged.connect(lambda value, i=index: self._on_duration_changed(i, value))
            player.mediaStatusChanged.connect(lambda status, i=index: self._on_media_status_changed(i, status))
            player.errorOccurred.connect(lambda _error, message, i=index: self._on_error(i, message))

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(50)
        self._fade_timer.timeout.connect(self._tick_crossfade)

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    @property
    def is_playing(self) -> bool:
        player = self._active_player()
        return player is not None and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def play(self, track: Track) -> None:
        if not Path(track.path).exists():
            self.error_occurred.emit(f"音频文件不存在：{track.path}")
            return

        self._play_source(track, QUrl.fromLocalFile(str(track.path)))

    def play_remote(self, track: Track, url: str) -> None:
        self._play_source(track, QUrl(url))

    def _play_source(self, track: Track, source: QUrl) -> None:
        self._current_track = track
        next_index = 0 if self._active_index is None else 1 - self._active_index
        next_player = self._players[next_index]
        next_output = self._outputs[next_index]

        next_player.stop()
        next_player.setSource(source)
        next_output.setVolume(0.0 if self._active_index is not None else self._volume)
        next_player.play()

        if self._active_index is None:
            self._active_index = next_index
            self.playback_state_changed.emit(True)
        else:
            self._fade_from = self._active_index
            self._fade_to = next_index
            self._fade_elapsed = 0
            self._fade_timer.start()
            self._active_index = next_index

        self.track_changed.emit(track)

    def toggle_pause(self) -> None:
        player = self._active_player()
        if player is None:
            return

        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
            self.playback_state_changed.emit(False)
        else:
            player.play()
            self.playback_state_changed.emit(True)

    def pause(self) -> None:
        player = self._active_player()
        if player is not None:
            player.pause()
            self.playback_state_changed.emit(False)

    def stop(self) -> None:
        self._fade_timer.stop()
        for player, output in zip(self._players, self._outputs, strict=True):
            player.stop()
            output.setVolume(0.0)
        self._active_index = None
        self._current_track = None
        self.playback_state_changed.emit(False)

    def set_volume(self, value: int) -> None:
        self._volume = max(0.0, min(1.0, value / 100))
        if self._active_index is not None and not self._fade_timer.isActive():
            self._outputs[self._active_index].setVolume(self._volume)

    def _tick_crossfade(self) -> None:
        if self._fade_from is None or self._fade_to is None:
            self._fade_timer.stop()
            return

        self._fade_elapsed += self._fade_timer.interval()
        progress = min(1.0, self._fade_elapsed / self._fade_ms)
        self._outputs[self._fade_from].setVolume(self._volume * (1.0 - progress))
        self._outputs[self._fade_to].setVolume(self._volume * progress)

        if progress >= 1.0:
            self._players[self._fade_from].stop()
            self._outputs[self._fade_from].setVolume(0.0)
            self._outputs[self._fade_to].setVolume(self._volume)
            self._fade_from = None
            self._fade_to = None
            self._fade_timer.stop()
            self.playback_state_changed.emit(True)

    def _active_player(self) -> QMediaPlayer | None:
        if self._active_index is None:
            return None
        return self._players[self._active_index]

    def _on_position_changed(self, index: int, position: int) -> None:
        if index == self._active_index:
            self.position_changed.emit(position, self._players[index].duration())

    def _on_duration_changed(self, index: int, duration: int) -> None:
        if index == self._active_index:
            self.position_changed.emit(self._players[index].position(), duration)

    def _on_media_status_changed(self, index: int, status: QMediaPlayer.MediaStatus) -> None:
        if index == self._active_index and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.track_finished.emit()

    def _on_error(self, index: int, message: str) -> None:
        if index == self._active_index and message:
            self.error_occurred.emit(message)
