@echo off
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

if "%~1"=="" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -X utf8 manual_test.py
) else (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -X utf8 manual_test.py %*
)

if %errorlevel% neq 0 (
    echo.
    echo Fehler beim Ausfuehren. Fehlercode: %errorlevel%
)

pause
