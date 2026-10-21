@echo off
cd /d "%~dp0"
python -m instrumentlab --demo
if errorlevel 1 pause
