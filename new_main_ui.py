# main.py
"""
AI Studio - Pro
메인 실행 파일
"""
import sys
import os

# Chromium/QtWebEngine 네이티브 로그 억제 (QApplication 생성 전에 설정)
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-logging --log-level=3 --disable-features=WebRtcHideLocalIpsWithMdns",
)
os.environ.setdefault("QT_LOGGING_RULES", "qt.webenginecontext.debug=false")

from config import *
from ui.generator_main import GeneratorMainUI
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt, QEvent, QObject
from PyQt6.QtGui import QPalette, QColor, QCursor


class ButtonCursorFilter(QObject):
    """QPushButton에 마우스 올리면 포인터 커서로 변경"""
    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and obj.isEnabled():
            if event.type() == QEvent.Type.Enter:
                obj.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            elif event.type() == QEvent.Type.Leave:
                obj.unsetCursor()
        return False


def main():
    """메인 실행 함수"""
    # 윈도우 작업 표시줄 아이콘 해결 (AppUserModelID 설정)
    if sys.platform == 'win32':
        import ctypes
        myappid = 'mycompany.myproduct.subproduct.version' # 임의의 고유 ID
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("AI Studio Pro")
    app.setOrganizationName("AI Studio")

    # 앱 전역 아이콘 설정 (작업 표시줄 및 트레이 기본값)
    from PyQt6.QtGui import QIcon
    icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icons', 'app_icon.svg')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # PyQt 스타일 완전 제거 — Vue가 모든 UI 스타일링 담당
    app.setStyleSheet("")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 예외 핸들러 — 크래시 원인 로깅 (콘솔 + 파일).
    # Python 예외와 네이티브 크래시(SIGSEGV/abort/0x80000003)를 모두
    # logs/last_crash.log 에 기록해, 콘솔 창이 닫혀도 사후 확인 가능.
    import traceback, faulthandler
    from core.storage_paths import log_file
    _crash_log = str(log_file('last_crash.log', legacy_paths='config/last_crash.log'))
    _crash_fp = None
    try:
        os.makedirs(os.path.dirname(_crash_log), exist_ok=True)
        _crash_fp = open(_crash_log, 'w', encoding='utf-8', buffering=1)
        # 네이티브 크래시 시 전체 스레드 스택 자동 덤프
        faulthandler.enable(_crash_fp)
    except Exception:
        _crash_fp = None

    def _excepthook(exc_type, exc_value, exc_tb):
        print("=" * 60)
        print("UNHANDLED EXCEPTION:")
        traceback.print_exception(exc_type, exc_value, exc_tb)
        print("=" * 60)
        if _crash_fp is not None:
            try:
                _crash_fp.write("\n=== UNHANDLED PYTHON EXCEPTION ===\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=_crash_fp)
                _crash_fp.flush()
            except Exception:
                pass
    sys.excepthook = _excepthook

    window = GeneratorMainUI()
    # 스플래시 로딩 시퀀스: 백엔드 선택 → 로딩창 → 데이터 준비 → 완성된 UI.
    # (실패해도 내부 폴백으로 앱은 뜸. 시작 다이얼로그 X면 SystemExit로 종료.)
    if hasattr(window, '_run_startup_sequence'):
        window._run_startup_sequence(app)

    # 생성 API는 설정에서 명시적으로 켜 둔 경우에만 로컬 서버를 연다.
    # 위젯에 참조를 보관해 앱 수명과 gateway 수명을 일치시킨다.
    try:
        from core.generation_api import get_generation_api_manager

        generation_api_manager = get_generation_api_manager()
        window._generation_api_manager = generation_api_manager
        generation_api_manager.start_if_enabled()
        app.aboutToQuit.connect(generation_api_manager.shutdown)
    except Exception as exc:
        print(f"[Generation API] startup skipped: {exc}")
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
