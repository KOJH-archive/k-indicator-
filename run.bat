@echo off
title K-Indicator AI Automation System
echo [INFO] Starting FastAPI Uvicorn Server...

:: Start uvicorn in the background using the specified Python path
start /b "" C:\Users\Check\AppData\Local\Python\bin\python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8000

echo [INFO] Waiting 3 seconds for server to start...
timeout /t 3 > nul

echo [INFO] Opening default web browser at http://127.0.0.1:8000...
start "" "http://127.0.0.1:8000"

echo.
echo =========================================================================
echo  K-Indicator Dashboard is now running.
echo  Keep this console window open while using the dashboard.
echo  To terminate, press Ctrl+C in this console or close the window.
echo =========================================================================
echo.

:: Hold console to display logs
pause > nul
