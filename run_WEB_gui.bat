@echo off
setlocal
REM ── 웹 모드 (브라우저로 접속, A1111 처럼 포트 오픈) ──
REM   기본: http://localhost:7800  (WebSocket 7801)
REM   같은 공유기의 폰/다른 PC 에서도 http://<이 PC IP>:7800 으로 접속 가능.
REM   전부 localhost/LAN 이라 인터넷은 필요 없음.
REM 로컬 창 모드는 run_gui.bat 참고.

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

python web_main_ui.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo [run] 웹 모드가 비정상 종료했습니다. 아래 크래시 로그를 확인하세요:
    echo ============================================================
    if exist config\last_crash.log type config\last_crash.log
    echo ============================================================
    pause
)
endlocal
