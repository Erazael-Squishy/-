@echo off
curl -s http://127.0.0.1:7373/quit >nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Twitch Bowl.bat"
echo The bowl has stopped and will no longer start with Windows.
echo You can now delete this folder.
pause
