@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo Harmonic Playlist Generator - Start
echo ========================================
echo.

rem Verbindliches Environment ist venv312 (Python 3.12). Python 3.13+ wird
rem NICHT unterstuetzt: numba (librosa-Stack) ist damit inkompatibel.
set "PYTHON_EXE="

if exist "venv312\Scripts\python.exe" (
    set "PYTHON_EXE=venv312\Scripts\python.exe"
    echo [INFO] Nutze virtuelles Environment ^(venv312^).
) else (
    echo [WARN] venv312 nicht gefunden - suche globales Python 3.12...
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        py -3.12 --version >nul 2>&1
        if not errorlevel 1 (
            for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
        )
    )
)

if not defined PYTHON_EXE (
    echo.
    echo [FEHLER] Kein Python 3.12 gefunden.
    echo [INFO]   Erwartet: venv312\Scripts\python.exe oder eine 3.12-Installation.
    echo [INFO]   Python 3.13+ wird nicht unterstuetzt ^(numba^).
    echo [INFO]   Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [INFO] Interpreter: !PYTHON_EXE!
echo.
"!PYTHON_EXE!" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Anwendung konnte nicht gestartet werden. Fehlercode: !errorlevel!
    echo [INFO]  Details siehe logs\hpg.log
    pause
    exit /b 1
)

endlocal
