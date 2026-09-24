@echo off
REM RealAssistant launcher. Usage:  run.bat          (text mode)
REM                                 run.bat voice    (voice mode)
setlocal
set HERE=%~dp0
set ENTRY=main.py
if /I "%~1"=="voice" set ENTRY=voice_main.py

if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%%ENTRY%"
  goto :done
)
if exist "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" (
  "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" "%HERE%%ENTRY%"
  goto :done
)
where py >nul 2>nul && (py -3 "%HERE%%ENTRY%" & goto :done)
python "%HERE%%ENTRY%"

:done
echo.
pause
