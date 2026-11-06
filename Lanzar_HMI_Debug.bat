@echo off
title HMI Rover Lunar - Debug
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py"
)

if not defined PY_CMD (
    echo [AVISO] No se encontro Python. Instalalo desde https://www.python.org/downloads/
    pause
    exit /b 1
)

%PY_CMD% -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo Instalando pyserial...
    %PY_CMD% -m pip install pyserial
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar pyserial.
        pause
        exit /b 1
    )
)

cd /d "%~dp001_Oficial\HMI"
start "" %PY_CMD% HMI_Rover_Debug.py
exit /b 0
