@echo off
REM Voice Generator - normal launch (built app, no DevTools)
REM Double-click to start.
cd /d "%~dp0frontend"
if not exist "dist\index.html" (
  echo [setup] Building UI...
  call npm run build
  if errorlevel 1 (
    echo [error] Build failed.
    pause
    exit /b 1
  )
)
echo [start] Launching Voice Generator...
call npm start
if errorlevel 1 pause