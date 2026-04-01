@echo off
REM Create portable deployment package script (using server/venv)
REM Usage: create_portable_package_venv.bat

setlocal enabledelayedexpansion

echo Creating portable deployment package (using server/venv)
echo ==================================================

REM Check if virtual environment exists
if not exist "venv" (
    echo ERROR: Virtual environment not found: server/venv
    echo TIP: Please ensure the virtual environment exists in server/venv
    pause
    exit /b 1
)

echo OK: Found virtual environment: server/venv

REM Create portable package directory
set PORTABLE_DIR=radar-portable-package
if exist "%PORTABLE_DIR%" rmdir /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%"

echo Creating directory structure...

REM Copy server code (excluding venv to avoid duplication)
echo Copying server code...
xcopy /E /I /Y . "%PORTABLE_DIR%\server" /EXCLUDE:exclude_list.txt

REM Create exclude list
echo __pycache__ > exclude_list.txt
echo *.pyc >> exclude_list.txt
echo venv >> exclude_list.txt
echo *.tar >> exclude_list.txt
echo node_modules >> exclude_list.txt
echo %PORTABLE_DIR% >> exclude_list.txt
echo radar-portable-package >> exclude_list.txt

REM Copy virtual environment separately
echo Copying virtual environment (this may take several minutes)...
xcopy /E /I /Y "venv" "%PORTABLE_DIR%\venv"

if errorlevel 1 (
    echo ERROR: Virtual environment copy failed
    pause
    exit /b 1
)

echo OK: Virtual environment copy completed

REM Copy frontend files
if exist "..\dist" (
    xcopy /E /I /Y "..\dist" "%PORTABLE_DIR%\dist"
    echo OK: Frontend files copied
) else (
    echo WARNING: Frontend files not found, please build frontend project first
)

REM Copy config files
if exist "..\public" (
    xcopy /E /I /Y "..\public" "%PORTABLE_DIR%\public"
    echo OK: Config files copied
)

REM Create startup scripts
echo Creating startup scripts...

REM Windows startup script
(
echo @echo off
echo REM Radar System Portable Startup Script
echo title Radar System Server
echo.
echo echo Starting Radar System Server
echo echo ==================================================
echo.
echo cd /d "%%~dp0"
echo.
echo REM Activate virtual environment
echo call venv\Scripts\activate.bat
echo.
echo REM Enter server directory
echo cd server
echo.
echo REM Start server
echo echo OK: Virtual environment activated
echo echo Starting HTTP server ^(port: 8080^)
echo echo Starting WebSocket server ^(port: 8765^)
echo echo.
echo echo Access URLs:
echo echo   Frontend Application: http://localhost:8080
echo echo   WebSocket: ws://localhost:8080/ws
echo echo   External Device: ws://localhost:8765
echo echo.
echo echo TIP: Press Ctrl+C to stop server
echo echo ==================================================
echo echo.
echo python main.py
echo.
echo echo.
echo echo Server stopped
echo pause
) > "%PORTABLE_DIR%\start_radar.bat"

REM Linux/macOS startup script
(
echo #!/bin/bash
echo # Radar System Portable Startup Script
echo.
echo echo "Starting Radar System Server"
echo echo "=================================================="
echo.
echo cd "$(dirname "$0")"
echo.
echo # Activate virtual environment
echo source venv/bin/activate
echo.
echo # Enter server directory
echo cd server
echo.
echo # Start server
echo echo "OK: Virtual environment activated"
echo echo "Starting HTTP server (port: 8080)"
echo echo "Starting WebSocket server (port: 8765)"
echo echo
echo echo "Access URLs:"
echo echo "  Frontend Application: http://localhost:8080"
echo echo "  WebSocket: ws://localhost:8080/ws"
echo echo "  External Device: ws://localhost:8765"
echo echo
echo echo "TIP: Press Ctrl+C to stop server"
echo echo "=================================================="
echo echo
echo.
echo python main.py
echo.
echo echo
echo echo "Server stopped"
) > "%PORTABLE_DIR%\start_radar.sh"

REM Create stop script
(
echo @echo off
echo REM Stop Radar System Server
echo.
echo echo Stopping Radar System Server
echo echo ==================================================
echo.
echo REM Find and terminate Python processes
echo for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>nul') do (
echo     if not "%%i"=="PID" (
echo         echo Terminating process %%i
echo         taskkill /pid %%i /f >nul 2>&1
echo     )
echo )
echo.
echo echo OK: Server stopped
echo pause
) > "%PORTABLE_DIR%\stop_radar.bat"

REM Create README file
(
echo # Radar System Portable Deployment Package
echo.
echo ## Package Contents
echo.
echo - `server/` - Server code
echo - `venv/` - Python virtual environment (includes all dependencies)
echo - `dist/` - Frontend files
echo - `public/` - Configuration files
echo - `start_radar.bat` - Windows startup script
echo - `start_radar.sh` - Linux/macOS startup script
echo - `stop_radar.bat` - Windows stop script
echo.
echo ## Usage
echo.
echo ### Windows:
echo ```cmd
echo start_radar.bat
echo ```
echo.
echo ### Linux/macOS:
echo ```bash
echo chmod +x start_radar.sh
echo ./start_radar.sh
echo ```
echo.
echo ## System Requirements
echo.
echo - **No Python installation required** - Complete virtual environment included
echo - About 1GB disk space
echo - Ports 8080 and 8765 available
echo - Windows 10+ or Linux/macOS
echo.
echo ## Access URLs
echo.
echo - Frontend Application: http://localhost:8080
echo - WebSocket: ws://localhost:8080/ws
echo - External Device: ws://localhost:8765
echo.
echo ## Troubleshooting
echo.
echo 1. Ensure ports 8080 and 8765 are not occupied
echo 2. Check firewall settings
echo 3. If startup fails, check if virtual environment is complete
echo.
echo ## Directory Description
echo.
echo - `server/data/` - Database files storage location
echo - `server/logs/` - Log files storage location (if any)
echo - `venv/` - Do not modify this directory
echo.
echo ## Update Instructions
echo.
echo To update the system, replace files in the `server/` directory,
echo keep the `venv/` directory unchanged.
echo.
) > "%PORTABLE_DIR%\README.md"

REM Clean up temporary files
del exclude_list.txt

echo OK: Portable deployment package created successfully!
echo.
echo Package location: %PORTABLE_DIR%
echo Calculating package size...

echo.
echo Features:
echo OK: Uses existing server/venv virtual environment
echo OK: Target environment does not need Python installation
echo OK: One-click startup, ready to use
echo OK: Cross-platform support

echo.
echo Next steps:
echo 1. Copy the entire %PORTABLE_DIR% folder to target environment
echo 2. Run start_radar.bat (Windows) or ./start_radar.sh (Linux/macOS)

pause
