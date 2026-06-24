@echo off
title MRA Mapmaker
cd /d "%~dp0"
rem Prefer a Python that already has pygame; otherwise use any Python and install it.
set "PY="
py -3 -c "import pygame" >nul 2>nul && set "PY=py -3" && goto run
python -c "import pygame" >nul 2>nul && set "PY=python" && goto run
py -3 --version >nul 2>nul && set "PY=py -3" && goto run
python --version >nul 2>nul && set "PY=python" && goto run
goto nopy
:run
%PY% -c "import pygame" >nul 2>nul || %PY% -m pip install pygame
%PY% editor.py
if errorlevel 1 pause
exit /b 0
:nopy
echo.
echo   Python 3 was not found.
echo   Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
echo.
pause
