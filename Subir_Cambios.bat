@echo off
title Subir Cambios a GitHub - Rover Lunar V2.0
cd /d "%~dp0"
echo ========================================================
echo   ROVER LUNAR V2.0 - SINCRONIZADOR RAPIDO CON GITHUB
echo ========================================================
echo.
git status -s
echo.
set /p mensaje="Escribe un mensaje para estos cambios (o Enter para 'Actualizacion'): "
if "%mensaje%"=="" set mensaje=Actualizacion de archivos y codigo

echo.
echo Guardando cambios...
git add .
git commit -m "%mensaje%"

echo.
echo Subiendo a GitHub...
git push

if errorlevel 1 (
    echo.
    echo ========================================================
    echo  [ERROR] Hubo un problema al subir los cambios a GitHub.
    echo ========================================================
    pause
) else (
    echo.
    echo ========================================================
    echo  [OK] Cambios subidos exitosamente a GitHub!
    echo ========================================================
    timeout /t 3 >nul
)
