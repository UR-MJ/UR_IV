@echo off
setlocal

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [run] Failed to activate venv at venv\Scripts\activate.bat
    pause
    exit /b 1
)

python core\check_requirements.py
if errorlevel 1 (
    echo [run] Dependency check/install failed. See log above.
    pause
    exit /b 1
)

python core\fetch_data.py
if errorlevel 1 (
    echo [run] Data fetch failed. See log above.
    pause
    exit /b 1
)

python new_main_ui.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo [run] 앱이 비정상 종료했습니다. 아래 크래시 로그를 확인하세요:
    echo ============================================================
    if exist config\last_crash.log type config\last_crash.log
    echo ============================================================
    pause
)
endlocal
