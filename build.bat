@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
REM =========================================================
REM Harmonic Playlist Generator v3.7.2 - Build Script
REM One-Click Build: Creates standalone Windows executable
REM =========================================================

echo.
echo ========================================================
echo   Harmonic Playlist Generator v3.7.2 - BUILD SCRIPT
echo ========================================================
echo.

REM Find Python (explicit path to avoid Windows Store stub)
set "PYTHON_EXE="
if defined GITHUB_ACTIONS (
    set "PYTHON_EXE=python"
) else if exist "venv312\Scripts\python.exe" (
    set "PYTHON_EXE=venv312\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else (
    REM Fallback: py-Launcher mit 3.12
    py -3.12 --version >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%P"
    ) else (
        echo [ERROR] Python 3.12 nicht gefunden!
        echo [INFO]  Erwarteter Pfad: %LOCALAPPDATA%\Programs\Python\Python312\python.exe
        echo [INFO]  Numba ist inkompatibel mit Python 3.13 und hoeher.
        echo [INFO]  Download: https://www.python.org/downloads/release/python-3120/
        exit /b 1
    )
)

"!PYTHON_EXE!" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not working! Check installation.
    exit /b 1
)

"!PYTHON_EXE!" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.version_info >= (3, 12, 1) else 1)"
if errorlevel 1 (
    echo [ERROR] Build requires Python 3.12.1 or newer within the 3.12 series.
    "!PYTHON_EXE!" --version
    exit /b 1
)

echo [1/6] Python found: !PYTHON_EXE!
echo.

REM Check if running in GitHub Actions
if defined GITHUB_ACTIONS (
    echo [2/6] Running in GitHub Actions - using system Python
    echo [INFO] Skipping virtual environment setup
    echo.
) else (
    REM Local build - use virtual environment
    if not exist "venv312\" (
        echo [2/6] Creating virtual environment...
        "!PYTHON_EXE!" -m venv venv312
        if errorlevel 1 (
            echo [ERROR] Virtual environment creation failed.
            exit /b 1
        )
        echo [SUCCESS] Virtual environment created
        echo.
    ) else (
        echo [2/6] Using existing virtual environment...
        echo.
    )

    echo [INFO] Activating virtual environment...
    call venv312\Scripts\activate.bat
    if errorlevel 1 (
        echo [ERROR] Failed to activate virtual environment
        exit /b 1
    )
    set "PYTHON_EXE=venv312\Scripts\python.exe"
    echo.
)

REM Install dependencies from requirements.txt
echo [3/6] Installing dependencies...
"!PYTHON_EXE!" -m pip install --upgrade pip -q
if errorlevel 1 (
    echo [ERROR] pip upgrade failed.
    exit /b 1
)
"!PYTHON_EXE!" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
)
echo [SUCCESS] Dependencies installed
echo.

REM Verify pinned PyInstaller from requirements.txt
echo [4/6] Verifying PyInstaller...
"!PYTHON_EXE!" -c "import PyInstaller; raise SystemExit(0 if PyInstaller.__version__ == '6.21.0' else 1)"
if errorlevel 1 (
    echo [ERROR] Required PyInstaller 6.21.0 is not installed.
    exit /b 1
)
echo [SUCCESS] PyInstaller ready
echo.

REM Clean previous builds
echo [5/6] Cleaning previous builds...
if exist "build\" rmdir /s /q build
if exist "dist\" rmdir /s /q dist
if exist "HarmonicPlaylistGenerator.exe" del /q HarmonicPlaylistGenerator.exe
echo [SUCCESS] Cleaned
echo.

REM Build executable
echo [6/6] Building executable (this may take 2-5 minutes)...
echo [INFO] Please wait...
"!PYTHON_EXE!" -m PyInstaller --clean --noconfirm HPG.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check error messages above.
    exit /b 1
)
echo.
echo [SUCCESS] Build complete!
echo.

REM Move executable to root
echo [INFO] Finalizing...
if exist "dist\HarmonicPlaylistGenerator.exe" (
    move /y "dist\HarmonicPlaylistGenerator.exe" "HarmonicPlaylistGenerator.exe" >nul
    echo [SUCCESS] Executable: HarmonicPlaylistGenerator.exe
) else (
    echo [ERROR] Executable not found in dist folder!
    exit /b 1
)

REM Clean up build artifacts
rmdir /s /q build >nul 2>&1
rmdir /s /q dist >nul 2>&1

echo.
echo ========================================================
echo   BUILD SUCCESSFUL!
echo ========================================================
echo.
echo   Executable: HarmonicPlaylistGenerator.exe
echo   Size: ~300-500 MB (includes all dependencies)
echo.
echo   Next steps:
echo   1. Test: Run HarmonicPlaylistGenerator.exe
echo   2. Create installer: Run build_installer.bat (optional)
echo   3. Distribute: Share the .exe or installer
echo.
echo ========================================================
echo.

endlocal
