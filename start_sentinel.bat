@echo off
setlocal

rem SentinelOS local launcher. Run this file from Explorer or a Command Prompt.
cd /d "%~dp0"

set "SENTINEL_HOST=127.0.0.1"
if "%SENTINEL_PORT%"=="" set "SENTINEL_PORT=8000"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [SentinelOS] Python was not found. Install Python 3.10+ or create .venv.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

echo [SentinelOS] Starting local server at http://%SENTINEL_HOST%:%SENTINEL_PORT%
echo [SentinelOS] Press Ctrl+C to stop the server.
"%PYTHON%" -m uvicorn api.app:app --host %SENTINEL_HOST% --port %SENTINEL_PORT%

if errorlevel 1 (
    echo.
    echo [SentinelOS] Server stopped with an error.
    pause
)
endlocal
