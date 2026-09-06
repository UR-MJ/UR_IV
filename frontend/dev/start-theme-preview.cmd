@echo off
setlocal
cd /d "%~dp0.."

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is required to run this development preview.
  pause
  exit /b 1
)
if not exist "node_modules\vite\bin\vite.js" (
  echo Dependencies are missing. Run npm install in the frontend folder first.
  pause
  exit /b 1
)
if not exist "dev\theme-audit.html" (
  echo Missing dev\theme-audit.html. Restore the preview files first.
  pause
  exit /b 1
)
if not exist "dev\theme-audit.js" (
  echo Missing dev\theme-audit.js. Restore the preview files first.
  pause
  exit /b 1
)

echo Theme preview: http://127.0.0.1:5174/dev/theme-audit.html
echo Keep this window open while using the preview. Press Ctrl+C to stop.
echo If port 5174 is already in use, check the existing preview before retrying.
call npm run dev -- --host 127.0.0.1 --port 5174 --strictPort --open /dev/theme-audit.html
if errorlevel 1 pause
endlocal
