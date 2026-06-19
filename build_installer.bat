@echo off
REM =========================================================
REM Build Professional Windows Installer for HPG v3.5.3
REM Requires: Inno Setup (https://jrsoftware.org/isdl.php)
REM =========================================================

echo.
echo ========================================================
echo   HPG v3.5.3 - INSTALLER BUILD SCRIPT
echo ========================================================
echo.

REM Check if executable exists
if not exist "HarmonicPlaylistGenerator.exe" (
    echo [ERROR] HarmonicPlaylistGenerator.exe not found!
    echo.
    echo Please run build.bat first to create the executable.
    echo.
    pause
    exit /b 1
)

echo [1/4] Executable found: HarmonicPlaylistGenerator.exe
echo.

REM Check if Inno Setup is installed
set "INNO_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%INNO_PATH%" (
    echo [ERROR] Inno Setup not found!
    echo.
    echo Please install Inno Setup 6:
    echo https://jrsoftware.org/isdl.php
    echo.
    echo After installation, run this script again.
    echo.
    pause
    exit /b 1
)

echo [2/4] Inno Setup found
echo.

REM Create output directory
if not exist "installer_output\" mkdir installer_output
echo [3/4] Output directory ready
echo.

REM Build installer
echo [4/4] Building installer...
echo [INFO] This may take 1-2 minutes...
echo.

"%INNO_PATH%" "installer.iss"
if errorlevel 1 (
    echo.
    echo [ERROR] Installer build failed!
    echo Check error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   INSTALLER BUILD SUCCESSFUL!
echo ========================================================
echo.
echo   Installer: installer_output\HPG_v3.5.3_Setup.exe
echo   Size: ~300-500 MB (standalone installer)
echo.
echo   Features:
echo   - One-click installation
echo   - Desktop icon
echo   - Start Menu entry
echo   - Uninstaller
echo   - Professional UI
echo.
echo   Ready to distribute!
echo.
echo ========================================================
echo.

REM Open output folder
if exist "installer_output\HPG_v3.5.3_Setup.exe" (
    explorer /select,"installer_output\HPG_v3.5.3_Setup.exe"
)

pause
