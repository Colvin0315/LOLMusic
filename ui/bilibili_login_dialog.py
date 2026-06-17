from __future__ import annotations

from io import BytesIO

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.bilibili import BilibiliClient, BilibiliError, BilibiliLoginPoll, BilibiliQrLogin


class BilibiliTaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class BilibiliQrStartTask(QRunnable):
    def __init__(self, client: BilibiliClient) -> None:
        super().__init__()
        self.client = client
        self.signals = BilibiliTaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.client.start_qr_login())
        except BilibiliError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"B站登录初始化失败：{exc}")


class BilibiliQrPollTask(QRunnable):
    def __init__(self, client: BilibiliClient, qrcode_key: str) -> None:
        super().__init__()
        self.client = client
        self.qrcode_key = qrcode_key
        self.signals = BilibiliTaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.client.poll_qr_login(self.qrcode_key))
        except BilibiliError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"B站登录轮询失败：{exc}")


class BilibiliLoginDialog(QDialog):
    login_succeeded = Signal(object)

    def __init__(self, client: BilibiliClient, thread_pool: QThreadPool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.thread_pool = thread_pool
        self.qrcode_key: str | None = None
        self._polling = False

        self.setWindowTitle("B站扫码登录")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        title = QLabel("使用哔哩哔哩 App 扫码登录")
        title.setObjectName("DialogTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.qr_label = QLabel("正在生成二维码...")
        self.qr_label.setObjectName("QrBox")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(260, 260)
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("请稍候")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("刷新二维码")
        self.close_button = QPushButton("关闭")
        self.refresh_button.clicked.connect(self.refresh)
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1800)
        self.poll_timer.timeout.connect(self._poll)

        self.setStyleSheet(
            """
            QDialog {
                background: #0b0f1a;
                color: #f6f8ff;
                font-family: "Microsoft YaHei UI", "Segoe UI";
            }
            #DialogTitle {
                font-size: 18px;
                font-weight: 800;
            }
            #QrBox {
                background: #ffffff;
                border-radius: 8px;
                color: #131826;
            }
            QPushButton {
                min-height: 34px;
                border-radius: 8px;
                color: #ffffff;
                background: rgba(125, 148, 199, 80);
                border: 1px solid rgba(147, 166, 210, 80);
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(137, 108, 255, 100);
            }
            """
        )

        self.refresh()

    def reject(self) -> None:
        self.poll_timer.stop()
        super().reject()

    def refresh(self) -> None:
        self.poll_timer.stop()
        self.qrcode_key = None
        self._polling = False
        self.refresh_button.setEnabled(False)
        self.status_label.setText("正在生成二维码...")
        self.qr_label.setText("加载中")
        task = BilibiliQrStartTask(self.client)
        task.signals.finished.connect(self._on_qr_ready)
        task.signals.failed.connect(self._on_error)
        self.thread_pool.start(task)

    def _on_qr_ready(self, login: BilibiliQrLogin) -> None:
        self.qrcode_key = login.qrcode_key
        self.refresh_button.setEnabled(True)
        self.status_label.setText("请使用 B 站 App 扫描二维码")
        self._set_qr_image(login.url)
        self.poll_timer.start()

    def _poll(self) -> None:
        if self._polling or self.qrcode_key is None:
            return
        self._polling = True
        task = BilibiliQrPollTask(self.client, self.qrcode_key)
        task.signals.finished.connect(self._on_poll_result)
        task.signals.failed.connect(self._on_poll_error)
        self.thread_pool.start(task)

    def _on_poll_result(self, result: BilibiliLoginPoll) -> None:
        self._polling = False
        self.status_label.setText(result.message)
        if result.expired:
            self.poll_timer.stop()
            self.refresh_button.setEnabled(True)
            return
        if result.profile is not None:
            self.poll_timer.stop()
            self.login_succeeded.emit(result.profile)
            self.accept()

    def _on_poll_error(self, message: str) -> None:
        self._polling = False
        self._on_error(message)

    def _on_error(self, message: str) -> None:
        self.poll_timer.stop()
        self.refresh_button.setEnabled(True)
        self.status_label.setText(message)
        self.qr_label.setText("二维码加载失败")

    def _set_qr_image(self, url: str) -> None:
        try:
            import qrcode
        except ImportError:
            self.qr_label.setText("缺少 qrcode 依赖\n请先安装 requirements.txt")
            self.status_label.setText(url)
            self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return

        image = qrcode.make(url).resize((240, 240))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.qr_label.setPixmap(pixmap)
