@echo off
cd /d "%~dp0"
py -3 scripts\launch_product.py --stop
if errorlevel 1 pause
