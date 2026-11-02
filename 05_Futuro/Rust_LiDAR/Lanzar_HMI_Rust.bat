@echo off
title HMI Rover Lunar V2.0 - Rust Desktop GUI Launcher
cd /d "%~dp0..\..\..\HMI-Lunar-Rover-Rust"

if not exist "%cd%\Cargo.toml" (
    echo [ERROR] No se encontro la carpeta del proyecto en Rust en:
    echo %cd%
    echo.
    pause
    exit /b 1
)

call "%cd%\Lanzar_HMI_Rust.bat"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] El lanzador de Rust finalizo con error.
    pause
)
