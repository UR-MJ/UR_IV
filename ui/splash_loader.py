# ui/splash_loader.py
"""시작 로딩 스플래시 — 백엔드 선택 후 '얼마나 로딩됐는지' 시각 표시.

main()이 _run_startup_sequence에서 직접 step()/close()를 호출한다. app.exec() 전
(부트스트랩) 단계에서 쓰이므로, 갱신 직후 QApplication.processEvents()로 즉시 다시 그린다.
순수 위젯 — 비즈니스 로직 없음.

색은 하드코딩하지 않고 get_color()를 거친다 — 사용자가 고른 테마는 Vue가 뜨기
전인 이 화면에도 적용돼야 한다. (테마 색의 원본은 core/theme_presets.)
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from utils.theme_manager import get_color


class SplashLoader(QWidget):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen,
        )
        self.setFixedSize(400, 168)

        text_primary = get_color('text_primary')
        text_secondary = get_color('text_secondary')

        # 컨테이너 배경은 QWidget 선택자로 준다(자식까지 상속되므로 자식마다 border:none 으로 되돌림).
        # 테두리는 rule(헤어라인)이 아니라 border_strong — 창틀 없이 바탕화면 위에 뜨는
        # 창이라 가장자리가 보이지 않으면 어디까지가 창인지 알 수 없다.
        self.setStyleSheet(
            f"QWidget {{ background: {get_color('bg_card')};"
            f" border: 1px solid {get_color('border_strong')}; border-radius: 12px; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(8)

        # 전각 대문자 영문은 이 화면에서 여기 하나뿐.
        title = QLabel("AI STUDIO PRO")
        title.setStyleSheet(
            f"color:{text_primary}; font-size:16px; font-weight:600; border:none;"
        )
        # letter-spacing 은 QSS 에 없는 속성이라 QFont 로 준다.
        title_font = title.font()
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        lay.addStretch()

        self._status = QLabel("초기화 중…")
        self._status.setStyleSheet(f"color:{text_secondary}; font-size:12px; border:none;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background:{get_color('bg_input')}; border:none; border-radius:2px; }}"
            f"QProgressBar::chunk {{ background:{get_color('accent')}; border-radius:2px; }}"
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
