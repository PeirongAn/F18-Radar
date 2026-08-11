@echo off
setlocal
chcp 65001 >nul

set "F18_ROOT=%~dp0"
set "F18_RADAR_HOME=%F18_ROOT%"
set "F18_RADAR_WEB_DIR=%F18_ROOT%web"
set "F18_RADAR_CONFIG_DIR=%F18_ROOT%web"
set "F18_RADAR_DATA_DIR=%F18_ROOT%data"
set "F18_RADAR_LOG_DIR=%F18_ROOT%logs"
set "F18_RADAR_ENV_FILE=%F18_ROOT%config\portable.env"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%F18_ROOT%runtime\F18RadarServer.exe" (
  echo [ERROR] Missing runtime\F18RadarServer.exe
  pause
  exit /b 1
)

if not exist "%F18_ROOT%web\index.html" (
  echo [ERROR] Missing web\index.html
  pause
  exit /b 1
)

start "" /b powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%F18_ROOT%tools\open_when_ready.ps1"
echo F18 Radar is starting at http://127.0.0.1:8080
echo Close this window or press Ctrl+C to stop the service.
echo Logs: %F18_ROOT%logs
echo.

"%F18_ROOT%runtime\F18RadarServer.exe" --static-dir "%F18_ROOT%web" --http-port 8080
set "F18_EXIT=%ERRORLEVEL%"

if not "%F18_EXIT%"=="0" (
  echo.
  echo [ERROR] F18 Radar exited with code %F18_EXIT%.
  echo Check the logs directory for details.
  pause
)
exit /b %F18_EXIT%
