@echo off
REM RealAssistant launcher - ALWAYS use this so the right Python is used.
REM   run.bat          -> text mode
REM   run.bat voice    -> voice mode
REM   run.bat check    -> voice diagnosis
REM   run.bat mic      -> voice diagnosis + 4s mic test
setlocal
set HERE=%~dp0
set ENTRY=main.py
set EXTRA=
if /I "%~1"=="voice" set ENTRY=voice_main.py
if /I "%~1"=="check" set ENTRY=voice_check.py
if /I "%~1"=="mic"   set ENTRY=voice_check.py & set EXTRA=--mic

if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%%ENTRY%" %EXTRA%
  goto :done
)
if exist "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" (
  "%HERE%..\Python\.venv\RealAssistant\Scripts\python.exe" "%HERE%%ENTRY%" %EXTRA%
  goto :done
)
where py >nul 2>nul && (py -3 "%HERE%%ENTRY%" %EXTRA% & goto :done)
python "%HERE%%ENTRY%" %EXTRA%

:done
echo.
pause
