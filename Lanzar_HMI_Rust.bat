@echo off
title HMI Rover Lunar V2.0 - Rust Desktop GUI
cd /d "%~dp0"

echo ========================================================
echo   [INICIO] HMI ROVER LUNAR V2.0 - APLICACION EN RUST
echo ========================================================
echo.

:: 1. Comprobar si existe el binario Windows precompilado
if exist "%~dp0target\release\hmi-gui.exe" (
    echo [INFO] Binario nativo Windows detectado en target\release.
    start "" "%~dp0target\release\hmi-gui.exe"
    goto fin
)

:: 2. Comprobar si cargo esta disponible en Windows directamente
where cargo >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Compilando y ejecutando HMI en Rust [Windows nativo]...
    cargo run --release -p hmi-gui
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] La aplicacion finalizo con codigo de error %errorlevel%.
        pause
    )
    goto fin
)

:: 3. Ejecucion a traves de WSL / WSLg
where wsl >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Cargo no detectado en el PATH de Windows.
    echo [OK] Iniciando HMI en Rust a traves de WSL / WSLg...
    if exist "%~dp0target\release\hmi-gui" (
        echo [INFO] Ejecutando binario release optimizado precompilado...
        wsl /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/target/release/hmi-gui
    ) else if exist "%~dp0target\debug\hmi-gui" (
        echo [INFO] Ejecutando binario debug precompilado...
        wsl /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/target/debug/hmi-gui
    ) else (
        echo [INFO] Compilando y ejecutando con Cargo en WSL...
        wsl --cd /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust /home/joaqu/.cargo/bin/cargo run --release -p hmi-gui
    )
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Fallo la ejecucion de la HMI a traves de WSL [codigo %errorlevel%].
        pause
    )
    goto fin
)

echo ========================================================
echo [ERROR] No se detecto Rust ni WSL instalado en Windows.
echo Instale Rust desde https://rustup.rs o habilite WSL.
echo ========================================================
pause
exit /b 1

:fin
echo.
echo [INFO] Sesion de HMI finalizada.
pause
