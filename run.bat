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

REM 2. Check or create virtual environment
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

REM 3. Activate virtual environment
call venv\Scripts\activate.bat

REM 4. Check if required packages are installed
%PYTHON_CMD% -c "import fastapi, uvicorn, pandas, pydantic, xlrd, httpx, multipart" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Required dependencies not detected. Installing requirements...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Package installation failed. Please check network/pip setup.
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed successfully.
    echo.
) else (
    echo [OK] All required dependencies are installed.
    echo.
)

REM 5. Launch Dashboard in Default Browser
echo [INFO] Starting ORCA Marine Intelligence Platform...
echo [INFO] Opening dashboard at http://127.0.0.1:8000/
echo.
start "" "http://127.0.0.1:8000/"

REM 6. Run FastAPI application via uvicorn
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

pause
