@echo off
REM =========================================================
REM Harmonic Playlist Generator v3.0 - Build Script
REM One-Click Build: Creates standalone Windows executable
REM =========================================================

echo.
echo ========================================================
echo   Harmonic Playlist Generator v3.0 - BUILD SCRIPT
echo ========================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.9+
    pause
    exit /b 1
)

echo [1/7] Python found
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo [WARNING] Virtual environment not found. Creating...
    python -m venv venv
    echo [SUCCESS] Virtual environment created
    echo.
)

echo [2/7] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

REM Install dependencies from requirements.txt
echo [3/6] Installing dependencies...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Some dependencies may have failed to install
)
echo [SUCCESS] Dependencies installed
echo.

REM Install/upgrade PyInstaller
echo [4/6] Installing PyInstaller...
pip install --upgrade pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller
    pause
    exit /b 1
)
echo [SUCCESS] PyInstaller ready
echo.

REM Clean previous builds
echo [5/7] Cleaning previous builds...
if exist "build\" rmdir /s /q build
if exist "dist\" rmdir /s /q dist
if exist "HarmonicPlaylistGenerator.exe" del /q HarmonicPlaylistGenerator.exe
echo [SUCCESS] Cleaned
echo.

REM Build executable
echo [6/7] Building executable (this may take 2-5 minutes)...
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
echo [7/7] Finalizing...
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
