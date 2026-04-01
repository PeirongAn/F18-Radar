@echo off
REM Test script to verify venv-based deployment scripts
REM Usage: test_venv_scripts.bat

echo Testing venv-based deployment scripts
echo ==================================================

REM Test 1: Check if venv exists
echo Test 1: Checking virtual environment...
if exist "venv" (
    echo OK: Virtual environment found at server/venv
) else (
    echo ERROR: Virtual environment not found at server/venv
    goto :error
)

REM Test 2: Check if venv is functional
echo.
echo Test 2: Testing virtual environment functionality...
call venv\Scripts\activate.bat
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not working in virtual environment
    goto :error
) else (
    echo OK: Python working in virtual environment
)

REM Test 3: Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip not available in virtual environment
    goto :error
) else (
    echo OK: pip available in virtual environment
)

REM Test 4: Check requirements.txt
echo.
echo Test 3: Checking requirements.txt...
if exist "requirements.txt" (
    echo OK: requirements.txt found
    echo Contents:
    type requirements.txt | findstr /n ".*"
) else (
    echo ERROR: requirements.txt not found
    goto :error
)

REM Test 5: Check frontend files
echo.
echo Test 4: Checking frontend files...
if exist "..\dist" (
    echo OK: Frontend files found at ../dist
) else (
    echo WARNING: Frontend files not found at ../dist
    echo TIP: Run 'npm run build' or 'pnpm build' to create frontend files
)

REM Test 6: Check config files
echo.
echo Test 5: Checking config files...
if exist "..\public" (
    echo OK: Config files found at ../public
) else (
    echo INFO: Config files not found at ../public (optional)
)

deactivate

echo.
echo ==================================================
echo All tests passed! You can now use:
echo - create_portable_package_venv.bat (for portable deployment)
echo - create_offline_package_venv.bat (for offline package deployment)
echo ==================================================
pause
goto :end

:error
deactivate
echo.
echo ==================================================
echo Tests failed! Please check the issues above.
echo ==================================================
pause

:end
