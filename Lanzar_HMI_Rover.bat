@echo off
title HMI Rover Lunar V2.0
cd /d "%~dp0Archivos de arduino de ahora\Interfaz"
python HMI_Rover_V2.py
if errorlevel 1 (
    echo.
    echo ========================================================
    echo Error al iniciar la interfaz en Python.
    echo Asegurate de tener instalado Python y pyserial:
    echo    pip install pyserial
    echo ========================================================
    pause
)
