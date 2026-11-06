@echo off
title HMI Rover Lunar
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py"
)

if not defined PY_CMD (
    if exist "%~dp0HMI_Rover.exe" (
        start "" "%~dp0HMI_Rover.exe"
        exit /b 0
    )
    echo [AVISO] No se encontro Python. Instalalo desde https://www.python.org/downloads/
    echo o pedi HMI_Rover.exe, generado con Compilar_HMI_a_EXE.bat.
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
start "" %PY_CMD% HMI_Rover.py
exit /b 0
