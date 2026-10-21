@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Project Python environment was not found.
  echo Run the project setup first, then launch this file again.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "src\start_job_bot.py"
if errorlevel 1 (
  echo.
  echo The job dashboard did not start. Review the message above.
  pause
)
endlocal
