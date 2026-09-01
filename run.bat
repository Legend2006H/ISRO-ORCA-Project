@echo off
title ORCA Marine Intelligence Platform
echo ========================================================
echo         ORCA Marine Intelligence Platform
echo ========================================================
echo.

cd /d "%~dp0"

REM 1. Locate Python executable
set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py"
    ) else (
        echo [ERROR] Python was not found in PATH.
        echo Please install Python 3.10 or higher.
        pause
        exit /b 1
    )
)

REM 2. Prefer an existing working Python installation
set "VENV_PYTHON=%PYTHON_CMD%"
%VENV_PYTHON% -c "import fastapi, uvicorn, pandas, pydantic, xlrd, httpx" >nul 2>nul
if not errorlevel 1 (
    echo [OK] Using the existing Python environment.
    echo.
    goto :runtime_ready
)

REM 3. Check or create virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment not found. Creating venv...
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created.
    echo.
)

REM 4. Use the virtual environment explicitly
set "VENV_PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment was not created correctly.
    pause
    exit /b 1
)

:runtime_ready

REM 5. Check if required packages are installed
"%VENV_PYTHON%" -c "import fastapi, uvicorn, pandas, pydantic, xlrd, httpx" >nul 2>nul
if errorlevel 1 goto :install_dependencies
"%VENV_PYTHON%" -m pip check >nul 2>nul
if errorlevel 1 goto :install_dependencies
echo [OK] All required dependencies are installed.
echo.
goto :dependencies_ready

:install_dependencies
    echo [INFO] Required dependencies not detected. Installing requirements...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Package installation failed. Please check network/pip setup.
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed successfully.
    echo.

:dependencies_ready

REM 6. Reuse an already-running healthy server
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8000/health | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
    echo [OK] ORCA is already running. Opening the dashboard...
    start "" "http://127.0.0.1:8000/"
    exit /b 0
)

REM 7. Start FastAPI application, then wait until it is ready
echo [INFO] Starting ORCA Marine Intelligence Platform...
start "ORCA Server" "%VENV_PYTHON%" -m uvicorn api.main:app --host 127.0.0.1 --port 8000

set "SERVER_READY=0"
for /L %%I in (1,1,30) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8000/health | Out-Null; exit 0 } catch { exit 1 }"
    if not errorlevel 1 (
        set "SERVER_READY=1"
        goto :server_ready
    )
    timeout /t 1 /nobreak >nul
)

if "%SERVER_READY%" neq "1" (
    echo [ERROR] ORCA did not become ready at http://127.0.0.1:8000/
    echo Check the ORCA Server window for details.
    pause
    exit /b 1
)

:server_ready
echo [OK] Server is ready. Opening dashboard in your browser...
start "" "http://127.0.0.1:8000/"

exit /b 0
