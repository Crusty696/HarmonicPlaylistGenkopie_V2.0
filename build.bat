@echo off
REM =========================================================
REM Harmonic Playlist Generator v3.6.0 - Build Script
REM One-Click Build: Creates standalone Windows executable
REM =========================================================

echo.
echo ========================================================
echo   Harmonic Playlist Generator v3.6.0 - BUILD SCRIPT
echo ========================================================
echo.

REM Find Python (explicit path to avoid Windows Store stub)
set "PYTHON_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
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
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not working! Check installation.
    pause
    exit /b 1
)

echo [1/6] Python found: %PYTHON_EXE%
echo.

REM Check if running in GitHub Actions
if defined GITHUB_ACTIONS (
    echo [2/6] Running in GitHub Actions - using system Python
    echo [INFO] Skipping virtual environment setup
    echo.
) else (
    REM Local build - use virtual environment
    if not exist "venv\" (
        echo [2/6] Creating virtual environment...
        "%PYTHON_EXE%" -m venv venv
        echo [SUCCESS] Virtual environment created
        echo.
    ) else (
        echo [2/6] Using existing virtual environment...
        echo.
    )

    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
    if errorlevel 1 (
        echo [ERROR] Failed to activate virtual environment
        pause
        exit /b 1
    )
    echo.
)

REM Install dependencies from requirements.txt
echo [3/6] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [WARNING] Some dependencies may have failed to install - continuing...
)
echo [SUCCESS] Dependencies installed
echo.

REM Install/upgrade PyInstaller
echo [4/6] Installing PyInstaller...
pip install --upgrade pyinstaller -q
if errorlevel 1 (
    echo [WARNING] PyInstaller installation had errors - trying to continue...
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
pyinstaller --clean --noconfirm HPG.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check error messages above.
    pause
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
    pause
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

pause
