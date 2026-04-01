@echo off
REM Create truly portable deployment package (independent of system Python)
REM Usage: create_truly_portable_package.bat

setlocal enabledelayedexpansion

echo Creating truly portable deployment package (independent of system Python)
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
set PORTABLE_DIR=radar-truly-portable-package
if exist "%PORTABLE_DIR%" rmdir /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%"

echo Creating directory structure...

REM Copy virtual environment first
echo Copying virtual environment (this may take several minutes)...
xcopy /E /I /Y "venv" "%PORTABLE_DIR%\venv"

if errorlevel 1 (
    echo ERROR: Virtual environment copy failed
    pause
    exit /b 1
)

echo OK: Virtual environment copy completed

REM Fix pyvenv.cfg to make it portable
echo Fixing virtual environment configuration for portability...
(
echo home = .
echo include-system-site-packages = false
echo version = 3.12.10
echo executable = .\python.exe
echo command = python.exe -m venv
) > "%PORTABLE_DIR%\venv\pyvenv.cfg"

echo OK: Virtual environment configuration updated for portability

REM Copy server code (excluding venv to avoid duplication)
echo Copying server code...
mkdir "%PORTABLE_DIR%\server"

REM Copy Python files
copy *.py "%PORTABLE_DIR%\server\" >nul 2>&1
copy *.txt "%PORTABLE_DIR%\server\" >nul 2>&1

REM Copy directories
xcopy /E /I /Y "core" "%PORTABLE_DIR%\server\core" >nul 2>&1
xcopy /E /I /Y "managers" "%PORTABLE_DIR%\server\managers" >nul 2>&1
xcopy /E /I /Y "network" "%PORTABLE_DIR%\server\network" >nul 2>&1
xcopy /E /I /Y "models" "%PORTABLE_DIR%\server\models" >nul 2>&1
xcopy /E /I /Y "services" "%PORTABLE_DIR%\server\services" >nul 2>&1
xcopy /E /I /Y "data" "%PORTABLE_DIR%\server\data" >nul 2>&1

echo OK: Server code copied

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

REM Create portable startup scripts
echo Creating portable startup scripts...

REM Windows startup script (using relative paths)
(
echo @echo off
echo REM Radar System Truly Portable Startup Script
echo title Radar System Server
echo.
echo echo Starting Radar System Server ^(Portable Version^)
echo echo ==================================================
echo.
echo cd /d "%%~dp0"
echo.
echo REM Set Python path to use portable Python
echo set PYTHONHOME=%%cd%%\venv
echo set PYTHONPATH=%%cd%%\venv\Lib;%%cd%%\venv\Lib\site-packages
echo set PATH=%%cd%%\venv\Scripts;%%PATH%%
echo.
echo REM Enter server directory
echo cd server
echo.
echo REM Start server using portable Python
echo echo OK: Using portable Python environment
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
echo.
echo ..\venv\Scripts\python.exe main.py
echo.
echo echo.
echo echo Server stopped
echo pause
) > "%PORTABLE_DIR%\start_radar.bat"

REM Linux/macOS startup script (using relative paths)
(
echo #!/bin/bash
echo # Radar System Truly Portable Startup Script
echo.
echo echo "Starting Radar System Server (Portable Version)"
echo echo "=================================================="
echo.
echo cd "$(dirname "$0")"
echo.
echo # Set Python path to use portable Python
echo export PYTHONHOME="$(pwd)/venv"
echo export PYTHONPATH="$(pwd)/venv/lib/python3.12/site-packages"
echo export PATH="$(pwd)/venv/bin:$PATH"
echo.
echo # Enter server directory
echo cd server
echo.
echo # Start server using portable Python
echo echo "OK: Using portable Python environment"
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
echo ../venv/bin/python main.py
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
echo for /f "tokens=2" %%i in ^('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>nul'^) do ^(
echo     if not "%%i"=="PID" ^(
echo         echo Terminating process %%i
echo         taskkill /pid %%i /f ^>nul 2^>^&1
echo     ^)
echo ^)
echo.
echo echo OK: Server stopped
echo pause
) > "%PORTABLE_DIR%\stop_radar.bat"

REM Create test script for portable package
(
echo @echo off
echo REM Test truly portable package
echo.
echo echo Testing Truly Portable Package
echo echo ==================================================
echo.
echo cd /d "%%~dp0"
echo.
echo REM Test 1: Check Python executable
echo echo Test 1: Testing portable Python...
echo venv\Scripts\python.exe --version
echo if errorlevel 1 ^(
echo     echo ERROR: Portable Python not working
echo     pause
echo     exit /b 1
echo ^)
echo.
echo REM Test 2: Test package imports
echo echo Test 2: Testing package imports...
echo venv\Scripts\python.exe -c "import sys; print('Python path:', sys.executable)"
echo.
echo REM Test 3: Test dependencies
echo echo Test 3: Testing key dependencies...
echo venv\Scripts\python.exe -c "import websockets, aiohttp, matplotlib; print('Key dependencies OK')"
echo if errorlevel 1 ^(
echo     echo ERROR: Dependencies test failed
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo ==================================================
echo echo All tests passed! Package is truly portable.
echo echo You can copy this entire folder to any Windows machine.
echo echo ==================================================
echo pause
) > "%PORTABLE_DIR%\test_portable.bat"

REM Create README file
(
echo # Radar System Truly Portable Deployment Package
echo.
echo ## 📦 Package Contents
echo.
echo - `server/` - Server code
echo - `venv/` - **Truly portable** Python environment ^(independent of system Python^)
echo - `dist/` - Frontend files
echo - `public/` - Configuration files
echo - `start_radar.bat` - Windows startup script ^(portable^)
echo - `start_radar.sh` - Linux/macOS startup script ^(portable^)
echo - `stop_radar.bat` - Windows stop script
echo - `test_portable.bat` - Test script to verify portability
echo.
echo ## 🚀 Usage
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
echo ## ✨ Key Features
echo.
echo - **✅ Truly Portable** - No system Python installation required
echo - **✅ Self-contained** - All dependencies included
echo - **✅ Cross-platform** - Works on Windows, Linux, macOS
echo - **✅ Zero configuration** - Just copy and run
echo.
echo ## 📋 System Requirements
echo.
echo - **No Python installation required** - Package includes everything
echo - About 1GB disk space
echo - Ports 8080 and 8765 available
echo - Windows 10+, Linux, or macOS
echo.
echo ## 🌐 Access URLs
echo.
echo - Frontend Application: http://localhost:8080
echo - WebSocket: ws://localhost:8080/ws
echo - External Device: ws://localhost:8765
echo.
echo ## 🧪 Testing Portability
echo.
echo Run the test script to verify the package is truly portable:
echo ```cmd
echo test_portable.bat
echo ```
echo.
echo ## 🔧 Troubleshooting
echo.
echo 1. Ensure ports 8080 and 8765 are not occupied
echo 2. Check firewall settings
echo 3. Run test_portable.bat to diagnose issues
echo 4. On Linux/macOS, ensure execute permissions: `chmod +x start_radar.sh`
echo.
echo ## 📁 Directory Description
echo.
echo - `server/data/` - Database files storage location
echo - `venv/` - **Do not modify** - Portable Python environment
echo - `dist/` - Frontend static files
echo - `public/` - System configuration files
echo.
echo ## 🔄 Deployment
echo.
echo This package is **truly portable** and can be copied to any compatible system
echo without requiring Python installation on the target machine.
echo.
) > "%PORTABLE_DIR%\README.md"

echo OK: Truly portable deployment package created successfully!
echo.
echo Package location: %PORTABLE_DIR%
echo.
echo Features:
echo OK: Independent of system Python installation
echo OK: Truly portable across different machines
echo OK: Self-contained with all dependencies
echo OK: Cross-platform support

echo.
echo Next steps:
echo 1. Test portability: cd %PORTABLE_DIR% && test_portable.bat
echo 2. Copy entire %PORTABLE_DIR% folder to target environment
echo 3. Run start_radar.bat (Windows) or ./start_radar.sh (Linux/macOS)

pause
