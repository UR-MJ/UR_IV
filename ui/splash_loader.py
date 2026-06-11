# ui/splash_loader.py
"""시작 로딩 스플래시 — 백엔드 선택 후 '얼마나 로딩됐는지' 시각 표시.

main()이 _run_startup_sequence에서 직접 step()/close()를 호출한다. app.exec() 전
(부트스트랩) 단계에서 쓰이므로, 갱신 직후 QApplication.processEvents()로 즉시 다시 그린다.
순수 위젯 — 비즈니스 로직 없음.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt


class SplashLoader(QWidget):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen,
        )
        self.setFixedSize(440, 190)
        self.setStyleSheet(
            "QWidget { background: #0D0D0D; border: 1px solid #333; border-radius: 14px; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 26, 30, 26)
        lay.setSpacing(12)

        title = QLabel("\U0001F680  AI Studio Pro")
        title.setStyleSheet("color:#FACC15; font-size:19px; font-weight:800; border:none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        lay.addStretch()

        self._status = QLabel("초기화 중…")
        self._status.setStyleSheet("color:#B0B0B0; font-size:12px; border:none;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            "QProgressBar { background:#1A1A1A; border:none; border-radius:4px; }"
            "QProgressBar::chunk { background:#FACC15; border-radius:4px; }"
        )
        lay.addWidget(self._bar)

        self._center_on_screen()

    def _center_on_screen(self):
        try:
            from PyQt6.QtGui import QGuiApplication
            scr = QGuiApplication.primaryScreen().availableGeometry()
            self.move(scr.center().x() - self.width() // 2,
                      scr.center().y() - self.height() // 2)
        except Exception:
            pass

    def step(self, message: str, pct: int = None):
        """상태 텍스트 + 진행률 갱신."""
        try:
            self._status.setText(message)
            if pct is not None:
                self._bar.setValue(max(0, min(100, int(pct))))
        except Exception:
            pass
