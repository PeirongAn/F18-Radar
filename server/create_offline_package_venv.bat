@echo off
REM Create Python offline deployment package script (using server/venv)
REM Usage: create_offline_package_venv.bat

setlocal enabledelayedexpansion

echo Creating Python offline deployment package (using server/venv)
echo ==================================================

REM Check if virtual environment exists
if not exist "venv" (
    echo ERROR: Virtual environment not found: server/venv
    echo TIP: Please ensure the virtual environment exists in server/venv
    pause
    exit /b 1
)

echo OK: Found virtual environment: server/venv

REM Activate virtual environment to use its pip
call venv\Scripts\activate.bat

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip not available in virtual environment
    pause
    exit /b 1
)

echo OK: Virtual environment activated, pip available

REM Create offline package directory
set OFFLINE_DIR=radar-offline-package
if exist "%OFFLINE_DIR%" rmdir /s /q "%OFFLINE_DIR%"
mkdir "%OFFLINE_DIR%"

echo Creating directory structure...

REM Copy server code
xcopy /E /I /Y . "%OFFLINE_DIR%\server" /EXCLUDE:exclude_list.txt

REM Create exclude list
echo __pycache__ > exclude_list.txt
echo *.pyc >> exclude_list.txt
echo venv >> exclude_list.txt
echo *.tar >> exclude_list.txt
echo node_modules >> exclude_list.txt
echo %OFFLINE_DIR% >> exclude_list.txt
echo radar-portable-package >> exclude_list.txt

REM Copy frontend files
if exist "..\dist" (
    xcopy /E /I /Y "..\dist" "%OFFLINE_DIR%\dist"
    echo OK: Frontend files copied
) else (
    echo WARNING: Frontend files not found, please build frontend project first
)

REM Copy config files
if exist "..\public" (
    xcopy /E /I /Y "..\public" "%OFFLINE_DIR%\public"
    echo OK: Config files copied
)

REM Download Python dependencies
echo Downloading Python dependencies...
mkdir "%OFFLINE_DIR%\python-packages"

REM Use pip download to get all dependencies
pip download -r requirements.txt -d "%OFFLINE_DIR%\python-packages"

if errorlevel 1 (
    echo ERROR: Dependencies download failed
    pause
    exit /b 1
)

echo OK: Python dependencies downloaded

REM Create offline installation script
echo Creating offline installation script...

REM Windows installation script
(
echo @echo off
echo REM Radar System Offline Installation Script
echo REM Usage: install_offline.bat
echo.
echo echo Radar System Offline Installation
echo echo ==================================================
echo.
echo REM Check Python
echo python --version ^>nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo ERROR: Python not installed, please install Python 3.12+ first
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo OK: Python version check passed
echo.
echo REM Create virtual environment
echo echo Creating virtual environment...
echo python -m venv venv
echo.
echo REM Activate virtual environment and install dependencies
echo echo Installing Python dependencies...
echo call venv\Scripts\activate.bat
echo pip install --no-index --find-links python-packages -r server\requirements.txt
echo.
echo if errorlevel 1 ^(
echo     echo ERROR: Dependencies installation failed
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo OK: Dependencies installation completed
echo.
echo REM Create startup script
echo echo Creating startup script...
echo ^(
echo echo @echo off
echo echo title Radar System Server
echo echo cd /d "%%~dp0"
echo echo call venv\Scripts\activate.bat
echo echo cd server
echo echo echo Starting Radar System Server...
echo echo echo Access URLs:
echo echo echo   Frontend: http://localhost:8080
echo echo echo   WebSocket: ws://localhost:8080/ws
echo echo echo   External Device: ws://localhost:8765
echo echo echo Press Ctrl+C to stop server
echo echo echo ==================================================
echo echo python main.py
echo echo pause
echo ^) ^> start_radar.bat
echo.
echo echo Installation completed!
echo echo.
echo echo Usage Instructions:
echo echo 1. Run start_radar.bat to start server
echo echo 2. Access http://localhost:8080 to use system
echo echo 3. WebSocket port: ws://localhost:8080/ws
echo echo 4. External device port: 8765
echo.
echo pause
) > "%OFFLINE_DIR%\install_offline.bat"

REM Linux/macOS installation script
(
echo #!/bin/bash
echo # Radar System Offline Installation Script
echo # Usage: chmod +x install_offline.sh && ./install_offline.sh
echo.
echo echo "Radar System Offline Installation"
echo echo "=================================================="
echo.
echo # Check Python
echo if ! command -v python3 ^&^> /dev/null; then
echo     echo "ERROR: Python3 not installed, please install Python 3.12+ first"
echo     exit 1
echo fi
echo.
echo echo "OK: Python version check passed"
echo.
echo # Create virtual environment
echo echo "Creating virtual environment..."
echo python3 -m venv venv
echo.
echo # Activate virtual environment and install dependencies
echo echo "Installing Python dependencies..."
echo source venv/bin/activate
echo pip install --no-index --find-links python-packages -r server/requirements.txt
echo.
echo if [ $? -ne 0 ]; then
echo     echo "ERROR: Dependencies installation failed"
echo     exit 1
echo fi
echo.
echo echo "OK: Dependencies installation completed"
echo.
echo # Create startup script
echo echo "Creating startup script..."
echo cat ^> start_radar.sh ^<^< 'EOF'
echo #!/bin/bash
echo cd "$(dirname "$0")"
echo source venv/bin/activate
echo cd server
echo echo "Starting Radar System Server..."
echo echo "Access URLs:"
echo echo "  Frontend: http://localhost:8080"
echo echo "  WebSocket: ws://localhost:8080/ws"
echo echo "  External Device: ws://localhost:8765"
echo echo "Press Ctrl+C to stop server"
echo echo "=================================================="
echo python main.py
echo EOF
echo.
echo chmod +x start_radar.sh
echo.
echo echo "Installation completed!"
echo echo
echo echo "Usage Instructions:"
echo echo "1. Run ./start_radar.sh to start server"
echo echo "2. Access http://localhost:8080 to use system"
echo echo "3. WebSocket port: ws://localhost:8080/ws"
echo echo "4. External device port: 8765"
echo.
) > "%OFFLINE_DIR%\install_offline.sh"

REM Create README file
(
echo # Radar System Offline Deployment Package
echo.
echo ## Package Contents
echo.
echo - `server/` - Server code
echo - `dist/` - Frontend files
echo - `public/` - Configuration files
echo - `python-packages/` - Python dependency packages
echo - `install_offline.bat` - Windows installation script
echo - `install_offline.sh` - Linux/macOS installation script
echo.
echo ## Installation Steps
echo.
echo ### Windows:
echo ```cmd
echo install_offline.bat
echo ```
echo.
echo ### Linux/macOS:
echo ```bash
echo chmod +x install_offline.sh
echo ./install_offline.sh
echo ```
echo.
echo ## System Requirements
echo.
echo - Python 3.12+
echo - About 500MB disk space
echo - Ports 8080 and 8765 available
echo.
echo ## Access URLs
echo.
echo - Frontend Application: http://localhost:8080
echo - WebSocket: ws://localhost:8080/ws
echo - External Device: ws://localhost:8765
echo.
echo ## Troubleshooting
echo.
echo 1. Ensure Python 3.12+ is installed
echo 2. Ensure ports 8080 and 8765 are not occupied
echo 3. Check firewall settings
echo 4. If installation fails, check internet connection for initial setup
echo.
echo ## Notes
echo.
echo - This package was created using dependencies from server/venv
echo - All required packages are included in python-packages/ directory
echo - No internet connection required during installation
echo.
) > "%OFFLINE_DIR%\README.md"

REM Deactivate virtual environment
deactivate

REM Clean up temporary files
del exclude_list.txt

echo OK: Offline deployment package created successfully!
echo.
echo Package location: %OFFLINE_DIR%
echo.
echo Package contents:
echo - Server code and configuration
echo - Frontend files (if available)
echo - All Python dependencies (offline)
echo - Installation scripts for Windows and Linux/macOS

echo.
echo Next steps:
echo 1. Copy the entire %OFFLINE_DIR% folder to target environment
echo 2. Run install_offline.bat (Windows) or ./install_offline.sh (Linux/macOS)
echo 3. Use generated start_radar script to run the server

pause
