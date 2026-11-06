#!/bin/bash
set -e

EXE_NAME="${1:-HMI_Rover_Lunar_V2.exe}"
TARGET_PATH="/workspace/${EXE_NAME}"
LOG_FILE="/workspace/test_simulation_results.log"

echo "=========================================================="
echo "  🍷 BANCO DE PRUEBAS EN CONTENEDOR DOCKER (WINE 64-BIT)   "
echo "  Simulación de Windows Limpio para Rover Lunar V2.0 HMI   "
echo "=========================================================="
echo ""

if [ ! -f "$TARGET_PATH" ]; then
    echo "⚠️ [AVISO] No se encontró el archivo ejecutable: ${TARGET_PATH}"
    echo ""
    echo "Para probar el ejecutable en este entorno virtualizado:"
    echo " 1. En Windows, hacé doble clic en 'Compilar_HMI_a_EXE.bat'"
    echo " 2. Una vez generado '${EXE_NAME}', volvé a ejecutar este contenedor."
    echo ""
    echo "Archivos disponibles actualmente en /workspace:"
    ls -lh /workspace | grep -E "\.exe|\.bat|\.py|\.md" || ls -la /workspace
    exit 1
fi

echo "🔍 [1/3] Ejecutable detectado:"
ls -lh "$TARGET_PATH"
echo ""

echo "🚀 [2/3] Lanzando '${EXE_NAME}' en entorno virtual Windows con Xvfb..."
echo "Configuración: WINEARCH=${WINEARCH}, WINEDEBUG=${WINEDEBUG}"
echo "La prueba se ejecutará durante 15 segundos para validar arranque estable..."
echo ""

# Limpiar logs previos si existen
rm -f "$LOG_FILE" "/workspace/hmi_crash_log.txt"

# Ejecutar con timeout de 15 segundos en segundo plano con Xvfb
export DISPLAY=:99
Xvfb :99 -screen 0 1280x1024x24 > /dev/null 2>&1 &
XVFB_PID=$!

sleep 1

# Ejecutar Wine capturando salida
set +e
timeout 15s wine "$TARGET_PATH" > "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

# Matar Xvfb
kill $XVFB_PID > /dev/null 2>&1 || true

echo "📊 [3/3] Análisis de Resultados:"
echo "----------------------------------------------------------"

if [ -f "/workspace/hmi_crash_log.txt" ]; then
    echo "❌ [FALLO DETECTADO] Se generó reporte de crash en Python:"
    echo ""
    cat "/workspace/hmi_crash_log.txt"
    echo ""
elif [ $EXIT_CODE -eq 124 ]; then
    echo "✅ [ÉXITO TOTAL] El ejecutable arrancó y se mantuvo en ejecución de forma continua!"
    echo "(El temporizador de 15 segundos finalizó la prueba porque la ventana de la HMI permaneció abierta y estable)."
elif [ $EXIT_CODE -eq 0 ]; then
    echo "ℹ️ [INFO] El ejecutable finalizó normalmente (Exit Code 0)."
else
    echo "⚠️ [FALLO EN EJECUCIÓN] El ejecutable terminó prematuramente con código de salida: $EXIT_CODE"
fi

echo ""
echo "=== Registro detallado de Wine (últimas 30 líneas de $LOG_FILE) ==="
if [ -f "$LOG_FILE" ]; then
    tail -n 30 "$LOG_FILE"
else
    echo "No se generó archivo de log."
fi
echo "=========================================================="
