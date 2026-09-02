@echo off
setlocal
REM ── 로컬 창 모드 (PyQt 창 안의 Vue) ──
REM 웹 모드는 run_WEB_gui.bat 참고.

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [run] venv 활성화 실패: venv\Scripts\activate.bat
    pause
    exit /b 1
)

python core\check_requirements.py
if errorlevel 1 (
    echo [run] 의존성 점검/설치 실패. 위 로그 확인.
    pause
    exit /b 1
)

python core\fetch_data.py
if errorlevel 1 (
    echo [run] 데이터 페치 실패. 위 로그 확인.
    pause
    exit /b 1
)

python new_main_ui.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo [run] 앱이 비정상 종료했습니다. 아래 크래시 로그를 확인하세요:
    echo ============================================================
    if exist logs\last_crash.log type logs\last_crash.log
    echo ============================================================
    pause
)
endlocal
