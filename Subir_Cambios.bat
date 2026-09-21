@echo off
title Subir Cambios a GitHub - Rover Lunar V2.0
cd /d "%~dp0"
echo ========================================================
echo   ROVER LUNAR V2.0 - SINCRONIZADOR RAPIDO CON GITHUB
echo ========================================================
echo.
:: Detectar comando de git (Windows nativo o WSL)
set "GIT_EXE=git"
where git >nul 2>&1
if errorlevel 1 (
    where wsl >nul 2>&1
    if not errorlevel 1 (
        set "GIT_EXE=wsl git"
    ) else (
        echo [ERROR] Git no esta en el PATH de Windows ni se detecto WSL.
        echo Podes instalar Git para Windows desde https://git-scm.com/
        echo o ejecutar 'git push' directo en tu terminal de WSL / VS Code.
        pause
        exit /b 1
    )
)

%GIT_EXE% status -s
echo.
set /p mensaje="Escribe un mensaje para estos cambios (o Enter para 'Actualizacion'): "
if "%mensaje%"=="" set mensaje=Actualizacion de archivos y codigo

echo.
echo Guardando cambios...
%GIT_EXE% add .
%GIT_EXE% commit -m "%mensaje%"

echo.
echo Subiendo a GitHub...
%GIT_EXE% push

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
