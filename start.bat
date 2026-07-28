@echo off
REM Voice Generator - normal launch (built app, no DevTools)
REM Double-click to start.
cd /d "%~dp0frontend"
REM Always rebuild: it only takes a few seconds and guarantees the built UI
REM matches the current source (a stale dist/ silently shows the old UI).
echo [setup] Building UI...
call npm run build
if errorlevel 1 (
  echo [error] Build failed.
  pause
  exit /b 1
)
echo [start] Launching Voice Generator...
call npm start
if errorlevel 1 pause