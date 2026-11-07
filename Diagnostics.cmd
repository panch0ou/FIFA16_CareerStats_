@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
where.exe python.exe >nul 2>nul
if errorlevel 1 (
    echo Install 64-bit Python 3.11 or later and add it to PATH.
    exit /b 1
)
python.exe -B "%~dp0runtime\launch.py" %*
exit /b %errorlevel%

