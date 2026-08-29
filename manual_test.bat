@echo off
setlocal
cd /d "%~dp0"
title HPG - DJ Manueller Test

echo.
echo =============================================
echo   HPG - Manueller DJ Test
echo   Tracks aus: D:\beatport_tracks_2025-08
echo =============================================
echo.
echo Aufruf-Optionen:
echo   Interaktiv:       manual_test.bat
echo   Direkter Track:   manual_test.bat "C:\pfad\zum\track.aiff"
echo   Anderer Ordner:   manual_test.bat --folder "D:\mein_ordner"
echo.

set "PYTHON_EXE=%~dp0venv312\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [FEHLER] Projekt-venv nicht gefunden: venv312\Scripts\python.exe
    pause
    exit /b 1
)

"%PYTHON_EXE%" -X utf8 tools\manual_test.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Fehler beim Ausfuehren. Fehlercode: %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

pause
exit /b 0
