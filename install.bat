@echo off
setlocal
cd /d "%~dp0"

set "PY_CMD="
py -3 -V >nul 2>&1 && set "PY_CMD=py -3"
if "%PY_CMD%"=="" python -V >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" python3 -V >nul 2>&1 && set "PY_CMD=python3"

if "%PY_CMD%"=="" (
    echo [ERROR] Python 3 was not found in your system PATH.
    echo Please install Python from https://www.python.org and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

%PY_CMD% "%~dp0deploy.py" %*

if "%1"=="" (
    echo.
    echo Press any key to exit...
    pause >nul
)
