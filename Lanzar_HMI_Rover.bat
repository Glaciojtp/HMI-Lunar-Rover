@echo off
title HMI Rover Lunar V2.0 — Lanzador Inteligente Windows
cd /d "%~dp0"

echo ========================================================
echo   🛰️ HMI ROVER LUNAR V2.0 — INICIANDO SISTEMA
echo ========================================================
echo.

:: 1. Si ya existe el ejecutable compilado, abrirlo directamente
if exist "%~dp0HMI_Rover_Lunar_V2.exe" (
    echo [INFO] Ejecutable nativo detectado. Abriendo HMI_Rover_Lunar_V2.exe...
    start "" "%~dp0HMI_Rover_Lunar_V2.exe"
    exit /b 0
)

:: 2. Detectar comando de Python en Windows
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

:: 3. Si no hay Python, ofrecer ayuda amigable
if not defined PY_CMD (
    echo ========================================================
    echo  [AVISO] No se detecto Python instalado en este Windows.
    echo ========================================================
    echo.
    echo  Tenes 2 opciones sencillas:
    echo.
    echo  1. Pedile a Joaquin el archivo 'HMI_Rover_Lunar_V2.exe'
    echo     (No necesita Python ni instalar nada).
    echo.
    echo  2. Instala Python desde la web oficial (marca 'Add to PATH').
    echo.
    set /p abrir_web="¿Queres abrir la web para descargar Python ahora? (S/N): "
    if /i "%abrir_web%"=="S" (
        start https://www.python.org/downloads/
    )
    pause
    exit /b 1
)

:: 4. Verificar automáticamente la librería pyserial (Auto-instalación)
%PY_CMD% -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo [CONFIGURACION INICIAL] Instalando libreria pyserial para comunicacion USB...
    %PY_CMD% -m pip install pyserial
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar pyserial automaticamente.
        pause
        exit /b 1
    )
    echo [OK] pyserial instalada con exito.
    echo.
)

:: 5. Iniciar la interfaz HMI
echo [OK] Iniciando HMI_Rover_V2.py...
cd /d "%~dp0Firmware_y_Control\Interfaz"
start "" %PY_CMD% HMI_Rover_V2.py
exit /b 0
