@echo off
chcp 65001 >nul
set "DEEPAHA_ENTRY_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DEEPAHA_ENTRY_ROOT%scripts\local-manual-test.ps1" -Action Start
set "DEEPAHA_ENTRY_EXIT=%ERRORLEVEL%"
if not "%DEEPAHA_LAUNCHER_NONINTERACTIVE%"=="1" pause
exit /b %DEEPAHA_ENTRY_EXIT%
