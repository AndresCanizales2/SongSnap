@echo off
chcp 65001 >nul
setlocal

REM Runs SongRadar from source, keeping its playlists in this folder.
REM
REM It deliberately ignores dist\SongRadar.exe even when you have built one:
REM the packaged app keeps its data next to itself, so launching it from here
REM would quietly swap your playlists for whatever lives in dist\.
REM If you only want to use SongRadar, download SongRadar.exe from the
REM releases and double-click that instead.

set "ROOT=%~dp0"
set "WEB=%ROOT%web"

echo.
echo   === SongRadar ===
echo.

REM --- Python side -----------------------------------------------------------
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo   Creating the Python environment...
    py -3.12 -m venv "%ROOT%.venv"
    if errorlevel 1 (
        echo.
        echo   Could not create it with Python 3.12. SongRadar needs Python
        echo   3.10 - 3.12; 3.13 and newer have no wheels for the audio library.
        pause
        exit /b 1
    )
    "%ROOT%.venv\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
)

set "PY=%ROOT%.venv\Scripts\python.exe"

REM --- Interface -------------------------------------------------------------
if not exist "%WEB%\out\index.html" (
    echo   Building the interface, this only happens once...
    "%PY%" "%ROOT%build.py" --web
    if errorlevel 1 (
        echo.
        echo   The interface build failed. Node.js 20 or newer is required.
        pause
        exit /b 1
    )
)

echo   Starting SongRadar on http://127.0.0.1:8000
echo   Close this window to stop it.
echo.
"%PY%" "%ROOT%app.py"
