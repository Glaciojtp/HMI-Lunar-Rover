@echo off
title HMI Rover Lunar V2.0 — Modo Debug y Telemetria
cd /d "%~dp0Firmware_y_Control\Interfaz"
python HMI_Rover_Debug.py
if errorlevel 1 (
    echo.
    echo ========================================================
    echo Error al iniciar la interfaz de depuracion en Python.
    echo Asegurate de tener instalado Python y pyserial:
    echo    pip install pyserial
    echo ========================================================
    pause
)
