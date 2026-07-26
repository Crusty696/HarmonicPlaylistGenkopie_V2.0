@echo off
REM Installiert die HPG-Experten-Skills aus hpg-skills-bundle.zip nach .claude\
REM Einfach per Doppelklick ausfuehren (oder Claude Code darum bitten).
cd /d "%~dp0"
powershell -NoProfile -Command "Expand-Archive -Path 'hpg-skills-bundle.zip' -DestinationPath '.' -Force"
if exist ".claude\skills\hpg-mix-points\SKILL.md" (
  echo.
  echo ✔ HPG-Skills erfolgreich installiert nach .claude\skills\ und .claude\agents\
  echo   Naechste Claude-Code-Session in diesem Repo laedt sie automatisch.
) else (
  echo ✖ Installation fehlgeschlagen - bitte hpg-skills-bundle.zip manuell nach .claude\ entpacken.
)
pause
