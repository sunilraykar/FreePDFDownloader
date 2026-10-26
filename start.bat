@echo off
setlocal
cd /d "%~dp0"
echo Starting FreePDFDownloader...
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.10+ and enable Add Python to PATH.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error
python app.py
goto :eof
:error
echo Startup failed. Review the error above.
pause
