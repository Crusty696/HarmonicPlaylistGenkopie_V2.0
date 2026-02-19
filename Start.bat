@echo off
cd /d "%~dp0"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
if %errorlevel% neq 0 (
    echo.
    echo Fehler beim Starten. Fehlercode: %errorlevel%
    pause
)
