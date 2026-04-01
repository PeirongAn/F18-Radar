@echo off
REM Test portable package integrity
REM Usage: test_portable_package.bat

echo Testing Radar Portable Package Integrity
echo ==================================================

set PACKAGE_DIR=radar-portable-package

REM Test 1: Check if package directory exists
echo Test 1: Checking package directory...
if exist "%PACKAGE_DIR%" (
    echo OK: Package directory found
) else (
    echo ERROR: Package directory not found
    goto :error
)

REM Test 2: Check virtual environment
echo.
echo Test 2: Checking virtual environment...
if exist "%PACKAGE_DIR%\venv\Scripts\python.exe" (
    echo OK: Virtual environment found
) else (
    echo ERROR: Virtual environment not found
    goto :error
)

REM Test 3: Check server code
echo.
echo Test 3: Checking server code...
if exist "%PACKAGE_DIR%\server\main.py" (
    echo OK: Main server file found
) else (
    echo ERROR: Main server file not found
    goto :error
)

REM Test 4: Check frontend files
echo.
echo Test 4: Checking frontend files...
if exist "%PACKAGE_DIR%\dist\index.html" (
    echo OK: Frontend files found
) else (
    echo WARNING: Frontend files not found
)

REM Test 5: Check startup scripts
echo.
echo Test 5: Checking startup scripts...
if exist "%PACKAGE_DIR%\start_radar.bat" (
    echo OK: Windows startup script found
) else (
    echo ERROR: Windows startup script not found
    goto :error
)

if exist "%PACKAGE_DIR%\start_radar.sh" (
    echo OK: Linux startup script found
) else (
    echo ERROR: Linux startup script not found
    goto :error
)

REM Test 6: Check README
echo.
echo Test 6: Checking documentation...
if exist "%PACKAGE_DIR%\README.md" (
    echo OK: README file found
) else (
    echo WARNING: README file not found
)

REM Test 7: Calculate package size
echo.
echo Test 7: Package information...
echo Package location: %PACKAGE_DIR%
for /f %%i in ('dir /s "%PACKAGE_DIR%" ^| find "File(s)"') do echo Package size: %%i

echo.
echo ==================================================
echo All tests passed! The portable package is ready for deployment.
echo.
echo Next steps:
echo 1. Copy the entire %PACKAGE_DIR% folder to target environment
echo 2. Run start_radar.bat on Windows or ./start_radar.sh on Linux/macOS
echo 3. Access the system at http://localhost:8080
echo ==================================================
pause
goto :end

:error
echo.
echo ==================================================
echo Tests failed! Please check the issues above.
echo ==================================================
pause

:end
