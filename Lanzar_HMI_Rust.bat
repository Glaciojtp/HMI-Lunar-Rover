@echo off
title HMI Rover Lunar V2.0 - Rust Desktop GUI
cd /d "%~dp0"

echo ========================================================
echo   [INICIO] HMI ROVER LUNAR V2.0 - APLICACION EN RUST
echo ========================================================
echo.

:: 1. Comprobar si existe el binario Windows precompilado
if exist "target\release\hmi-gui.exe" (
    echo [INFO] Binario nativo Windows detectado en target\release.
    start "" "target\release\hmi-gui.exe"
    exit /b 0
)

:: 2. Comprobar si cargo esta disponible en Windows directamente
where cargo >nul 2>&1
if not errorlevel 1 (
    echo [OK] Compilando y ejecutando HMI en Rust (Windows nativo)...
    cargo run -p hmi-gui
    if errorlevel 1 (
        echo.
        echo [ERROR] La aplicacion finalizo con codigo de error %errorlevel%.
        pause
    )
    goto :fin
)

:: 3. Si no esta en Windows, ejecutar a traves de WSL con WSLg
where wsl >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Cargo no detectado en el PATH de Windows.
    echo [OK] Ejecutando HMI en Rust a traves de WSL / WSLg...
    wsl bash -lc "cd /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust && cargo run -p hmi-gui"
    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo la ejecucion de la HMI a traves de WSL (codigo %errorlevel%).
        pause
    )
    goto :fin
)

echo ========================================================
echo [ERROR] No se detecto Rust (cargo) en Windows ni WSL.
echo Instale Rust desde https://rustup.rs para compilar.
echo ========================================================
pause
exit /b 1

:fin
echo.
echo [INFO] Sesion de HMI finalizada.
pause
