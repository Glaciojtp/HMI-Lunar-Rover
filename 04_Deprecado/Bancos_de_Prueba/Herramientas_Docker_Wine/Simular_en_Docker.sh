#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=== Construyendo imagen Docker para simulación Wine ==="
docker build -t hmi-wine-simulator -f "$DIR/Herramientas_Docker_Wine/Dockerfile.wine-test" "$DIR/Herramientas_Docker_Wine"

echo "=== Ejecutando simulación en contenedor ==="
docker run --rm -v "$DIR:/workspace" hmi-wine-simulator "$@"
