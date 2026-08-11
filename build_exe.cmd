@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1" %*
set "BUILD_EXIT=%ERRORLEVEL%"

if not "%BUILD_EXIT%"=="0" (
  echo.
  echo Build failed with exit code %BUILD_EXIT%.
  pause
  exit /b %BUILD_EXIT%
)

echo.
echo Build completed successfully.
pause
exit /b 0
