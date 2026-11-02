@echo off
title Compilar HMI Rover Lunar a EXE
cd /d "%~dp0"

set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    where py >nul 2>&1 && set "PY_CMD=py"
)
if not defined PY_CMD (
    echo [ERROR] No se encontro Python.
    pause
    exit /b 1
)

%PY_CMD% -m pip install pyserial pyinstaller
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

cd /d "%~dp001_Oficial\HMI"
%PY_CMD% -m PyInstaller --clean --noconsole --onefile --name "HMI_Rover" HMI_Rover.py
if errorlevel 1 (
    echo [ERROR] Fallo PyInstaller.
    cd /d "%~dp0"
    pause
    exit /b 1
)

move /y "dist\HMI_Rover.exe" "%~dp0HMI_Rover.exe" >nul
rmdir /s /q build
rmdir /s /q dist
del /f /q HMI_Rover.spec
cd /d "%~dp0"
echo [OK] Generado HMI_Rover.exe en la raiz del repositorio.
pause
