@echo off
title HMI Rover Lunar V2.0 — Modo Debug y Telemetria Windows
cd /d "%~dp0"

echo ========================================================
echo   🛰️ HMI ROVER LUNAR V2.0 — INICIANDO MODO DEBUG
echo ========================================================
echo.

:: Detectar comando de Python en Windows
set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py"
)
if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    )
)

if not defined PY_CMD (
    echo ========================================================
    echo  [AVISO] No se detecto Python instalado en este Windows.
    echo ========================================================
    pause
    exit /b 1
)

:: Verificar automáticamente pyserial
%PY_CMD% -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo [CONFIGURACION INICIAL] Instalando libreria pyserial para comunicacion USB...
    %PY_CMD% -m pip install pyserial
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar pyserial automaticamente.
        pause
        exit /b 1
    )
)

echo [OK] Iniciando HMI_Rover_Debug.py...
cd /d "%~dp0Firmware_y_Control\Interfaz"
start "" %PY_CMD% HMI_Rover_Debug.py
exit /b 0
