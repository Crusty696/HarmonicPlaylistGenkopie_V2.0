@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo Harmonic Playlist Generator - Installer bauen
echo ========================================
echo.
echo Dieses Skript erzeugt NUR den Installer aus installer.iss.
echo Die EXE baut build.bat - bitte vorher ausfuehren.
echo.

rem --- 1/4: EXE muss vorhanden sein -------------------------------------
if not exist "HarmonicPlaylistGenerator.exe" (
    echo [FEHLER] HarmonicPlaylistGenerator.exe nicht gefunden.
    echo [INFO]   Zuerst build.bat ausfuehren.
    echo.
    pause
    exit /b 1
)
echo [1/4] EXE gefunden: HarmonicPlaylistGenerator.exe

rem --- 2/4: Inno Setup finden -------------------------------------------
set "INNO_PATH="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "INNO_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined INNO_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "INNO_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined INNO_PATH (
    echo [FEHLER] Inno Setup 6 nicht gefunden ^(ISCC.exe^).
    echo [INFO]   Download: https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)
echo [2/4] Inno Setup gefunden: !INNO_PATH!

rem --- 3/4: Ausgabeverzeichnis ------------------------------------------
if not exist "installer_output\" mkdir "installer_output"
echo [3/4] Ausgabeverzeichnis bereit: installer_output\

rem --- 4/4: Installer kompilieren ---------------------------------------
echo [4/4] Kompiliere installer.iss ^(dauert 1-2 Minuten^)...
echo.
"!INNO_PATH!" "installer.iss"
if errorlevel 1 (
    echo.
    echo [FEHLER] Installer-Build fehlgeschlagen - Meldungen oben pruefen.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   INSTALLER ERFOLGREICH ERSTELLT
echo ========================================
echo   Ablage: installer_output\
echo.
pause
endlocal
