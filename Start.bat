@echo off
cd /d "%~dp0"

echo Starte Harmonic Playlist Generator...
echo.

rem Pruefe zuerst, ob das virtuelle Environment (venv) existiert und nutze es
if exist "venv\Scripts\python.exe" (
    echo Nutze virtuelles Environment ^(venv^)...
    "venv\Scripts\python.exe" main.py
) else (
    echo Virtuelles Environment nicht gefunden. Nutze globales Python...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
)

if %errorlevel% neq 0 (
    echo.
    echo Fehler beim Starten. Fehlercode: %errorlevel%
    pause
)
