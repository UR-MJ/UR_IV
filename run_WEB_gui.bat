@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 (
    echo [run] 앱 디렉터리로 이동 실패: %~dp0
    pause
    exit /b 1
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$n='Local\AIStudioPro.UR_IV.Update'; try{$m=[Threading.Mutex]::OpenExisting($n)}catch [Threading.WaitHandleCannotBeOpenedException]{exit 0}; $owned=$false; try{try{$owned=$m.WaitOne(120000)}catch [Threading.AbandonedMutexException]{$owned=$true}; if(-not $owned){exit 2}}finally{if($owned){$m.ReleaseMutex()};$m.Dispose()}"
if errorlevel 1 (
    echo [run] 앱 업데이트가 진행 중입니다. 잠시 후 다시 실행하세요.
    pause
    exit /b 1
)
REM ── 웹 모드 (브라우저로 접속, A1111 처럼 포트 오픈) ──
REM   기본: http://localhost:7800  (WebSocket 7801)
REM   기본은 이 PC에서만 접속 가능. LAN 공유가 필요하면 실행 전에
REM   set AISTUDIO_BIND=0.0.0.0 을 지정 (콘솔에 일회용 인증 URL 표시).
REM   전부 localhost/LAN 이라 인터넷은 필요 없음.
REM 로컬 창 모드는 run_gui.bat 참고.

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [run] venv 활성화 실패: venv\Scripts\activate.bat
    pause
    exit /b 1
)

python web_main_ui.py
if errorlevel 1 (
    echo.
    echo ============================================================
    echo [run] 웹 모드가 비정상 종료했습니다. 아래 크래시 로그를 확인하세요:
    echo ============================================================
    if exist logs\last_crash.log type logs\last_crash.log
    echo ============================================================
    pause
)
endlocal
