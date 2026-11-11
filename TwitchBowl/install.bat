@echo off
cd /d "%~dp0"
if not exist "%~dp0node.exe" (
  echo Extract the zip to a folder first, then run install.bat from there.
  pause
  exit /b
)
"%~dp0node.exe" setup.js
pause
