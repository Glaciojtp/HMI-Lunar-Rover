@echo off
title Simulador de HMI en Docker Wine
cd /d "%~dp0.."
echo ========================================================
echo   🐳 SIMULADOR DE WINDOWS LIMPIO EN DOCKER (WINE)
echo   Verifica si el .exe corre en una PC sin dependencias
echo ========================================================
echo.
docker build -t hmi-wine-simulator -f "Herramientas_Docker_Wine\Dockerfile.wine-test" Herramientas_Docker_Wine
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo construir la imagen Docker.
    echo Asegurate de tener Docker Desktop iniciado.
    pause
    exit /b 1
)
echo.
echo [INFO] Iniciando contenedor de prueba con Wine...
docker run --rm -v "%cd%:/workspace" hmi-wine-simulator
echo.
pause
