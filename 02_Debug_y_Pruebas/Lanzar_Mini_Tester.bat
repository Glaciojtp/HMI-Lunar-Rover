@echo off
title Mini Tester de Actuadores — Rover Lunar V2.0
cd /d "%~dp0"

echo ========================================================
echo   [INICIO] MINI TESTER DE COMPONENTES ROVER LUNAR V2.0
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

:: Verificar automaticamente pyserial
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

echo [OK] Iniciando Mini Tester...
cd /d "%~dp0Mini_Tester"
start "" %PY_CMD% mini_tester_rover.py
exit /b 0
