@echo off
chcp 65001 >nul
title HPG - Hörtest Manager

cd /d "%~dp0"

if not exist "venv312\Scripts\python.exe" (
    echo [FEHLER] Python venv312 nicht gefunden!
    echo Bitte stelle sicher, dass das Projekt-Environment unter venv312 existiert.
    pause
    exit /b 1
)

"%~dp0venv312\Scripts\python.exe" "%~dp0tools\hoertest_launcher.py"
