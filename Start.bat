@echo off
cd /d "%~dp0"

echo Starte Harmonic Playlist Generator...
echo.

rem Verbindliches Environment ist venv312 (Python 3.12) — das alte venv/ war
rem Python 3.14 mit defektem numpy und wurde entfernt (Audit 2026-07-17)
if exist "venv312\Scripts\python.exe" (
    echo Nutze virtuelles Environment ^(venv312^)...
    "venv312\Scripts\python.exe" main.py
) else (
    echo Virtuelles Environment nicht gefunden. Nutze globales Python...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
)

if %errorlevel% neq 0 (
    echo.
    echo Fehler beim Starten. Fehlercode: %errorlevel%
    pause
)
