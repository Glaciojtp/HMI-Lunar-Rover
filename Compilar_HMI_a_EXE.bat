@echo off
title Compilador HMI Rover Lunar a Ejecutable Windows (.EXE)
cd /d "%~dp0"
echo ========================================================
echo   🛰️ COMPILADOR DE HMI ROVER LUNAR V2.0 A .EXE STANDALONE
echo   (Genera un archivo ejecutable apto para cualquier PC)
echo ========================================================
echo.

:: 1. Detectar comando de Python en Windows
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
    echo [ERROR] No se encontro Python en Windows para compilar el ejecutable.
    echo Asegurate de instalar Python desde https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Usando interprete: %PY_CMD%
echo.

:: 2. Instalar / Actualizar PyInstaller y PySerial
echo [1/3] Verificando e instalando PyInstaller y PySerial...
%PY_CMD% -m pip install --upgrade pip >nul 2>&1
%PY_CMD% -m pip install pyserial pyinstaller
if errorlevel 1 (
    echo.
    echo [ERROR] Ocurrio un error al instalar las dependencias con pip.
    pause
    exit /b 1
)

:: 3. Compilar la HMI a un único ejecutable
echo.
echo [2/3] Compilando HMI_Rover_V2.py en un unico archivo .EXE...
echo (Este proceso puede demorar entre 30 y 60 segundos, por favor espera...)
cd /d "%~dp0Firmware_y_Control\Interfaz"
%PY_CMD% -m PyInstaller --clean --noconsole --onefile --name "HMI_Rover_Lunar_V2" HMI_Rover_V2.py

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la compilacion con PyInstaller.
    cd /d "%~dp0"
    pause
    exit /b 1
)

:: 4. Mover el ejecutable a la raíz del proyecto y limpiar temporales
echo.
echo [3/3] Finalizando y organizando archivos...
cd /d "%~dp0"
if exist "%~dp0HMI_Rover_Lunar_V2.exe" del /f /q "%~dp0HMI_Rover_Lunar_V2.exe"
if exist "%~dp0Firmware_y_Control\Interfaz\dist\HMI_Rover_Lunar_V2.exe" (
    move /y "%~dp0Firmware_y_Control\Interfaz\dist\HMI_Rover_Lunar_V2.exe" "%~dp0HMI_Rover_Lunar_V2.exe" >nul
)

:: Limpieza de carpetas temporales de compilación
if exist "%~dp0Firmware_y_Control\Interfaz\build" rmdir /s /q "%~dp0Firmware_y_Control\Interfaz\build"
if exist "%~dp0Firmware_y_Control\Interfaz\dist" rmdir /s /q "%~dp0Firmware_y_Control\Interfaz\dist"
if exist "%~dp0Firmware_y_Control\Interfaz\HMI_Rover_Lunar_V2.spec" del /f /q "%~dp0Firmware_y_Control\Interfaz\HMI_Rover_Lunar_V2.spec"

echo.
echo ========================================================
echo  🎉 [EXITO] Archivo 'HMI_Rover_Lunar_V2.exe' generado!
echo ========================================================
echo.
echo  Ubicacion: %~dp0HMI_Rover_Lunar_V2.exe
echo.
echo  Instrucciones para tus companeros de equipo:
echo   1. Copiar 'HMI_Rover_Lunar_V2.exe' a cualquier computadora con Windows.
echo   2. Hacerle DOBLE CLIC directo (¡NO requiere instalar Python ni nada!).
echo   3. Conectar el cable USB del Rover, tocar 'CONECTAR' y manejar.
echo ========================================================
echo.
pause
