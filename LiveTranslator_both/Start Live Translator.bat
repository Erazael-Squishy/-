@echo off
setlocal
rem ==========================================================================
rem  Live Translator launcher - double-click, or use the shortcut it creates.
rem  Keep this file in the same folder as translator_http.py.
rem
rem  If VS Code runs the translator with a specific Python (bottom-right corner
rem  of VS Code), paste its full path here so the same one is used, e.g.
rem      set "PYTHON=C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe"
rem  (if the path has spaces, put quotes around it inside:  set "PYTHON="C:\My Python\python.exe"")
set "PYTHON="
rem ==========================================================================
cd /d "%~dp0"
title Live Translator  (close this window to stop it)

rem Extracted? (Started from inside the zip, Windows copies out only this file.)
if not exist "translator_http.py" (
    echo.
    echo  translator_http.py is missing from this folder.
    echo  Right-click the zip, choose "Extract All", then start this from the extracted folder.
    echo.
    pause
    exit /b 1
)

rem Find Python 3.11 - 3.13: the one set above, a venv in this folder, the py launcher, the usual install
rem folders, then "python". Windows' Microsoft Store placeholder "python" isn't a real Python, so it's skipped.
if defined PYTHON goto run
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe" & goto run)
if exist "venv\Scripts\python.exe" (set "PYTHON=venv\Scripts\python.exe" & goto run)
call :find_python
if defined PYTHON goto run

echo.
echo  This needs Python 3.11, 3.12 or 3.13, and none is installed on this PC yet.
echo  (Python 3.14 and newer can't be used yet: the microphone package doesn't support them.)
echo.
where winget >nul 2>nul
if errorlevel 1 goto no_python
choice /c YN /m " Install Python 3.12 now (free, official python.org build, takes a minute)"
if errorlevel 2 goto no_python
winget install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
call :find_python
if defined PYTHON goto run

:no_python
echo.
echo  Install Python 3.12 from https://www.python.org/downloads/windows/
echo  and tick "Add python.exe to PATH" at the bottom of the first setup screen. Then start this again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:run
echo Starting the translator with: %PYTHON%
echo (Closing this window stops the translator.)
echo.
%PYTHON% translator_http.py
if errorlevel 1 (
    echo.
    echo  The translator stopped because of an error - see the messages above.
    pause
)

rem ---- finds a usable Python and puts it in PYTHON (empty if there's none) ----
:find_python
for %%V in (3.13 3.12 3.11) do (
    py -%%V -c "" >nul 2>nul && (set "PYTHON=py -%%V" & exit /b 0)
)
for %%V in (313 312 311) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (set "PYTHON="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"" & exit /b 0)
    if exist "%ProgramFiles%\Python%%V\python.exe" (set "PYTHON="%ProgramFiles%\Python%%V\python.exe"" & exit /b 0)
)
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P| findstr /i /c:"WindowsApps" >nul || (
        "%%P" -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>nul && (set "PYTHON="%%P"" & exit /b 0)
    )
)
exit /b 0
