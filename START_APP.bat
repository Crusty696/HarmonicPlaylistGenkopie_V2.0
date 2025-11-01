@echo off
REM Harmonic Playlist Generator v5 - Windows Starter
REM Doppelklick auf diese Datei zum Starten!

echo ================================================================================
echo   HARMONIC PLAYLIST GENERATOR v5
echo ================================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python ist nicht installiert!
    echo.
    echo Bitte installiere Python 3.10 oder neuer von:
    echo https://www.python.org/downloads/
    echo.
    echo WICHTIG: Setze den Haken bei "Add Python to PATH"!
    pause
    exit /b 1
)

echo Python gefunden:
python --version
echo.

REM Check if dependencies are installed
echo Pruefe Dependencies...
python -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Dependencies fehlen! Installiere jetzt...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Installation fehlgeschlagen!
        pause
        exit /b 1
    )
)

echo.
echo Alle Dependencies installiert!
echo.
echo ================================================================================
echo   STARTE APP...
echo ================================================================================
echo.

REM Start the app
python main.py

REM If app crashed, show error
if errorlevel 1 (
    echo.
    echo ================================================================================
    echo   ERROR: App ist abgestuerzt!
    echo ================================================================================
    echo.
    echo Siehe Fehlermeldungen oben fuer Details.
    echo.
)

pause
