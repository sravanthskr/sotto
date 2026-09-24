@echo off
REM RealAssistant launcher - double-click this to start.
REM Prefers a project virtualenv, then the Windows launcher, then plain python.
setlocal
set HERE=%~dp0

if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%main.py"
  goto :done
)
if exist "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" (
  "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" "%HERE%main.py"
  goto :done
)
where py >nul 2>nul && (py -3 "%HERE%main.py" & goto :done)
python "%HERE%main.py"

:done
echo.
pause
