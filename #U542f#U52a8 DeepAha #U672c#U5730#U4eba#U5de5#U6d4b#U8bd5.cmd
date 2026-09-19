@echo off
cd /d "%~dp0"
py -3 scripts\launch_product.py --install
if errorlevel 1 pause
