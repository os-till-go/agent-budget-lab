@echo off
setlocal
cd /d "%~dp0"
python server.py --check
if errorlevel 1 (
  echo.
  echo Please install dependencies first:
  echo   python -m pip install -r requirements.txt
  echo Then run this file again.
  pause
  exit /b 1
)
echo.
echo Opening Agent Budget Lab at http://127.0.0.1:8767
echo Keep this window open. Press Ctrl+C to stop.
python server.py --open
pause
