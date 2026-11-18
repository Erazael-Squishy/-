@echo off
rem Run once: puts a "Live Translator" shortcut on the desktop and in the Start menu.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcuts.ps1"
pause
