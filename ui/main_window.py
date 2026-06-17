from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRunnable,
    QRectF,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppStateStore
from core.bili_stream_proxy import BiliStreamProxy
from core.bilibili import BilibiliClient, BilibiliProfile, BilibiliResolvedAudio, BilibiliVideo
from core.champion_assets import ChampionAssetManager
from core.detector import DetectionResult, HeroDetector
from core.music_manager import HeroMusic, MusicManager, Track
from core.paths import ensure_user_resource, resource_path, user_data_path, user_data_root
from core.player import AudioPlayer
from ui.bilibili_login_dialog import BilibiliLoginDialog
from ui.bilibili_search_task import BilibiliHeroSearchTask


BG = "#0b0f1a"
TEXT = "#f6f8ff"
MUTED = "#9aa7c4"
CARD = "rgba(18, 26, 44, 184)"
BORDER = "rgba(150, 172, 220, 56)"

UI_SIZE_PROFILES = {
    "small": {"label": "小", "size": (1366, 860), "scale": 0.92, "font": 9},
    "medium": {"label": "中", "size": (1440, 900), "scale": 1.0, "font": 10},
    "large": {"label": "大", "size": (1600, 1000), "scale": 1.1, "font": 11},
}

TAG_LABELS = {
    "wind": "风",
    "lonely": "孤独",
    "battle": "战斗",
    "sword": "剑客",
    "shadow": "影流",
    "assassin": "刺客",
    "art": "艺术",
    "fatal": "宿命",
    "dramatic": "戏剧",
    "dragon": "龙",
    "rhythm": "节奏",
    "fight": "热血",
    "fox": "灵动",
    "charm": "魅惑",
    "pop": "热门",
    "light": "光",
    "bright": "明亮",
    "fighter": "战士",
    "tank": "坦克",
    "mage": "法师",
    "assassin": "刺客",
    "marksman": "射手",
    "support": "辅助",
}

HERO_PALETTES = {
    "yasuo": ("#213d77", "#8a6cff", "#64a7ff"),
    "zed": ("#2a1324", "#e04c72", "#7b6cff"),
    "jhin": ("#301a24", "#d99a5e", "#8a6cff"),
    "lee_sin": ("#27160f", "#d35f39", "#f0bc68"),
    "ahri": ("#251d56", "#e56fb8", "#7dc8ff"),
    "lux": ("#172a4e", "#f2d477", "#79b7ff"),
}


@dataclass
class HistoryEntry:
    hero_key: str
    hero_name: str
    track_name: str
    time_label: str


def apply_shadow(widget: QWidget, blur: int = 32, alpha: int = 90, y: int = 16) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)


def draw_pixmap_cover(painter: QPainter, rect: QRectF, pixmap: QPixmap, opacity: float = 1.0) -> bool:
    if pixmap.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return False

    scaled = pixmap.scaled(
        int(rect.width()),
        int(rect.height()),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = int(rect.left() + (rect.width() - scaled.width()) / 2)
    y = int(rect.top() + (rect.height() - scaled.height()) / 2)
    painter.save()
    painter.setOpacity(opacity)
    painter.drawPixmap(x, y, scaled)
    painter.restore()
    return True


class IconButton(QPushButton):
    def __init__(self, text: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("IconButton")
        self.setFixedSize(38, 38)


class LogoMark(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(54, 54)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(5, 5, 44, 44)
        gradient = QRadialGradient(rect.center(), 25)
        gradient.setColorAt(0.0, QColor("#f7f9ff"))
        gradient.setColorAt(0.72, QColor("#cfd8ff"))
        gradient.setColorAt(1.0, QColor("#6f8cff"))

        for index, angle in enumerate((18, 102, 186, 270)):
            painter.save()
            painter.translate(rect.center())
            painter.rotate(angle)
            path = QPainterPath()
            path.moveTo(0, -21)
            path.cubicTo(18, -18, 24, 0, 12, 14)
            path.cubicTo(4, 8, -2, 4, -15, 2)
            path.cubicTo(-9, -7, -7, -15, 0, -21)
            painter.setBrush(gradient if index % 2 == 0 else QColor("#ffffff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.restore()

        painter.setBrush(QColor(BG))
        painter.drawEllipse(QRectF(19, 19, 16, 16))


class GlowBackground(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        w = max(1, self.width())
        h = max(1, self.height())

        glow = QRadialGradient(QRectF(w * 0.26, -h * 0.24, w * 0.82, h * 0.8).center(), w * 0.42)
        glow.setColorAt(0.0, QColor(60, 88, 180, 90))
        glow.setColorAt(0.58, QColor(74, 38, 140, 34))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-w * 0.1, -h * 0.28, w * 0.9, h * 0.8))

        right_glow = QRadialGradient(QRectF(w * 0.58, -h * 0.2, w * 0.6, h * 0.65).center(), w * 0.34)
        right_glow.setColorAt(0.0, QColor(114, 88, 255, 62))
        right_glow.setColorAt(0.75, QColor(10, 14, 26, 0))
        painter.setBrush(right_glow)
        painter.drawEllipse(QRectF(w * 0.45, -h * 0.26, w * 0.65, h * 0.72))

        for x, y, radius, color in (
            (0.16, 0.09, 2, "#d58aff"),
            (0.21, 0.07, 1, "#a68cff"),
            (0.24, 0.11, 4, "#9b7aff"),
            (0.67, 0.09, 2, "#ff9bd7"),
            (0.76, 0.12, 5, "#d77bff"),
        ):
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            cx, cy = w * x, h * y
            if radius >= 4:
                path = QPainterPath()
                path.moveTo(cx, cy - radius)
                path.lineTo(cx + radius * 0.35, cy - radius * 0.35)
                path.lineTo(cx + radius, cy)
                path.lineTo(cx + radius * 0.35, cy + radius * 0.35)
                path.lineTo(cx, cy + radius)
                path.lineTo(cx - radius * 0.35, cy + radius * 0.35)
                path.lineTo(cx - radius, cy)
                path.lineTo(cx - radius * 0.35, cy - radius * 0.35)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                painter.drawEllipse(QRectF(cx, cy, radius * 2, radius * 2))


class HeroArtwork(QWidget):
    def __init__(
        self,
        hero_key: str = "yasuo",
        compact: bool = False,
        asset_manager: ChampionAssetManager | None = None,
        ensure_asset: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.hero_key = hero_key
        self.compact = compact
        self.asset_manager = asset_manager
        self.ensure_asset = ensure_asset
        self._icon_path = self.asset_manager.icon_path(hero_key, ensure=ensure_asset) if self.asset_manager is not None else None
        self.setMinimumSize(120, 120)

    def set_hero(self, hero_key: str) -> None:
        self.hero_key = hero_key
        self._icon_path = (
            self.asset_manager.icon_path(hero_key, ensure=self.ensure_asset) if self.asset_manager is not None else None
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        painter.setClipPath(path)

        if self._icon_path is not None:
            pixmap = QPixmap(str(self._icon_path))
            if draw_pixmap_cover(painter, rect, pixmap):
                shade = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
                shade.setColorAt(0.0, QColor(255, 255, 255, 10))
                shade.setColorAt(0.72, QColor(5, 8, 18, 42))
                shade.setColorAt(1.0, QColor(5, 8, 18, 120))
                painter.fillRect(rect, shade)
                painter.setClipping(False)
                painter.setPen(QPen(QColor(148, 171, 220, 70), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect, 16, 16)
                return

        base, accent, glow = HERO_PALETTES.get(self.hero_key, HERO_PALETTES["yasuo"])
        background = QLinearGradient(rect.topLeft(), rect.bottomRight())
        background.setColorAt(0.0, QColor(base))
        background.setColorAt(0.48, QColor(accent).darker(190))
        background.setColorAt(1.0, QColor("#07111e"))
        painter.fillRect(rect, background)

        radial = QRadialGradient(rect.center(), rect.width() * 0.66)
        radial.setColorAt(0.0, QColor(glow))
        radial.setColorAt(0.45, QColor(102, 94, 201, 70))
        radial.setColorAt(1.0, QColor(20, 20, 40, 0))
        painter.setBrush(radial)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect.adjusted(-30, -40, 70, 25))

        painter.setPen(QPen(QColor("#d7d9ff"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx = rect.left() + rect.width() * (0.54 if self.compact else 0.6)
        base_y = rect.bottom() - rect.height() * 0.12
        painter.drawLine(cx - rect.width() * 0.36, base_y - 92, cx + rect.width() * 0.28, base_y - 150)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(7, 11, 24, 220))
        silhouette = QPainterPath()
        silhouette.moveTo(cx - 18, base_y)
        silhouette.cubicTo(cx - 28, base_y - 42, cx - 10, base_y - 78, cx + 4, base_y - 98)
        silhouette.cubicTo(cx + 28, base_y - 74, cx + 28, base_y - 34, cx + 18, base_y)
        silhouette.closeSubpath()
        painter.drawPath(silhouette)

        for i in range(14):
            x = rect.left() + (i * 37) % max(1, int(rect.width()))
            y = rect.top() + (i * 53) % max(1, int(rect.height()))
            painter.setBrush(QColor(255, 147, 220, 90 if i % 2 else 150))
            painter.drawEllipse(QRectF(x, y, 3, 3))


class HeroBanner(QWidget):
    def __init__(
        self,
        hero_key: str = "yasuo",
        asset_manager: ChampionAssetManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.hero_key = hero_key
        self.asset_manager = asset_manager
        self._splash_path = self.asset_manager.splash_path(hero_key) if self.asset_manager is not None else None
        self.setMinimumHeight(330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_hero(self, hero_key: str) -> None:
        self.hero_key = hero_key
        self._splash_path = self.asset_manager.splash_path(hero_key) if self.asset_manager is not None else None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        rounded = QPainterPath()
        rounded.addRoundedRect(rect, 16, 16)
        painter.setClipPath(rounded)

        base, accent, glow_color = HERO_PALETTES.get(self.hero_key, HERO_PALETTES["yasuo"])

        has_splash = False
        if self._splash_path is not None:
            has_splash = draw_pixmap_cover(painter, rect, QPixmap(str(self._splash_path)))

        if not has_splash:
            base_gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            base_gradient.setColorAt(0.0, QColor(base).lighter(122))
            base_gradient.setColorAt(0.42, QColor("#121a2b"))
            base_gradient.setColorAt(1.0, QColor("#070c16"))
            painter.fillRect(rect, base_gradient)

            glow = QRadialGradient(rect.center() + self._point(rect.width() * 0.32, -16), rect.width() * 0.45)
            glow.setColorAt(0.0, QColor(glow_color))
            glow.setColorAt(0.3, QColor(accent))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect.adjusted(rect.width() * 0.34, -90, 170, 100))

            self._paint_warrior(painter, rect, accent)

        vignette = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        vignette.setColorAt(0.0, QColor(7, 11, 24, 238))
        vignette.setColorAt(0.32, QColor(7, 11, 24, 146))
        vignette.setColorAt(0.66, QColor(7, 11, 24, 42 if has_splash else 38))
        vignette.setColorAt(1.0, QColor(7, 11, 24, 202))
        painter.fillRect(rect, vignette)

        painter.setClipping(False)
        painter.setPen(QPen(QColor(148, 171, 220, 55), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

    def _paint_warrior(self, painter: QPainter, rect: QRectF, accent: str) -> None:
        center_x = rect.left() + rect.width() * 0.58
        center_y = rect.top() + rect.height() * 0.48

        painter.setPen(QPen(QColor("#586b95"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(5):
            y = rect.top() + 34 + i * 34
            painter.drawLine(rect.left() + 30, y, rect.left() + rect.width() * 0.72, y - 44)

        hair = QPainterPath()
        hair.moveTo(center_x - 30, center_y - 82)
        hair.cubicTo(center_x + 75, center_y - 164, center_x + 190, center_y - 96, center_x + 258, center_y - 132)
        hair.cubicTo(center_x + 136, center_y - 28, center_x + 48, center_y - 18, center_x - 16, center_y + 2)
        hair.closeSubpath()
        painter.setBrush(QColor("#111827"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(hair)

        scarf = QPainterPath()
        scarf.moveTo(center_x - 58, center_y - 4)
        scarf.cubicTo(center_x + 34, center_y - 80, center_x + 188, center_y - 60, center_x + 250, center_y - 12)
        scarf.cubicTo(center_x + 130, center_y + 46, center_x + 36, center_y + 56, center_x - 64, center_y + 36)
        scarf.closeSubpath()
        scarf_gradient = QLinearGradient(center_x - 50, center_y - 60, center_x + 220, center_y + 50)
        scarf_gradient.setColorAt(0.0, QColor(accent).darker(115))
        scarf_gradient.setColorAt(0.6, QColor("#1a2a55"))
        scarf_gradient.setColorAt(1.0, QColor("#0c1329"))
        painter.setBrush(scarf_gradient)
        painter.drawPath(scarf)

        body = QPainterPath()
        body.moveTo(center_x - 74, center_y + 116)
        body.cubicTo(center_x - 94, center_y + 22, center_x - 22, center_y - 38, center_x + 18, center_y - 34)
        body.cubicTo(center_x + 76, center_y - 18, center_x + 84, center_y + 68, center_x + 118, center_y + 132)
        body.closeSubpath()
        painter.setBrush(QColor("#0c1121"))
        painter.drawPath(body)

        painter.setPen(QPen(QColor("#d8e2ff"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(center_x - 275, center_y + 20, center_x + 118, center_y - 86)
        painter.setPen(QPen(QColor(accent), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(center_x - 275, center_y + 20, center_x + 118, center_y - 86)

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(18):
            painter.setBrush(QColor("#cc80d8" if i % 2 else "#706cff"))
            x = rect.left() + 58 + (i * 71) % int(max(1, rect.width() - 80))
            y = rect.top() + 28 + (i * 43) % int(max(1, rect.height() - 70))
            painter.drawEllipse(QRectF(x, y, 3, 3))

    @staticmethod
    def _point(x: float, y: float):
        from PySide6.QtCore import QPointF

        return QPointF(x, y)


class AudioOrb(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(132, 132)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(8, 8, self.width() - 16, self.height() - 16)

        glow = QRadialGradient(rect.center(), rect.width() * 0.62)
        glow.setColorAt(0.0, QColor(118, 108, 255, 80))
        glow.setColorAt(0.65, QColor(73, 155, 255, 55))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(0, 0, self.width(), self.height()))

        fill = QRadialGradient(rect.center(), rect.width() * 0.5)
        fill.setColorAt(0.0, QColor("#31406d"))
        fill.setColorAt(1.0, QColor("#121a36"))
        painter.setBrush(fill)
        painter.setPen(QPen(QColor("#8a6cff"), 3))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor("#6fb1ff"), 2))
        painter.drawArc(rect.adjusted(4, 4, -4, -4), 205 * 16, 156 * 16)

        painter.setPen(QPen(QColor("#dfe6ff"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x = rect.center().x() - 30
        for index, height in enumerate((25, 43, 62, 48, 36)):
            painter.drawLine(x + index * 15, rect.center().y() - height / 2, x + index * 15, rect.center().y() + height / 2)


class WaveformWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(64)
        self._bars = [random.uniform(0.18, 1.0) for _ in range(96)]
        self._progress = 0.0

    def set_progress(self, progress: float) -> None:
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 8, 0, -8)
        center_y = rect.center().y()
        bar_w = max(2, rect.width() / len(self._bars) * 0.42)
        step = rect.width() / len(self._bars)
        active_until = int(len(self._bars) * self._progress)

        painter.setPen(QPen(QColor(39, 50, 82), 2))
        painter.drawLine(rect.left(), center_y, rect.right(), center_y)

        for index, value in enumerate(self._bars):
            x = rect.left() + index * step
            height = 8 + value * (rect.height() - 10)
            color = QColor("#8a6cff") if index <= active_until else QColor("#2c57d4")
            if index % 5 == 0:
                color = QColor("#6fb1ff") if index <= active_until else QColor("#264699")
            painter.setPen(QPen(color, bar_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(x, center_y - height * 0.48, x, center_y + height * 0.48)

        knob_x = rect.left() + active_until * step
        painter.setBrush(QColor("#7bb3ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(knob_x - 4, center_y - 4, 8, 8))


class Pill(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class NavButton(QPushButton):
    def __init__(self, icon: str, text: str, active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(f"{icon}   {text}", parent)
        self.setCheckable(True)
        self.setChecked(active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("NavButton")
        self.setMinimumHeight(56)


class MiniCover(HeroArtwork):
    def __init__(
        self,
        hero_key: str = "yasuo",
        asset_manager: ChampionAssetManager | None = None,
        ensure_asset: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            hero_key=hero_key,
            compact=True,
            asset_manager=asset_manager,
            ensure_asset=ensure_asset,
            parent=parent,
        )
        self.setFixedSize(48, 48)


class TitleBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(54)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        layout.addWidget(IconButton("☰", "菜单"))
        layout.addWidget(IconButton("−", "最小化"))
        layout.addWidget(IconButton("□", "最大化"))
        layout.addWidget(IconButton("×", "关闭"))


class DetectionTaskSignals(QObject):
    finished = Signal(object)


class DetectionTask(QRunnable):
    def __init__(self, detector: HeroDetector, image: QImage | None) -> None:
        super().__init__()
        self.detector = detector
        self.image = image.copy() if image is not None else None
        self.signals = DetectionTaskSignals()

    @Slot()
    def run(self) -> None:
        result = self.detector.detect(self.image)
        self.signals.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Rift BGM")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resource_data_dir = resource_path("data")
        self.user_data_dir = user_data_root()
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        community_catalog_path = ensure_user_resource(Path("data") / "community_bgm_catalog.json")

        self.app_state = AppStateStore(user_data_path("app_state.json"))
        self._settings = self.app_state.settings
        self._favorites = self.app_state.favorites
        self._ui_size_key = self._normalize_ui_size_key(str(self._settings.get("ui_size") or "medium"))
        self._ui_scale = float(UI_SIZE_PROFILES[self._ui_size_key]["scale"])
        hero_data_path = self.resource_data_dir / "hero_music_map.json"
        self.music_manager = MusicManager(hero_data_path)
        self.champion_assets = ChampionAssetManager(
            hero_data_path,
            user_data_path("champions"),
        )
        self.music_manager.ensure_demo_audio_assets()
        self.detector = HeroDetector(self.music_manager, use_ocr=False)
        self.player = AudioPlayer(self)
        self.thread_pool = QThreadPool.globalInstance()
        self.bili_thread_pool = QThreadPool(self)
        self.bili_thread_pool.setMaxThreadCount(2)
        self.bilibili = BilibiliClient(self.user_data_dir, community_catalog_path=community_catalog_path)
        self.bili_stream_proxy = BiliStreamProxy()

        self._drag_position = None
        self._scan_enabled = bool(self._settings.get("auto_scan", True))
        self._detecting = False
        self._current_hero_key = "yasuo"
        self._manual_index = 0
        self._history: list[HistoryEntry] = []
        self._tag_widgets: list[QWidget] = []
        self._bili_candidates: list[BilibiliVideo] = []
        self._bili_result_cache: dict[str, tuple[list[BilibiliVideo], BilibiliResolvedAudio]] = {}
        self._bili_index = 0
        self._bili_searching = False
        self._bili_search_hero_key: str | None = None
        self._bili_active = False
        self._active_bili_hero_key: str | None = None
        self._nav_buttons: dict[str, NavButton] = {}
        self._page_indices: dict[str, int] = {}

        self._apply_window_profile()
        self._set_application_font()
        self._build_ui()
        self._wire_events()
        self._apply_layout_scale()
        self._set_initial_state()
        self._play_intro_animation()

    def _normalize_ui_size_key(self, value: str) -> str:
        return value if value in UI_SIZE_PROFILES else "medium"

    def _scaled(self, value: int | float) -> int:
        return max(1, int(round(float(value) * self._ui_scale)))

    def _css_px(self, value: int | float) -> str:
        return f"{self._scaled(value)}px"

    def _apply_window_profile(self) -> None:
        width, height = UI_SIZE_PROFILES[self._ui_size_key]["size"]
        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
        self.resize(width, height)

    def _set_application_font(self) -> None:
        QApplication.setFont(QFont("Microsoft YaHei UI", int(UI_SIZE_PROFILES[self._ui_size_key]["font"])))

    def _apply_layout_scale(self) -> None:
        if hasattr(self, "sidebar"):
            self.sidebar.setFixedWidth(self._scaled(258))
        if hasattr(self, "right_panel"):
            self.right_panel.setFixedWidth(self._scaled(394))
        if hasattr(self, "player_bar"):
            self.player_bar.setFixedHeight(self._scaled(96))
        if hasattr(self, "status_card"):
            self.status_card.setFixedHeight(self._scaled(138))
        if hasattr(self, "sidebar_mini_card"):
            self.sidebar_mini_card.setFixedHeight(self._scaled(82))
        if hasattr(self, "sidebar_cover"):
            self.sidebar_cover.setFixedSize(self._scaled(58), self._scaled(58))
        if hasattr(self, "hero_art"):
            self.hero_art.setMinimumHeight(self._scaled(330))
        if hasattr(self, "detect_status_label"):
            self.detect_status_label.setFixedWidth(self._scaled(142))
        if hasattr(self, "now_playing_card"):
            self.now_playing_card.setMinimumHeight(self._scaled(290))
        if hasattr(self, "now_media_host"):
            self.now_media_host.setFixedSize(self._scaled(320), self._scaled(182))
        if hasattr(self, "now_cover"):
            self.now_cover.setFixedSize(self._scaled(182), self._scaled(182))
        if hasattr(self, "player_cover"):
            self.player_cover.setFixedSize(self._scaled(72), self._scaled(72))
        if hasattr(self, "play_pause_button"):
            self.play_pause_button.setFixedSize(self._scaled(64), self._scaled(64))
        if hasattr(self, "volume_slider"):
            self.volume_slider.setFixedWidth(self._scaled(190))
        if hasattr(self, "bili_avatar_label"):
            self.bili_avatar_label.setFixedSize(self._scaled(64), self._scaled(64))
            self._update_bili_avatar(self.bilibili.cached_profile())

        for button in self.findChildren(IconButton):
            if button is getattr(self, "play_pause_button", None):
                continue
            size = 34 if button.toolTip() == "播放" else 38
            button.setFixedSize(self._scaled(size), self._scaled(size))

        for button in self._nav_buttons.values():
            button.setMinimumHeight(self._scaled(56))

        if hasattr(self, "shell"):
            self.shell.setStyleSheet(self._style_sheet())

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)

        self.shell = QFrame()
        self.shell.setObjectName("Shell")
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        root_layout.addWidget(self.shell)

        self.background = GlowBackground(self.shell)
        self.background.lower()

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        shell_layout.addWidget(content, 1)

        content_layout.addWidget(self._build_sidebar())
        content_layout.addWidget(self._build_center(), 1)
        content_layout.addWidget(self._build_right_panel())
        shell_layout.addWidget(self._build_player_bar())

        self.shell.setStyleSheet(self._style_sheet())

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(258)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(30, 34, 18, 14)
        layout.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        brand_row.addWidget(LogoMark())
        brand_text = QVBoxLayout()
        title = QLabel("Rift BGM")
        title.setObjectName("BrandTitle")
        version = QLabel("v1.0.0")
        version.setObjectName("BrandVersion")
        brand_text.addWidget(title)
        brand_text.addWidget(version)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        layout.addLayout(brand_row)
        layout.addSpacing(8)

        for key, icon, text, active in (
            ("home", "⌂", "首页", True),
            ("library", "♪", "音乐库", False),
            ("community", "♬", "词库", False),
            ("favorites", "♡", "收藏", False),
            ("settings", "⚙", "设置", False),
            ("about", "i", "关于", False),
        ):
            button = NavButton(icon, text, active)
            self._nav_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch()

        status = QFrame()
        self.status_card = status
        status.setObjectName("StatusCard")
        status.setFixedHeight(138)
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)
        self.connection_label = QLabel("●  英雄联盟监听中")
        self.connection_label.setObjectName("ConnectedText")
        self.scan_label = QLabel("LCU 正在监听选人状态...")
        self.scan_label.setObjectName("MutedText")
        self.scan_label.setWordWrap(True)
        self.stop_button = QPushButton("停止监听")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setObjectName("GlassButton")
        self.test_button = QPushButton("测试识别")
        self.test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_button.setObjectName("GlassButton")
        status_layout.addWidget(self.connection_label)
        status_layout.addWidget(self.scan_label)
        status_layout.addSpacing(4)
        scan_buttons = QHBoxLayout()
        scan_buttons.setSpacing(8)
        scan_buttons.addWidget(self.stop_button)
        scan_buttons.addWidget(self.test_button)
        status_layout.addLayout(scan_buttons)
        layout.addWidget(status)

        mini = QFrame()
        self.sidebar_mini_card = mini
        mini.setObjectName("MiniTrack")
        mini.setFixedHeight(82)
        mini_layout = QHBoxLayout(mini)
        mini_layout.setContentsMargins(10, 10, 10, 10)
        mini_layout.setSpacing(10)
        self.sidebar_cover = HeroArtwork(compact=True, asset_manager=self.champion_assets)
        self.sidebar_cover.setFixedSize(58, 58)
        mini_layout.addWidget(self.sidebar_cover)
        text = QVBoxLayout()
        self.sidebar_song_label = QLabel("等待识别")
        self.sidebar_song_label.setObjectName("SidebarMiniSong")
        self.sidebar_song_label.setMinimumWidth(0)
        self.sidebar_song_label.setMaximumWidth(135)
        self.sidebar_song_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.sidebar_artist_label = QLabel("Rift BGM")
        self.sidebar_artist_label.setObjectName("SidebarMutedText")
        self.sidebar_artist_label.setMinimumWidth(0)
        self.sidebar_artist_label.setMaximumWidth(135)
        self.sidebar_artist_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        text.addStretch()
        text.addWidget(self.sidebar_song_label)
        text.addWidget(self.sidebar_artist_label)
        text.addStretch()
        mini_layout.addLayout(text)
        layout.addWidget(mini)
        return sidebar

    def _build_center(self) -> QWidget:
        center = QWidget()
        center.setObjectName("Center")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(30, 18, 28, 34)
        layout.setSpacing(18)
        layout.addWidget(TitleBar())

        stack_host = QWidget()
        self.center_stack = QStackedLayout(stack_host)
        self.center_stack.setContentsMargins(0, 0, 0, 0)
        self.center_stack.setSpacing(0)
        for key, page in (
            ("home", self._build_home_page()),
            ("library", self._build_library_page()),
            ("community", self._build_community_page()),
            ("favorites", self._build_favorites_page()),
            ("settings", self._build_settings_page()),
            ("about", self._build_about_page()),
        ):
            self._page_indices[key] = self.center_stack.count()
            self.center_stack.addWidget(page)
        layout.addWidget(stack_host, 1)
        return center

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        headline = QLabel("为你的英雄，匹配专属BGM")
        headline.setObjectName("Headline")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(headline)
        layout.addSpacing(8)

        self.hero_card = self._build_hero_card()
        layout.addWidget(self.hero_card)
        layout.addWidget(self._build_now_playing_card())
        layout.addStretch(1)
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_title("音乐库", f"{len(self.music_manager.list_heroes())} 位英雄 / {len(self.music_manager.all_tracks())} 首本地兜底音频"))

        toolbar = QHBoxLayout()
        self.library_search_input = QLineEdit()
        self.library_search_input.setObjectName("SearchInput")
        self.library_search_input.setPlaceholderText("搜索英雄、别名或英文名")
        toolbar.addWidget(self.library_search_input, 1)
        refresh = QPushButton("刷新推荐")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.setObjectName("GlassButton")
        refresh.clicked.connect(self._render_library)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setObjectName("TransparentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.library_list_layout = QVBoxLayout(body)
        self.library_list_layout.setContentsMargins(0, 0, 10, 0)
        self.library_list_layout.setSpacing(10)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.library_search_input.textChanged.connect(self._render_library)
        self._render_library()
        return page

    def _build_favorites_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_title("收藏", "这里保存你常用的英雄 BGM 入口，重启后也会保留"))

        scroll = QScrollArea()
        scroll.setObjectName("TransparentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.favorite_list_layout = QVBoxLayout(body)
        self.favorite_list_layout.setContentsMargins(0, 0, 10, 0)
        self.favorite_list_layout.setSpacing(10)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self._render_favorites()
        return page

    def _build_community_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_title("社区词库", "把小红书/社区评论里推荐的歌名粘进来，自动变成英雄 BGM 搜索词"))

        import_card = QFrame()
        import_card.setObjectName("ContentCard")
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(22, 20, 22, 20)
        import_layout.setSpacing(12)

        controls = QHBoxLayout()
        self.community_hero_combo = QComboBox()
        self.community_hero_combo.setObjectName("SearchInput")
        for hero in self.music_manager.list_heroes():
            self.community_hero_combo.addItem(f"{hero.display_name} / {hero.english_name}", hero.key)
        controls.addWidget(self.community_hero_combo, 1)
        import_button = QPushButton("提取并加入词库")
        import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        import_button.setObjectName("GlassButton")
        import_button.clicked.connect(self._import_community_text)
        controls.addWidget(import_button)
        import_layout.addLayout(controls)

        self.community_text_input = QTextEdit()
        self.community_text_input.setObjectName("ImportText")
        self.community_text_input.setPlaceholderText("粘贴小红书评论/帖子正文，例如：\n阿卡丽还是得《梨花香》\n腕豪评论区都在刷 Repeat / 够格小曲")
        self.community_text_input.setMinimumHeight(120)
        import_layout.addWidget(self.community_text_input)
        self.community_import_status = QLabel("只保存搜索词，不下载音频。")
        self.community_import_status.setObjectName("MutedText")
        self.community_import_status.setWordWrap(True)
        import_layout.addWidget(self.community_import_status)
        layout.addWidget(import_card)

        scroll = QScrollArea()
        scroll.setObjectName("TransparentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.community_catalog_layout = QVBoxLayout(body)
        self.community_catalog_layout.setContentsMargins(0, 0, 10, 0)
        self.community_catalog_layout.setSpacing(10)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self._render_community_catalog()
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_title("设置", "控制识别、播放源和本地缓存行为"))

        card = QFrame()
        card.setObjectName("ContentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(16)

        self.auto_scan_checkbox = QCheckBox("启动后自动监听英雄选择")
        self.auto_scan_checkbox.setObjectName("SettingsCheck")
        self.auto_scan_checkbox.setChecked(bool(self._settings.get("auto_scan", True)))
        self.auto_bili_checkbox = QCheckBox("识别英雄后优先播放 B 站热门音频流")
        self.auto_bili_checkbox.setObjectName("SettingsCheck")
        self.auto_bili_checkbox.setChecked(bool(self._settings.get("auto_bili", True)))
        card_layout.addWidget(self.auto_scan_checkbox)
        card_layout.addWidget(self.auto_bili_checkbox)

        size_row = QHBoxLayout()
        size_label = QLabel("界面尺寸")
        size_label.setObjectName("MutedText")
        self.ui_size_combo = QComboBox()
        self.ui_size_combo.setObjectName("SearchInput")
        for key, profile in UI_SIZE_PROFILES.items():
            width, height = profile["size"]
            self.ui_size_combo.addItem(f"{profile['label']}  {width} x {height}", key)
        current_index = self.ui_size_combo.findData(self._ui_size_key)
        if current_index >= 0:
            self.ui_size_combo.setCurrentIndex(current_index)
        size_row.addWidget(size_label)
        size_row.addWidget(self.ui_size_combo, 1)
        card_layout.addLayout(size_row)

        actions = QHBoxLayout()
        clear_cache = QPushButton("清空 B站结果缓存")
        clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_cache.setObjectName("GlassButton")
        clear_cache.clicked.connect(self._clear_bili_cache)
        clear_history = QPushButton("清空识别历史")
        clear_history.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_history.setObjectName("GlassButton")
        clear_history.clicked.connect(self._clear_history)
        actions.addWidget(clear_cache)
        actions.addWidget(clear_history)
        actions.addStretch()
        card_layout.addLayout(actions)

        self.settings_status_label = QLabel(f"设置会自动保存到 {user_data_path('app_state.json')}")
        self.settings_status_label.setObjectName("MutedText")
        card_layout.addWidget(self.settings_status_label)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._page_title("关于", "Rift BGM - 英雄联盟选人阶段自动 BGM 播放器"))

        card = QFrame()
        card.setObjectName("ContentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(14)
        for text in (
            "LCU 识别当前选人英雄，便携包不内置 OCR 大依赖。",
            "B 站播放只解析在线音频流，不下载或永久缓存音频文件。",
            f"社区 BGM 词库保存在 {user_data_path('data', 'community_bgm_catalog.json')}，可以继续手工扩充。",
            f"收藏、音量和自动播放设置保存在 {user_data_path('app_state.json')}。",
        ):
            label = QLabel(text)
            label.setObjectName("MutedText")
            label.setWordWrap(True)
            card_layout.addWidget(label)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _page_title(self, title: str, subtitle: str) -> QWidget:
        header = QWidget()
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("Headline")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedText")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return header

    def _build_hero_card(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("HeroCard")
        frame.setMinimumHeight(330)
        frame_layout = QGridLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self.hero_art = HeroBanner(asset_manager=self.champion_assets)
        frame_layout.addWidget(self.hero_art, 0, 0)

        overlay = QWidget()
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay_layout = QGridLayout(overlay)
        overlay_layout.setContentsMargins(38, 34, 38, 34)

        left = QVBoxLayout()
        left.setSpacing(12)
        self.detect_status_label = QLabel("  ⏳  等待识别  ")
        self.detect_status_label.setObjectName("SuccessPill")
        self.detect_status_label.setFixedWidth(142)
        self.hero_name_label = QLabel("疾风剑豪 亚索")
        self.hero_name_label.setObjectName("HeroName")
        self.hero_en_label = QLabel("Yasuo")
        self.hero_en_label.setObjectName("HeroEnglish")
        self.matched_label = QLabel("♪  匹配到 0 首相关BGM")
        self.matched_label.setObjectName("MatchedText")
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setSpacing(10)

        left.addWidget(self.detect_status_label)
        left.addStretch(1)
        left.addWidget(self.hero_name_label)
        left.addWidget(self.hero_en_label)
        left.addSpacing(12)
        left.addWidget(self.matched_label)
        left.addSpacing(6)
        left.addLayout(self.tags_layout)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addStretch()
        right.addWidget(AudioOrb(), alignment=Qt.AlignmentFlag.AlignCenter)
        self.orb_caption = QLabel("识别到英雄后自动播放")
        self.orb_caption.setObjectName("OrbCaption")
        self.orb_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.orb_caption)
        right.addStretch()

        overlay_layout.addLayout(left, 0, 0)
        overlay_layout.addLayout(right, 0, 1)
        overlay_layout.setColumnStretch(0, 3)
        overlay_layout.setColumnStretch(1, 1)
        frame_layout.addWidget(overlay, 0, 0)
        apply_shadow(frame, blur=42, alpha=115, y=18)
        return frame

    def _build_now_playing_card(self) -> QWidget:
        card = QFrame()
        self.now_playing_card = card
        card.setObjectName("ContentCard")
        card.setMinimumHeight(290)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 22, 26, 24)
        layout.setSpacing(18)

        header = QLabel("正在播放")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        main = QHBoxLayout()
        main.setSpacing(24)
        media_host = QWidget()
        self.now_media_host = media_host
        media_host.setFixedSize(320, 182)
        self.now_media_stack = QStackedLayout(media_host)
        self.now_media_stack.setContentsMargins(0, 0, 0, 0)

        cover_host = QWidget()
        cover_layout = QVBoxLayout(cover_host)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        self.now_cover = HeroArtwork(compact=True, asset_manager=self.champion_assets)
        self.now_cover.setFixedSize(182, 182)
        cover_layout.addWidget(self.now_cover, alignment=Qt.AlignmentFlag.AlignCenter)
        self.now_media_stack.addWidget(cover_host)

        self.bili_player_view = None
        main.addWidget(media_host)

        info = QVBoxLayout()
        info.setSpacing(6)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        self.song_title_label = QLabel("等待自动匹配")
        self.song_title_label.setObjectName("SongTitle")
        self.artist_label = QLabel("Rift BGM")
        self.artist_label.setObjectName("ArtistText")
        self.track_tag_label = QLabel("未播放")
        self.track_tag_label.setObjectName("SmallTag")
        titles.addWidget(self.song_title_label)
        titles.addWidget(self.artist_label)
        titles.addWidget(self.track_tag_label, alignment=Qt.AlignmentFlag.AlignLeft)
        top.addLayout(titles)
        top.addStretch()
        self.current_favorite_button = IconButton("♡", "收藏")
        top.addWidget(self.current_favorite_button)
        for symbol, tooltip in (("⇩", "下载"), ("⋮", "更多")):
            top.addWidget(IconButton(symbol, tooltip))
        info.addLayout(top)
        info.addStretch()
        self.waveform = WaveformWidget()
        info.addWidget(self.waveform)
        times = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setObjectName("TimeText")
        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("TimeText")
        times.addWidget(self.current_time_label)
        times.addStretch()
        times.addWidget(self.duration_label)
        info.addLayout(times)
        main.addLayout(info, 1)
        layout.addLayout(main)
        apply_shadow(card, blur=36, alpha=80, y=14)
        return card

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        self.right_panel = panel
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(394)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 76, 18, 122)
        layout.setSpacing(18)
        layout.addWidget(self._build_bilibili_card())
        layout.addWidget(self._build_history_card())
        layout.addStretch()
        return panel

    def _build_bilibili_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SideCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("B站联动")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        profile = self.bilibili.cached_profile()
        account_row = QHBoxLayout()
        account_text = QVBoxLayout()
        status_text = f"已登录：{profile.uname}" if profile is not None else "未登录，可扫码提升播放兼容性"
        self.bili_status_label = QLabel(status_text)
        self.bili_status_label.setObjectName("MutedText")
        self.bili_status_label.setWordWrap(True)
        account_text.addWidget(self.bili_status_label)

        self.bili_result_label = QLabel("检测到英雄后自动搜索热门 BGM 视频")
        self.bili_result_label.setObjectName("MoreText")
        self.bili_result_label.setWordWrap(True)
        account_text.addWidget(self.bili_result_label)
        account_row.addLayout(account_text, 1)
        self.bili_avatar_label = QLabel()
        self.bili_avatar_label.setObjectName("BiliAvatar")
        self.bili_avatar_label.setFixedSize(self._scaled(64), self._scaled(64))
        self.bili_avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        account_row.addWidget(self.bili_avatar_label)
        layout.addLayout(account_row)
        self._update_bili_avatar(profile)

        buttons = QHBoxLayout()
        self.bili_login_button = QPushButton("扫码登录")
        self.bili_login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bili_login_button.setObjectName("GlassButton")
        self.bili_logout_button = QPushButton("退出")
        self.bili_logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bili_logout_button.setObjectName("TextButton")
        self.bili_logout_button.setEnabled(profile is not None)
        self.bili_login_button.setEnabled(True)
        buttons.addWidget(self.bili_login_button)
        buttons.addWidget(self.bili_logout_button)
        layout.addLayout(buttons)
        return card

    def _build_history_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SideCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("识别历史")
        title.setObjectName("SectionTitle")
        self.clear_history_button = QPushButton("清空")
        self.clear_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_history_button.setObjectName("TextButton")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.clear_history_button)
        layout.addLayout(header)

        self.history_list_layout = QVBoxLayout()
        self.history_list_layout.setSpacing(8)
        layout.addLayout(self.history_list_layout)
        self.more_history_label = QLabel("等待第一次识别")
        self.more_history_label.setObjectName("MoreText")
        self.more_history_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.more_history_label)
        return card

    def _build_recommend_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SideCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("热门BGM推荐")
        title.setObjectName("SectionTitle")
        swap = QLabel("自动生成")
        swap.setObjectName("MutedText")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(swap)
        layout.addLayout(header)

        for index, track in enumerate(self.music_manager.recommendations(4), start=1):
            layout.addWidget(self._recommend_row(str(index), track))
        return card

    def _recommend_row(self, index_text: str, track: Track) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        index = QLabel(index_text)
        index.setObjectName("RankText")
        index.setFixedWidth(20)
        layout.addWidget(index)
        layout.addWidget(MiniCover(track.hero_key, asset_manager=self.champion_assets))
        text = QVBoxLayout()
        title = QLabel(track.name)
        title.setObjectName("RecommendTitle")
        artist = QLabel(track.artist)
        artist.setObjectName("MutedText")
        text.addWidget(title)
        text.addWidget(artist)
        layout.addLayout(text, 1)
        play = IconButton("▶", "播放")
        play.setFixedSize(34, 34)
        play.clicked.connect(lambda _checked=False, selected=track: self._play_track(selected))
        layout.addWidget(play)
        return row

    def _render_library(self) -> None:
        if not hasattr(self, "library_list_layout"):
            return
        self._clear_layout(self.library_list_layout)
        needle = self._normalize_filter(self.library_search_input.text() if hasattr(self, "library_search_input") else "")
        heroes = []
        for hero in self.music_manager.list_heroes():
            haystack = self._normalize_filter(" ".join((hero.key, hero.display_name, hero.english_name, *hero.aliases)))
            if not needle or needle in haystack:
                heroes.append(hero)

        for hero in heroes[:80]:
            self.library_list_layout.addWidget(self._hero_library_row(hero))
        if not heroes:
            self.library_list_layout.addWidget(self._empty_state("没有匹配的英雄"))
        elif len(heroes) > 80:
            self.library_list_layout.addWidget(self._empty_state(f"已显示前 80 项，继续输入关键词可缩小范围。共匹配 {len(heroes)} 项。"))
        self.library_list_layout.addStretch()

    def _render_favorites(self) -> None:
        if not hasattr(self, "favorite_list_layout"):
            return
        self._clear_layout(self.favorite_list_layout)
        heroes = [hero for hero in self.music_manager.list_heroes() if hero.key in self._favorites]
        if not heroes:
            self.favorite_list_layout.addWidget(self._empty_state("还没有收藏。去音乐库点亮心形按钮即可加入。"))
        for hero in heroes:
            self.favorite_list_layout.addWidget(self._hero_library_row(hero))
        self.favorite_list_layout.addStretch()

    def _render_community_catalog(self) -> None:
        if not hasattr(self, "community_catalog_layout"):
            return
        self._clear_layout(self.community_catalog_layout)
        overrides = self.bilibili.community_bgm_catalog.overrides
        rows: list[tuple[str, HeroMusic, dict]] = []
        for key, override in overrides.items():
            hero = self.music_manager.get_hero(key)
            if hero is not None and isinstance(override, dict):
                rows.append((str(override.get("confidence") or ""), hero, override))
        rows.sort(key=lambda item: (0 if item[0] == "verified" else 1, item[1].english_name))

        if not rows:
            self.community_catalog_layout.addWidget(self._empty_state("还没有社区词库。粘贴评论后会自动生成。"))
        for confidence, hero, override in rows:
            queries = [str(query) for query in override.get("queries", []) if str(query).strip()]
            self.community_catalog_layout.addWidget(self._community_catalog_row(hero, queries, confidence))
        self.community_catalog_layout.addStretch()

    def _community_catalog_row(self, hero: HeroMusic, queries: list[str], confidence: str) -> QWidget:
        row = QFrame()
        row.setObjectName("ContentCard")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(MiniCover(hero.key, asset_manager=self.champion_assets))

        text = QVBoxLayout()
        title = QLabel(hero.display_name)
        title.setObjectName("RecommendTitle")
        sub = QLabel(f"{hero.english_name} · {confidence or 'manual'} · {len(queries)} 条搜索词")
        sub.setObjectName("MutedText")
        preview = QLabel(" / ".join(queries[:3]) if queries else "暂无搜索词")
        preview.setObjectName("MutedText")
        preview.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(sub)
        text.addWidget(preview)
        layout.addLayout(text, 1)

        play = QPushButton("试播")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setObjectName("GlassButton")
        play.clicked.connect(lambda _checked=False, selected=hero: self._play_bili_for_hero(selected))
        layout.addWidget(play)
        return row

    def _import_community_text(self) -> None:
        key = str(self.community_hero_combo.currentData() or "")
        hero = self.music_manager.get_hero(key)
        text = self.community_text_input.toPlainText().strip()
        if hero is None:
            self.community_import_status.setText("请选择一个英雄。")
            return
        if not text:
            self.community_import_status.setText("先粘贴评论或帖子正文。")
            return

        added = self.bilibili.community_bgm_catalog.add_comment_text(
            hero,
            text,
            source_label="小红书/社区评论手动粘贴导入",
        )
        if not added:
            self.community_import_status.setText("没有提取到新的歌名或搜索词，可能已经存在。")
            return

        self._bili_result_cache.pop(hero.key, None)
        self.community_import_status.setText("已加入：" + " / ".join(added[:6]))
        self.community_text_input.clear()
        self._render_community_catalog()
        self._render_library()

    def _hero_library_row(self, hero: HeroMusic) -> QWidget:
        row = QFrame()
        row.setObjectName("ContentCard")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        layout.addWidget(MiniCover(hero.key, asset_manager=self.champion_assets))
        text = QVBoxLayout()
        name = QLabel(hero.display_name)
        name.setObjectName("RecommendTitle")
        sub = QLabel(f"{hero.english_name} · 本地兜底 {len(hero.tracks)} 首")
        sub.setObjectName("MutedText")
        query = self._community_query_preview(hero)
        hint = QLabel(query)
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(sub)
        text.addWidget(hint)
        layout.addLayout(text, 1)

        bili_button = QPushButton("B站播放")
        bili_button.setCursor(Qt.CursorShape.PointingHandCursor)
        bili_button.setObjectName("GlassButton")
        bili_button.clicked.connect(lambda _checked=False, selected=hero: self._play_bili_for_hero(selected))
        local_button = QPushButton("本地")
        local_button.setCursor(Qt.CursorShape.PointingHandCursor)
        local_button.setObjectName("GlassButton")
        local_button.clicked.connect(lambda _checked=False, selected=hero: self._play_local_for_hero_from_button(selected))
        favorite_button = IconButton("♥" if hero.key in self._favorites else "♡", "取消收藏" if hero.key in self._favorites else "收藏")
        favorite_button.clicked.connect(lambda _checked=False, selected=hero: self._toggle_favorite(selected.key))
        layout.addWidget(bili_button)
        layout.addWidget(local_button)
        layout.addWidget(favorite_button)
        return row

    def _empty_state(self, text: str) -> QWidget:
        label = QLabel(text)
        label.setObjectName("MoreText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setMinimumHeight(90)
        return label

    def _community_query_preview(self, hero: HeroMusic) -> str:
        queries = self.bilibili.community_bgm_catalog.keywords_for(hero)
        if not queries:
            return "使用通用 BGM 搜索模板"
        return "优先搜索：" + " / ".join(queries[:2])

    def _play_bili_for_hero(self, hero: HeroMusic) -> None:
        self._show_page("home")
        self._set_hero_ui(hero, "手动播放", fade=True)
        self._search_and_play_bili(hero)

    def _play_local_for_hero_from_button(self, hero: HeroMusic) -> None:
        self._show_page("home")
        self._set_hero_ui(hero, "本地播放", fade=True)
        self._play_local_for_hero(hero)

    def _toggle_favorite(self, hero_key: str) -> None:
        hero_key = hero_key.lower()
        if hero_key in self._favorites:
            self._favorites.remove(hero_key)
        else:
            self._favorites.add(hero_key)
        self._save_app_state()
        self._render_library()
        self._render_favorites()
        self._update_current_favorite_button()

    def _clear_bili_cache(self) -> None:
        self._bili_result_cache.clear()
        if hasattr(self, "settings_status_label"):
            self.settings_status_label.setText("已清空本次运行中的 B 站搜索结果缓存")

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_page(self, key: str) -> None:
        if not hasattr(self, "center_stack") or key not in self._page_indices:
            return
        self.center_stack.setCurrentIndex(self._page_indices[key])
        for button_key, button in self._nav_buttons.items():
            button.setChecked(button_key == key)

    def _save_app_state(self) -> None:
        self.app_state.update(self._favorites, self._settings)

    @staticmethod
    def _normalize_filter(value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()

    def _build_player_bar(self) -> QWidget:
        bar = QFrame()
        self.player_bar = bar
        bar.setObjectName("PlayerBar")
        bar.setFixedHeight(96)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(28)

        self.player_cover = HeroArtwork(compact=True, asset_manager=self.champion_assets)
        self.player_cover.setFixedSize(72, 72)
        layout.addWidget(self.player_cover)
        names = QVBoxLayout()
        self.player_song_label = QLabel("等待识别")
        self.player_song_label.setObjectName("MiniSong")
        self.player_artist_label = QLabel("Rift BGM")
        self.player_artist_label.setObjectName("MutedText")
        names.addStretch()
        names.addWidget(self.player_song_label)
        names.addWidget(self.player_artist_label)
        names.addStretch()
        layout.addLayout(names)
        layout.addSpacerItem(QSpacerItem(60, 1, QSizePolicy.Policy.Expanding))

        self.shuffle_button = IconButton("⇄", "随机播放")
        self.prev_button = IconButton("◀", "上一首")
        self.play_pause_button = IconButton("▶", "播放/暂停")
        self.play_pause_button.setObjectName("PrimaryPlayButton")
        self.play_pause_button.setFixedSize(64, 64)
        self.next_button = IconButton("▶", "下一首")
        self.queue_button = IconButton("☷", "播放列表")
        for button in (self.shuffle_button, self.prev_button, self.play_pause_button, self.next_button, self.queue_button):
            layout.addWidget(button)

        layout.addSpacerItem(QSpacerItem(60, 1, QSizePolicy.Policy.Expanding))
        volume_icon = QLabel("音量")
        volume_icon.setObjectName("PlayerIconText")
        layout.addWidget(volume_icon)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setFixedWidth(190)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self._settings.get("volume", 58)))
        layout.addWidget(self.volume_slider)
        layout.addWidget(IconButton("词", "歌词"))
        layout.addWidget(IconButton("⇱", "迷你播放器"))
        return bar

    def _wire_events(self) -> None:
        self.stop_button.clicked.connect(self._toggle_scan)
        self.test_button.clicked.connect(self._simulate_detection)
        self.clear_history_button.clicked.connect(self._clear_history)
        self.bili_login_button.clicked.connect(self._open_bili_login)
        self.bili_logout_button.clicked.connect(self._logout_bili)
        self.play_pause_button.clicked.connect(self._toggle_playback)
        self.next_button.clicked.connect(self._play_next)
        self.prev_button.clicked.connect(self._play_next)
        self.shuffle_button.clicked.connect(self._play_next)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.current_favorite_button.clicked.connect(self._toggle_current_favorite)

        for key, button in self._nav_buttons.items():
            button.clicked.connect(lambda _checked=False, page_key=key: self._show_page(page_key))
        if hasattr(self, "auto_scan_checkbox"):
            self.auto_scan_checkbox.toggled.connect(self._set_auto_scan_enabled)
        if hasattr(self, "auto_bili_checkbox"):
            self.auto_bili_checkbox.toggled.connect(self._set_auto_bili_enabled)
        if hasattr(self, "ui_size_combo"):
            self.ui_size_combo.currentIndexChanged.connect(self._set_ui_size_from_combo)

        self.player.track_changed.connect(self._on_track_changed)
        self.player.playback_state_changed.connect(self._on_playback_state_changed)
        self.player.position_changed.connect(self._on_position_changed)
        self.player.error_occurred.connect(self._on_player_error)
        self.player.track_finished.connect(self._play_next)

        for button in self.findChildren(IconButton):
            if button.toolTip() == "最小化":
                button.clicked.connect(self.showMinimized)
            elif button.toolTip() == "最大化":
                button.clicked.connect(self._toggle_maximized)
            elif button.toolTip() == "关闭":
                button.clicked.connect(self.close)

        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(2000)
        self.scan_timer.timeout.connect(self._scan_screen)
        self.scan_timer.start()

    def _set_initial_state(self) -> None:
        self.player.set_volume(self.volume_slider.value())
        if not self._scan_enabled:
            self.stop_button.setText("开始监听")
            self.scan_label.setText("监听已暂停")
        hero = self.music_manager.get_hero("yasuo")
        if hero is not None:
            self._set_hero_ui(hero, "等待识别", fade=False)
        self._render_history()
        self._render_library()
        self._render_favorites()
        self._render_community_catalog()
        self._update_current_favorite_button()

    def _open_bili_login(self) -> None:
        dialog = BilibiliLoginDialog(self.bilibili, self.bili_thread_pool, self)
        dialog.login_succeeded.connect(self._on_bili_login_succeeded)
        dialog.exec()

    def _on_bili_login_succeeded(self, profile: BilibiliProfile) -> None:
        self.bili_status_label.setText(f"已登录：{profile.uname}")
        self.bili_result_label.setText("登录成功，选英雄后会自动搜索 BGM")
        self.bili_logout_button.setEnabled(True)
        self._update_bili_avatar(profile)

    def _logout_bili(self) -> None:
        self.bilibili.clear_session()
        self.bili_status_label.setText("未登录，可扫码提升播放兼容性")
        self.bili_result_label.setText("检测到英雄后自动搜索热门 BGM 视频")
        self.bili_logout_button.setEnabled(False)
        self._update_bili_avatar(None)
        self._stop_bili_player()

    def _update_bili_avatar(self, profile: BilibiliProfile | None) -> None:
        if not hasattr(self, "bili_avatar_label"):
            return

        size = self.bili_avatar_label.width() or self._scaled(64)
        avatar_path = self.bilibili.cached_profile_avatar(profile)
        pixmap = QPixmap(str(avatar_path)) if avatar_path is not None else QPixmap()
        if pixmap.isNull():
            self.bili_avatar_label.setPixmap(QPixmap())
            self.bili_avatar_label.setText("未")
            return

        scaled = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, size, size))
        painter.setClipPath(path)
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()
        self.bili_avatar_label.setText("")
        self.bili_avatar_label.setPixmap(canvas)

    def _toggle_playback(self) -> None:
        self.player.toggle_pause()

    def _set_volume(self, value: int) -> None:
        self.player.set_volume(value)
        self._settings["volume"] = int(value)
        self._save_app_state()

    def _set_auto_scan_enabled(self, enabled: bool) -> None:
        self._settings["auto_scan"] = bool(enabled)
        self._save_app_state()
        if self._scan_enabled != enabled:
            self._toggle_scan()
        if hasattr(self, "settings_status_label"):
            self.settings_status_label.setText("自动监听设置已保存")

    def _set_auto_bili_enabled(self, enabled: bool) -> None:
        self._settings["auto_bili"] = bool(enabled)
        self._save_app_state()
        if hasattr(self, "settings_status_label"):
            self.settings_status_label.setText("B 站优先播放设置已保存")

    def _set_ui_size_from_combo(self) -> None:
        if not hasattr(self, "ui_size_combo"):
            return
        key = self._normalize_ui_size_key(str(self.ui_size_combo.currentData() or "medium"))
        if key == self._ui_size_key:
            return

        self._ui_size_key = key
        self._ui_scale = float(UI_SIZE_PROFILES[key]["scale"])
        self._settings["ui_size"] = key
        self._save_app_state()
        self._apply_window_profile()
        self._set_application_font()
        self._apply_layout_scale()
        if hasattr(self, "settings_status_label"):
            profile = UI_SIZE_PROFILES[key]
            width, height = profile["size"]
            self.settings_status_label.setText(f"已切换为{profile['label']}尺寸：{width} x {height}")

    def _toggle_current_favorite(self) -> None:
        self._toggle_favorite(self._current_hero_key)

    def _update_current_favorite_button(self) -> None:
        if not hasattr(self, "current_favorite_button"):
            return
        is_favorite = self._current_hero_key in self._favorites
        self.current_favorite_button.setText("♥" if is_favorite else "♡")
        self.current_favorite_button.setToolTip("取消收藏" if is_favorite else "收藏")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "background"):
            self.background.setGeometry(self.background.parentWidget().rect())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_position = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.scan_timer.stop()
        self._stop_bili_player()
        self.bili_stream_proxy.stop()
        self.player.stop()
        super().closeEvent(event)

    def _scan_screen(self) -> None:
        if not self._scan_enabled or self._detecting:
            return

        image: QImage | None = None
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            pixmap = screen.grabWindow(0)
            if not pixmap.isNull():
                image = pixmap.toImage()

        self._detecting = True
        self.scan_label.setText("正在读取 LCU 选人状态...")
        task = DetectionTask(self.detector, image)
        task.signals.finished.connect(self._on_detection_result)
        self.thread_pool.start(task)

    def _on_detection_result(self, result: DetectionResult) -> None:
        self._detecting = False
        if result.hero is None:
            self.scan_label.setText(result.status)
            if result.source in {"lcu-waiting", "lcu-unmapped"}:
                self.connection_label.setText("●  LCU 已连接")
            elif result.source in {"lcu-unavailable", "fallback"}:
                self.connection_label.setText("●  等待 LCU 连接")
            return
        self._handle_detected_hero(result.hero, result.confidence, result.source)

    def _simulate_detection(self) -> None:
        heroes = self.music_manager.list_heroes()
        if not heroes:
            self.scan_label.setText("音乐库为空")
            return
        hero = heroes[self._manual_index % len(heroes)]
        self._manual_index += 1
        result = self.detector.detect_text(hero.display_name, source="manual")
        if result.hero is not None:
            self._handle_detected_hero(result.hero, result.confidence, "manual")

    def _handle_detected_hero(self, hero: HeroMusic, confidence: float, source: str) -> None:
        source_text = {
            "manual": "测试识别",
            "lcu": "LCU",
            "ocr": "OCR",
            "fallback": "OCR 兜底",
        }.get(source, source.upper())
        status = f"识别成功 {confidence:.0%}"
        self.scan_label.setText(f"{source_text} 锁定：{hero.display_name}")
        self.connection_label.setText("●  LCU 已连接" if source == "lcu" else "●  英雄联盟监听中")

        already_playing = hero.key == self._current_hero_key and (
            self.player.current_track is not None
            or self._bili_searching
            or (self._bili_active and self._active_bili_hero_key == hero.key)
        )
        if already_playing:
            self.detect_status_label.setText(f"  ✓  {status}  ")
            return

        self._set_hero_ui(hero, status, fade=True)
        if bool(self._settings.get("auto_bili", True)):
            self._search_and_play_bili(hero)
        else:
            self._play_local_for_hero(hero)

    def _play_track(self, track: Track) -> None:
        self._stop_bili_player()
        hero = self.music_manager.get_hero(track.hero_key)
        if hero is not None:
            self._set_hero_ui(hero, "准备播放", fade=True)
            self._current_hero_key = hero.key
        self.player.play(track)

    def _play_local_for_hero(self, hero: HeroMusic) -> None:
        track = self.music_manager.choose_track(hero.key, self.player.current_track.path if self.player.current_track else None)
        if track is not None:
            self._play_track(track)

    def _show_bili_search_pending(self, hero: HeroMusic) -> None:
        self._stop_bili_player()
        self.player.stop()
        self.now_media_stack.setCurrentIndex(0)
        for cover in (self.now_cover, self.player_cover, self.sidebar_cover):
            cover.set_hero(hero.key)
        pending_title = f"正在搜索 {hero.english_name} BGM"
        self.song_title_label.setText(pending_title)
        self.artist_label.setText("Bilibili")
        self.track_tag_label.setText("B站热门视频")
        self.player_song_label.setText(pending_title)
        self.player_artist_label.setText("Bilibili")
        self.sidebar_song_label.setText(pending_title)
        self.sidebar_artist_label.setText("Bilibili")
        self.waveform.set_progress(0)
        self.current_time_label.setText("00:00")
        self.duration_label.setText("--:--")

    def _search_and_play_bili(self, hero: HeroMusic) -> None:
        cached = self._bili_result_cache.get(hero.key)
        if cached:
            videos, resolved = cached
            self._bili_candidates = videos
            self._bili_index = 0
            self._play_bili_audio(resolved, hero)
            return

        self._show_bili_search_pending(hero)
        self._bili_searching = True
        self._bili_search_hero_key = hero.key
        self._active_bili_hero_key = hero.key
        self.bili_result_label.setText(f"正在搜索：{hero.english_name} BGM")
        self.detect_status_label.setText("  B站搜索中  ")
        task = BilibiliHeroSearchTask(self.bilibili, hero, limit=5)
        task.signals.finished.connect(self._on_bili_search_finished)
        task.signals.failed.connect(self._on_bili_search_failed)
        self.bili_thread_pool.start(task)

    def _on_bili_search_finished(self, payload: object) -> None:
        hero_key, videos, resolved = payload
        if hero_key == self._bili_search_hero_key:
            self._bili_searching = False
            self._bili_search_hero_key = None
        if hero_key != self._current_hero_key:
            return
        hero = self.music_manager.get_hero(hero_key)
        if hero is None:
            return
        if not videos:
            self.bili_result_label.setText("没有搜到 B 站结果，已回落本地音频")
            self._play_local_for_hero(hero)
            return
        self._bili_candidates = list(videos)
        self._bili_result_cache[hero_key] = (self._bili_candidates, resolved)
        self._bili_index = 0
        self._play_bili_audio(resolved, hero)

    def _on_bili_search_failed(self, payload: object) -> None:
        hero_key, message = payload
        if hero_key == self._bili_search_hero_key:
            self._bili_searching = False
            self._bili_search_hero_key = None
        if hero_key != self._current_hero_key:
            return
        self.bili_result_label.setText(str(message))
        hero = self.music_manager.get_hero(hero_key)
        if hero is not None:
            self._play_local_for_hero(hero)

    def _play_bili_audio(self, resolved: BilibiliResolvedAudio, hero: HeroMusic) -> None:
        video = resolved.video
        stream_url = self.bili_stream_proxy.register(resolved.stream)
        self.player.stop()
        self._bili_active = True
        self._active_bili_hero_key = hero.key
        self._current_hero_key = hero.key
        self.now_media_stack.setCurrentIndex(0)

        self.song_title_label.setText(video.title)
        self.artist_label.setText(video.author)
        self.track_tag_label.setText("Bilibili 热门 BGM")
        self.player_song_label.setText(video.title)
        self.player_artist_label.setText(video.author)
        self.sidebar_song_label.setText(video.title)
        self.sidebar_artist_label.setText(video.author)
        for cover in (self.now_cover, self.player_cover, self.sidebar_cover):
            cover.set_hero(hero.key)
        self.detect_status_label.setText("  B站播放中  ")
        self.orb_caption.setText("正在播放 B 站热门视频")
        self.bili_result_label.setText(f"{video.keyword} · {video.bvid}")
        self.waveform.set_progress(0)
        self.current_time_label.setText("00:00")
        self.duration_label.setText(video.duration or "00:00")
        self.play_pause_button.setText("鈪?")
        self._add_history_entry(hero.key, hero.display_name, video.title)
        track = Track(
            name=video.title,
            path=Path(f"bilibili-{video.bvid}.stream"),
            artist=video.author,
            weight=1.0,
            hero_key=hero.key,
            hero_name=hero.display_name,
        )
        self.player.play_remote(track, stream_url)

    def _stop_bili_player(self) -> None:
        self._bili_active = False
        self._active_bili_hero_key = None
        if hasattr(self, "now_media_stack"):
            self.now_media_stack.setCurrentIndex(0)

    def _play_next(self) -> None:
        if self._bili_active and self._bili_candidates:
            hero = self.music_manager.get_hero(self._active_bili_hero_key or self._current_hero_key)
            if hero is not None:
                self._search_and_play_bili(hero)
            return
        current = self.player.current_track
        hero_key = current.hero_key if current is not None else self._current_hero_key
        track = self.music_manager.choose_track(hero_key, current.path if current is not None else None)
        if track is not None:
            self._play_track(track)

    def _toggle_scan(self) -> None:
        self._scan_enabled = not self._scan_enabled
        self._settings["auto_scan"] = self._scan_enabled
        if hasattr(self, "auto_scan_checkbox"):
            self.auto_scan_checkbox.blockSignals(True)
            self.auto_scan_checkbox.setChecked(self._scan_enabled)
            self.auto_scan_checkbox.blockSignals(False)
        self._save_app_state()
        if self._scan_enabled:
            self.stop_button.setText("停止监听")
            self.scan_label.setText("LCU 正在监听选人状态...")
            self.scan_timer.start()
        else:
            self.stop_button.setText("开始监听")
            self.scan_label.setText("监听已暂停")

    def _clear_history(self) -> None:
        self._history.clear()
        self._render_history()

    def _on_track_changed(self, track: Track) -> None:
        self.song_title_label.setText(track.name)
        self.artist_label.setText(track.artist)
        self.track_tag_label.setText(f"{track.hero_name} 专属BGM")
        self.player_song_label.setText(track.name)
        self.player_artist_label.setText(track.artist)
        self.sidebar_song_label.setText(track.name)
        self.sidebar_artist_label.setText(track.artist)
        for cover in (self.now_cover, self.player_cover, self.sidebar_cover):
            cover.set_hero(track.hero_key)
        self.detect_status_label.setText("  ✓  正在播放  ")
        self.orb_caption.setText("正在为你播放专属BGM")
        self.waveform.set_progress(0)
        self.current_time_label.setText("00:00")
        self.duration_label.setText("00:00")
        self._add_history(track)

    def _on_playback_state_changed(self, is_playing: bool) -> None:
        self.play_pause_button.setText("Ⅱ" if is_playing else "▶")

    def _on_position_changed(self, position: int, duration: int) -> None:
        self.current_time_label.setText(self._format_ms(position))
        self.duration_label.setText(self._format_ms(duration))
        self.waveform.set_progress(position / duration if duration > 0 else 0)

    def _on_player_error(self, message: str) -> None:
        self.scan_label.setText(message)
        self.detect_status_label.setText("  !  播放失败  ")

    def _set_hero_ui(self, hero: HeroMusic, status: str, fade: bool) -> None:
        self._current_hero_key = hero.key
        self._update_current_favorite_button()
        if hasattr(self, "community_hero_combo"):
            index = self.community_hero_combo.findData(hero.key)
            if index >= 0:
                self.community_hero_combo.setCurrentIndex(index)
        self.hero_art.set_hero(hero.key)
        for cover in (self.now_cover, self.player_cover, self.sidebar_cover):
            cover.set_hero(hero.key)
        self.hero_name_label.setText(hero.display_name)
        self.hero_en_label.setText(hero.english_name)
        self.detect_status_label.setText(f"  ✓  {status}  ")
        self.matched_label.setText(f"♪  匹配到 {len(hero.tracks)} 首相关BGM")
        self._set_tags(hero.tags)
        if fade:
            self._fade_widget(self.hero_card)

    def _set_tags(self, tags: tuple[str, ...]) -> None:
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for tag in tags[:5]:
            self.tags_layout.addWidget(Pill(TAG_LABELS.get(tag, tag)))
        self.tags_layout.addStretch()

    def _add_history(self, track: Track) -> None:
        entry = HistoryEntry(track.hero_key, track.hero_name, track.name, "刚刚")
        self._history = [item for item in self._history if item.hero_key != entry.hero_key]
        self._history.insert(0, entry)
        self._history = self._history[:5]
        self._render_history()

    def _add_history_entry(self, hero_key: str, hero_name: str, track_name: str) -> None:
        entry = HistoryEntry(hero_key, hero_name, track_name, "刚刚")
        self._history = [item for item in self._history if item.hero_key != entry.hero_key]
        self._history.insert(0, entry)
        self._history = self._history[:5]
        self._render_history()

    def _render_history(self) -> None:
        while self.history_list_layout.count():
            item = self.history_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, entry in enumerate(self._history):
            self.history_list_layout.addWidget(self._history_row(entry, active=index == 0))
        self.more_history_label.setText("查看更多  ⌄" if self._history else "等待第一次识别")

    def _history_row(self, entry: HistoryEntry, active: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("HistoryRowActive" if active else "HistoryRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)
        layout.addWidget(MiniCover(entry.hero_key, asset_manager=self.champion_assets))
        names = QVBoxLayout()
        name = QLabel(entry.hero_name)
        name.setObjectName("HistoryName")
        sub = QLabel(entry.track_name)
        sub.setObjectName("MutedText")
        names.addWidget(name)
        names.addWidget(sub)
        layout.addLayout(names)
        layout.addStretch()
        time = QLabel("正在播放" if active else entry.time_label)
        time.setObjectName("ActiveTime" if active else "MutedText")
        layout.addWidget(time)
        return row

    def _play_intro_animation(self) -> None:
        self._fade_widget(self.hero_card)

    def _fade_widget(self, widget: QWidget) -> None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(500)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._hero_intro = animation

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(0, value // 1000)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _style_sheet(self) -> str:
        return f"""
        QWidget {{
            color: {TEXT};
            font-family: "Microsoft YaHei UI", "Segoe UI";
            font-size: {self._css_px(14)};
        }}
        #Root {{
            background: transparent;
        }}
        #Shell {{
            background-color: {BG};
            border: 1px solid rgba(116, 137, 186, 76);
            border-radius: 24px;
        }}
        #Sidebar {{
            background-color: rgba(9, 14, 26, 199);
            border-top-left-radius: 24px;
            border-bottom-left-radius: 24px;
            border-right: 1px solid rgba(144, 162, 210, 41);
        }}
        #Center, #RightPanel {{
            background: transparent;
        }}
        #BrandTitle {{
            font-size: {self._css_px(20)};
            font-weight: 800;
            color: #ffffff;
        }}
        #BrandVersion, #MutedText, #ArtistText, #TimeText {{
            color: {MUTED};
        }}
        #Headline {{
            font-size: {self._css_px(30)};
            font-weight: 900;
            color: #ffffff;
        }}
        #NavButton {{
            text-align: left;
            padding-left: 22px;
            border: 1px solid transparent;
            border-radius: 9px;
            color: #96a2be;
            background: transparent;
            font-size: {self._css_px(17)};
            font-weight: 650;
        }}
        #NavButton:hover {{
            color: #ffffff;
            background-color: rgba(107, 133, 195, 33);
            border: 1px solid rgba(129, 151, 221, 51);
        }}
        #NavButton:checked {{
            color: #ffffff;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(134, 96, 255, 107),
                stop:1 rgba(77, 136, 255, 61));
            border: 1px solid rgba(143, 117, 255, 242);
        }}
        #StatusCard, #MiniTrack, #ContentCard, #SideCard {{
            background-color: {CARD};
            border: 1px solid {BORDER};
            border-radius: 16px;
        }}
        #MiniTrack {{
            border-radius: 14px;
        }}
        #BiliAvatar {{
            color: #9fb2e9;
            font-weight: 900;
            background-color: rgba(125, 148, 199, 35);
            border: 1px solid rgba(137, 108, 255, 95);
            border-radius: {self._css_px(32)};
        }}
        #HeroCard {{
            background-color: transparent;
            border: none;
        }}
        #BiliPlayer {{
            background-color: #05070d;
            border: 1px solid rgba(147, 166, 210, 56);
            border-radius: 12px;
        }}
        #ConnectedText {{
            color: #ffffff;
            font-weight: 800;
        }}
        #GlassButton {{
            min-height: 38px;
            border-radius: 9px;
            color: #ffffff;
            font-weight: 700;
            background: rgba(125, 148, 199, 43);
            border: 1px solid rgba(147, 166, 210, 33);
        }}
        #GlassButton:hover {{
            background: rgba(137, 108, 255, 66);
            border: 1px solid rgba(137, 108, 255, 122);
        }}
        #SearchInput {{
            min-height: 42px;
            border-radius: 9px;
            color: #ffffff;
            padding: 0 14px;
            background-color: rgba(125, 148, 199, 34);
            border: 1px solid rgba(147, 166, 210, 48);
            font-weight: 650;
        }}
        #SearchInput:focus {{
            border: 1px solid rgba(137, 108, 255, 168);
            background-color: rgba(125, 148, 199, 48);
        }}
        #ImportText {{
            border-radius: 9px;
            color: #ffffff;
            padding: 12px;
            background-color: rgba(125, 148, 199, 28);
            border: 1px solid rgba(147, 166, 210, 48);
            font-weight: 600;
        }}
        #ImportText:focus {{
            border: 1px solid rgba(137, 108, 255, 168);
            background-color: rgba(125, 148, 199, 42);
        }}
        #TransparentScroll {{
            background: transparent;
            border: none;
        }}
        #SettingsCheck {{
            color: #f6f8ff;
            font-size: 16px;
            font-weight: 700;
            spacing: 10px;
        }}
        #SettingsCheck::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid rgba(147, 166, 210, 100);
            background: rgba(125, 148, 199, 34);
        }}
        #SettingsCheck::indicator:checked {{
            background: #8a6cff;
            border: 1px solid #a590ff;
        }}
        #TextButton {{
            color: #aeb8d2;
            background: transparent;
            border: none;
            font-weight: 700;
        }}
        #TextButton:hover {{
            color: #ffffff;
        }}
        #SuccessPill {{
            color: #b9ffdf;
            font-weight: 800;
            background-color: rgba(0, 174, 123, 36);
            border: 1px solid rgba(38, 228, 166, 122);
            border-radius: 9px;
            padding: 9px 12px;
        }}
        #HeroName {{
            font-size: {self._css_px(34)};
            font-weight: 900;
            color: #ffffff;
        }}
        #HeroEnglish {{
            font-size: {self._css_px(24)};
            color: #c7d1ea;
            font-weight: 650;
        }}
        #MatchedText {{
            color: #f4f7ff;
            font-size: {self._css_px(16)};
            font-weight: 650;
        }}
        #Pill {{
            color: #c9d4ed;
            background-color: rgba(112, 128, 168, 36);
            border: 1px solid rgba(140, 161, 213, 36);
            border-radius: 13px;
            padding: 7px 15px;
        }}
        #OrbCaption {{
            color: #d5def5;
            font-size: 15px;
            font-weight: 700;
        }}
        #SectionTitle {{
            font-size: {self._css_px(19)};
            font-weight: 900;
            color: #ffffff;
        }}
        #SongTitle {{
            font-size: {self._css_px(28)};
            font-weight: 900;
            color: #ffffff;
        }}
        #MiniSong {{
            font-size: {self._css_px(18)};
            font-weight: 800;
            color: #ffffff;
        }}
        #SidebarMiniSong {{
            font-size: {self._css_px(15)};
            font-weight: 800;
            color: #ffffff;
        }}
        #SidebarMutedText {{
            font-size: {self._css_px(12)};
            color: {MUTED};
        }}
        #SmallTag {{
            color: #dfe6ff;
            background-color: rgba(147, 164, 212, 36);
            border: 1px solid rgba(147, 164, 212, 26);
            border-radius: 9px;
            padding: 6px 10px;
        }}
        #IconButton {{
            border: none;
            border-radius: 19px;
            color: #b9c4df;
            background-color: transparent;
            font-size: {self._css_px(21)};
            font-weight: 700;
        }}
        #IconButton:hover {{
            color: #ffffff;
            background-color: rgba(137, 108, 255, 46);
        }}
        #PrimaryPlayButton {{
            border-radius: 32px;
            color: #ffffff;
            font-size: {self._css_px(28)};
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.7,
                stop:0 rgba(255,255,255,87),
                stop:0.45 rgba(137,108,255,184),
                stop:1 rgba(71,146,255,179));
            border: 1px solid rgba(165, 144, 255, 250);
        }}
        #HistoryRow, #HistoryRowActive {{
            border-radius: 9px;
            background-color: transparent;
            border: 1px solid transparent;
        }}
        #HistoryRowActive {{
            background-color: rgba(106, 125, 178, 46);
            border: 1px solid rgba(130, 151, 215, 66);
        }}
        #HistoryName, #RecommendTitle {{
            color: #ffffff;
            font-weight: 750;
            font-size: 15px;
        }}
        #ActiveTime {{
            color: #69a7ff;
            font-weight: 800;
        }}
        #MoreText {{
            color: #aeb8d2;
            font-weight: 650;
            padding-top: 8px;
        }}
        #RankText {{
            color: #cbd5ef;
            font-size: {self._css_px(18)};
            font-weight: 800;
        }}
        #PlayerBar {{
            background-color: rgba(14, 20, 34, 235);
            border-top: 1px solid rgba(145, 163, 210, 56);
            border-bottom-left-radius: 24px;
            border-bottom-right-radius: 24px;
        }}
        #PlayerIconText {{
            color: #cbd5ef;
            font-weight: 800;
            font-size: {self._css_px(14)};
        }}
        #VolumeSlider::groove:horizontal {{
            height: 5px;
            border-radius: 3px;
            background: rgba(91, 104, 139, 61);
        }}
        #VolumeSlider::sub-page:horizontal {{
            border-radius: 3px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #6fb1ff, stop:1 #8a6cff);
        }}
        #VolumeSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
            background: #8a6cff;
        }}
        """
