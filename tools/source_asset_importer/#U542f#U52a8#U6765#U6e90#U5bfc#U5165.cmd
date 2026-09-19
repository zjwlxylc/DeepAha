@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if not errorlevel 1 (
  py -3 run_importer.py
) else (
  python run_importer.py
)
if errorlevel 1 pause
endlocal
