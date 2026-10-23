@echo off
title Cord - AI Laptop Worker
color 0D
cd /d "C:\Users\12san\Desktop\LAVA\backend"

echo ========================================================
echo               CORD - AI LAPTOP WORKER
echo ========================================================
echo.
echo [*] Working Directory: %CD%
echo [*] Target Server:     https://cord-backend-api.onrender.com
echo [*] Launching Python Worker...
echo.

"C:\Users\12san\Desktop\LAVA\backend\.venv\Scripts\python.exe" laptop_worker.py

echo.
echo ========================================================
echo [*] Worker process stopped.
echo ========================================================
echo Press any key to exit...
pause >nul
