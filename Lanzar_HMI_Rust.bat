@echo off
title HMI Rover Lunar V2.0 - Rust Desktop GUI
cd /d "%~dp0"

echo ========================================================
echo   [INICIO] HMI ROVER LUNAR V2.0 - APLICACION EN RUST
echo ========================================================
echo.

:: 1. Comprobar si cargo esta disponible en Windows directamente
where cargo >nul 2>&1
if not errorlevel 1 (
    echo [OK] Compilando y ejecutando HMI en Rust (Windows nativo)...
    cargo run -p hmi-gui
    goto :fin
)

:: 2. Si no esta en Windows, ejecutar a traves de WSL con WSLg
where wsl >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Cargo no detectado en el PATH de Windows.
    echo [OK] Ejecutando HMI en Rust a traves de WSL / WSLg...
    wsl bash -c "cd /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust && cargo run -p hmi-gui"
    goto :fin
)

echo ========================================================
echo [ERROR] No se detecto Rust (cargo) en Windows ni WSL.
echo Instale Rust desde https://rustup.rs para compilar.
echo ========================================================
pause
exit /b 1

:fin
