# main.py
"""
AI Studio - Pro
메인 실행 파일
"""
import sys
import os

# Do not import project code while the detached updater is replacing the
# checkout.  A Windows kernel mutex is process-owned, so a crashed helper can
# never leave a stale startup block behind.
def _acquire_detached_update_gate(timeout_ms: int = 120_000):
    if os.name != "nt":
        return None
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.CreateMutexW(None, False, r"Local\AIStudioPro.UR_IV.Update")
    if not handle:
        raise RuntimeError("앱 업데이트 시작 잠금을 확인하지 못했습니다.")
    result = int(kernel32.WaitForSingleObject(handle, timeout_ms))
    if result not in {0x00000000, 0x00000080}:
        kernel32.CloseHandle(handle)
        raise RuntimeError("앱 업데이트가 아직 진행 중입니다. 잠시 후 다시 실행하세요.")
    return kernel32, handle


_startup_update_gate = _acquire_detached_update_gate() if __name__ == "__main__" else None
try:
    if __name__ == "__main__":
        from core.app_instance import register_app_instance

        register_app_instance(update_guarded=_startup_update_gate is not None)
finally:
    if _startup_update_gate is not None:
        _startup_update_gate[0].ReleaseMutex(_startup_update_gate[1])
        _startup_update_gate[0].CloseHandle(_startup_update_gate[1])

if __name__ == "__main__":
    from core.app_startup import prepare_application

    _prepare_result = prepare_application()
    if _prepare_result:
        from core.app_instance import unregister_app_instance

        unregister_app_instance()
        raise SystemExit(_prepare_result)

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
    try:
        with open(os.path.join(os.path.dirname(__file__), "VERSION"), encoding="utf-8") as version_file:
            app.setApplicationVersion(version_file.read().strip())
    except OSError:
        app.setApplicationVersion("0.0.0")

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
