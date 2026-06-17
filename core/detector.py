from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from core.lcu_client import LcuClient, LcuUnavailableError
from core.music_manager import HeroMusic, MusicManager


@dataclass(frozen=True)
class DetectionResult:
    hero: HeroMusic | None
    confidence: float
    raw_text: str
    status: str
    source: str = "ocr"


class HeroDetector:
    def __init__(self, music_manager: MusicManager, use_ocr: bool = True, use_lcu: bool = True) -> None:
        self.music_manager = music_manager
        self.use_ocr = use_ocr
        self.use_lcu = use_lcu
        self.lcu_client = LcuClient()
        self._reader: Any | None = None
        self._ocr_error: str | None = None

    @property
    def ocr_available(self) -> bool:
        return self._get_reader() is not None

    def detect_text(self, text: str, source: str = "text") -> DetectionResult:
        match = self.music_manager.match_hero(text)
        if match is None:
            return DetectionResult(None, 0.0, text, "未匹配到英雄", source)
        hero, confidence = match
        return DetectionResult(hero, confidence, text, "识别成功", source)

    def detect_lcu(self) -> DetectionResult:
        if not self.use_lcu:
            return DetectionResult(None, 0.0, "", "LCU 已关闭", "lcu-disabled")

        try:
            selection = self.lcu_client.get_current_selection()
        except LcuUnavailableError as exc:
            return DetectionResult(None, 0.0, "", f"LCU 未连接：{exc}", "lcu-unavailable")

        if selection is None:
            phase = "Unknown"
            try:
                phase = self.lcu_client.get_gameflow_phase() or phase
            except LcuUnavailableError:
                pass
            return DetectionResult(None, 0.0, phase, f"LCU 已连接，当前阶段 {phase}，等待进入选人或选择英雄", "lcu-waiting")

        hero = self.music_manager.get_hero_by_champion_id(selection.champion_id) if selection.champion_id else None
        if hero is None and selection.champion_name:
            match = self.music_manager.match_hero(selection.champion_name)
            hero = match[0] if match is not None else None

        if hero is None:
            raw_value = selection.champion_name or str(selection.champion_id)
            return DetectionResult(
                None,
                0.0,
                raw_value,
                f"LCU 识别到英雄 {raw_value}，但音乐库未配置",
                "lcu-unmapped",
            )

        status = "LCU 识别成功" if selection.is_locked else "LCU 识别到预选英雄"
        raw_text = selection.champion_name or str(selection.champion_id)
        return DetectionResult(hero, 1.0 if selection.is_locked else 0.92, raw_text, status, "lcu")

    def detect(self, image: QImage | None = None) -> DetectionResult:
        lcu_result = self.detect_lcu()
        if lcu_result.hero is not None:
            return lcu_result

        if lcu_result.source in {"lcu-waiting", "lcu-unmapped", "lcu-disabled"}:
            return lcu_result

        if image is None:
            return lcu_result

        ocr_result = self.detect_qimage(image)
        if ocr_result.hero is not None:
            return ocr_result

        return DetectionResult(
            None,
            0.0,
            ocr_result.raw_text,
            f"{lcu_result.status}；OCR 兜底：{ocr_result.status}",
            "fallback",
        )

    def detect_qimage(self, image: QImage) -> DetectionResult:
        reader = self._get_reader()
        if reader is None:
            return DetectionResult(None, 0.0, "", self._ocr_error or "EasyOCR 未安装", "ocr")

        scaled = image
        if image.width() > 1500:
            scaled = image.scaledToWidth(1500, Qt.TransformationMode.SmoothTransformation)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file:
                temp_path = Path(file.name)

            if not scaled.save(str(temp_path), "PNG"):
                return DetectionResult(None, 0.0, "", "截图保存失败", "ocr")

            chunks = reader.readtext(str(temp_path), detail=0, paragraph=True)
            raw_text = "\n".join(str(chunk) for chunk in chunks)
            return self.detect_text(raw_text, source="ocr")
        except Exception as exc:  # noqa: BLE001
            return DetectionResult(None, 0.0, "", f"OCR 识别失败：{exc}", "ocr")
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _get_reader(self):
        if not self.use_ocr:
            self._ocr_error = "OCR 已关闭"
            return None
        if self._reader is not None:
            return self._reader
        if self._ocr_error is not None:
            return None

        try:
            import easyocr  # type: ignore
        except ImportError:
            self._ocr_error = "EasyOCR 未安装"
            return None

        try:
            self._reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            return self._reader
        except Exception as exc:  # noqa: BLE001
            self._ocr_error = f"EasyOCR 初始化失败：{exc}"
            return None
