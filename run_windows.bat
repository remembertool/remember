@echo off
rem SPDX-FileCopyrightText: 2026 Emilio Incerto, Andrea Vandin, Sima Sarv Ahrabi
rem SPDX-License-Identifier: GPL-3.0-or-later
rem Additional terms (GNU GPL v3, section 7): see the file NOTICE.
rem REMEMBER launcher for Windows. Double-click this file.
rem First start: creates a private Python environment (.venv) and installs the
rem packages from requirements.txt. This needs internet once.
setlocal
cd /d "%~dp0"
title REMEMBER

rem 1. Python 3.11 or newer
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [REMEMBER] ERROR: Python 3.11 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  goto :fail
)

rem 2. Java 17 or newer and the engine files
if not exist "engine\jfitVlmc-paper.jar" (
  echo [REMEMBER] ERROR: engine\jfitVlmc-paper.jar is missing. Please use a complete copy of the package.
  goto :fail
)
if not exist "engine\trace2ecf-paper.jar" (
  echo [REMEMBER] ERROR: engine\trace2ecf-paper.jar is missing. Please use a complete copy of the package.
  goto :fail
)
%PY% java_runtime.py
if errorlevel 1 goto :fail

rem 3. Private Python environment (.venv)
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if exist ".venv" (
  "%VENV_PY%" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [REMEMBER] The .venv folder does not work any more. Creating it again ...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv" (
  echo [REMEMBER] First start: creating the Python environment .venv ...
  %PY% -m venv ".venv"
  if errorlevel 1 (
    echo [REMEMBER] ERROR: Could not create the Python environment.
    if exist ".venv" rmdir /s /q ".venv"
    goto :fail
  )
)

fc /b "requirements.txt" ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  echo [REMEMBER] Installing the Python packages - only the first time, this can take a few minutes ...
  "%VENV_PY%" -m pip install --disable-pip-version-check --only-binary=:all: -r "requirements.txt"
  if errorlevel 1 (
    echo.
    echo [REMEMBER] ERROR: Package installation failed. Check the internet connection.
    echo If your Python is very new, install Python 3.13 from https://www.python.org/downloads/ and try again.
    goto :fail
  )
  copy /y "requirements.txt" ".venv\requirements.installed" >nul
)

rem 4. Start
set "REMEMBER_OPEN_BROWSER=1"
"%VENV_PY%" app.py
if errorlevel 1 goto :fail
echo.
pause
exit /b 0

:fail
echo.
echo REMEMBER could not start. Please read the message above.
pause
exit /b 1
