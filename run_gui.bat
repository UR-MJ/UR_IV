@echo off
setlocal
REM ── 로컬 창 모드 (PyQt 창 안의 Vue) ──
REM 웹 모드는 run_WEB_gui.bat 참고.

cd /d "%~dp0"
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$n='Local\AIStudioPro.UR_IV.Update'; try{$m=[Threading.Mutex]::OpenExisting($n)}catch [Threading.WaitHandleCannotBeOpenedException]{exit 0}; $owned=$false; try{try{$owned=$m.WaitOne(120000)}catch [Threading.AbandonedMutexException]{$owned=$true}; if(-not $owned){exit 2}}finally{if($owned){$m.ReleaseMutex()};$m.Dispose()}"
if errorlevel 1 (
    echo [run] 앱 업데이트가 진행 중입니다. 잠시 후 다시 실행하세요.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [run] venv 활성화 실패: venv\Scripts\activate.bat
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
