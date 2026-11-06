# Guia para agentes y desarrolladores: Rover Lunar

Lee este archivo antes de tocar el repositorio. Despues lee `HANDOVER_SESION.md` (estado vivo) y `CHANGELOG.md`.

**Sin emojis** en codigo, documentacion, commits ni respuestas. Estilo tecnico y directo, en espanol.

---

## 1. Regla principal: un solo archivo activo por pieza

El sistema activo son exactamente estos cuatro archivos. No puede haber otro firmware ni otra HMI en `01_Oficial/`.

| Pieza | Archivo |
|---|---|
| Firmware del transmisor (Nano ESP32 conectado a la PC) | `01_Oficial/Transmisor_NanoESP32/Transmisor_NanoESP32.ino` |
| Firmware del ejecutor (Nano ESP32 a bordo) | `01_Oficial/Ejecutor_NanoESP32/Ejecutor_NanoESP32.ino` |
| HMI normal (pilotaje) | `01_Oficial/HMI/HMI_Rover.py` |
| HMI debug (dos placas por USB, compara y grafica) | `01_Oficial/HMI/HMI_Rover_Debug.py` |

`tests/test_estructura.py` falla si esta regla se rompe. CI lo ejecuta en cada push.

### Como cambiar algo

1. **Mejora o correccion:** se edita el archivo activo. El historial queda en git. Prohibido crear `_v2`, `_pre`, `_nuevo`, `_final` o copias similares.
2. **Experimento:** en una rama de git (`exp/descripcion`), nunca en una copia dentro de `main`.
3. **Sketch de banco o prueba puntual:** en una rama o fuera del repositorio. Si tiene valor de referencia una vez terminado, va a `04_Deprecado/Bancos_de_Prueba/`.
4. **Reemplazo completo de una pieza:** el archivo anterior se mueve con `git mv` a `04_Deprecado/` y se agrega una fila al indice `04_Deprecado/README.md` (que era, por que se reemplazo, que lo reemplaza). El nuevo toma el nombre fijo de la tabla.
5. **Trabajo que todavia no se usa** (LiDAR, Rust, joystick): en `05_Futuro/`, nunca en `01_Oficial/`.

### Al terminar cada cambio

1. `python -m unittest discover -s tests` debe pasar.
2. Si cambio el firmware, compilar los dos sketches con el nucleo real (seccion 6).
3. Actualizar `CHANGELOG.md` y, si cambio el estado del proyecto, `HANDOVER_SESION.md`.
4. Si cambio la arquitectura, el cableado o el protocolo, actualizar `README.md`, este archivo y el esquematico.
5. Declarar por separado lo verificado en PC y lo verificado en hardware. Una prueba en PC no valida el hardware.

---

## 2. Estructura

```text
01_Oficial/                 Los cuatro archivos activos
03_Documentacion_y_Guias/   Esquematico vigente y material de estudio
04_Deprecado/               Todo lo reemplazado, con indice. No se usa ni se modifica
05_Futuro/                  Rust + LiDAR y joystick. Fuera de uso por ahora
tests/                      Pruebas de estructura, firmware (banco en PC) y HMI
```

En la raiz solo hay documentos principales (`README.md`, `AGENTS.md`, `CHANGELOG.md`, `HANDOVER_SESION.md`) y lanzadores `.bat`.

---

## 3. Arquitectura vigente

```text
HMI (PC) --USB 115200--> Nano ESP32 transmisor --WiFi UDP 4210--> Nano ESP32 ejecutor --> Motores y servos
         <--------------                       <-- telemetria ---
```

- El transmisor es el Access Point `ROVER_NET` (192.168.4.1, canal 6). Va alimentado por USB, por eso la emision permanente queda de ese lado.
- El ejecutor es estacion con IP fija 192.168.4.2.
- El nRF24L01 y el MKR 1310 ya no se usan.

### Pines del ejecutor

| Funcion | Pin |
|---|---|
| L9110S A1A / A1B (lado izquierdo) | D2 / D5 |
| L9110S B1A / B1B (lado derecho) | D3 / D4 |
| PCA9685 SDA / SCL | A4 / A5 |
| Servos S1 / S2 / S3 / S4 | Canales 0 / 1 / 2 / 3 del PCA9685 |

El rover lleva 3 modulos L9110S dobles comandados en paralelo, que es el valor por defecto (`PUENTE_H_L298N 0`), con `INVERTIR_IZQ` e `INVERTIR_DER` en `true` (validado en el rover). Con `PUENTE_H_L298N 1` el firmware usa L298N: ENA/IN1/IN2 en D2/D3/D4 y ENB/IN3/IN4 en D5/D6/D7. Las pruebas compilan las dos variantes.

Los GPIO 14, 25, 26, 27, 32 y 33 de versiones anteriores son numeracion de ESP32 clasico. No usarlos en esta placa.

---

## 4. Protocolo

**HMI a transmisor:** `CMD,izq,der,s1,s2,s3,s4`, `STOP`, `IDENT`, `PING`. Los PWM llevan signo real.

**Mando de la HMI:** direccion y traccion separadas. `A`, `D`, `Q` y `E` solo orientan las ruedas; solo `W` y `S` mueven los motores. Lo define `calcular_consigna` en `HMI_Rover.py` y lo cubren las pruebas de `TestCinematica`.

**Placas a PC:** `TX,...`, `RX,...`, `TLM,...`, `LINK,...`, `BOOT,...`, `ID:NANO_ESP32:<TX|RX>:<version>`. El formato exacto esta en la cabecera de cada firmware y en `CAMPOS_*` de `HMI_Rover.py`.

**Transmisor y ejecutor por UDP:** binario `PaqueteControl` (13 bytes) y `PaqueteTelemetria` (34 bytes), con CRC-8.

Un cambio de protocolo se hace a la vez en los dos `.ino` y en `HMI_Rover.py`, y sube `VERSION_FW`. Las pruebas verifican que las estructuras y los formatos coincidan.

---

## 5. Reglas obligatorias de seguridad

Vienen de incidentes reales.

**Software**

1. Angulos de servo siempre en `[10, 170]`. Un pulso fuera de rango deja al servo forzando contra el tope, consumiendo corriente de bloqueo.
2. El ejecutor debe parar motores y centrar servos tras `TIMEOUT_MS = 1000` sin tramas. El transmisor debe ordenar parada tras `HMI_TIMEOUT_MS = 500` sin consignas.
3. Sin `delay()` en firmware: todo con `millis()`. La salida USB nunca debe bloquear el lazo.
4. La HMI debe enviar consignas de forma continua a 20 Hz. Enviar solo al cambiar una tecla dispara los failsafes.
5. No quitar los limitadores de corriente del ejecutor (rampas, desfase, servos escalonados, fases del PCA9685, arranque por etapas) sin una medicion que lo justifique.
6. No desactivar el detector de brownout: oculta el problema y arriesga corromper la memoria.

**Hardware**

1. Motores, servos y logica en rieles separados con masa comun en estrella. Detalle en `03_Documentacion_y_Guias/Esquematicos/ESQUEMATICO_NANO_ESP32.md`.
2. Servos alimentados solo por regulador conmutado (buck o UBEC) a 5-6 V. Nunca por el Arduino, ni por regulador lineal tipo 7805, ni directo de bateria (asi se quemo un SG90 a 8 V).
3. El USB de la PC no puede alimentar motores ni servos.

---

## 6. Verificacion

```bash
python -m unittest discover -s tests

arduino-cli core install arduino:esp32
arduino-cli lib install "Adafruit PWM Servo Driver Library"
arduino-cli compile --fqbn arduino:esp32:nano_nora 01_Oficial/Transmisor_NanoESP32
arduino-cli compile --fqbn arduino:esp32:nano_nora 01_Oficial/Ejecutor_NanoESP32
```

- `tests/test_firmware.py` ejecuta los `.ino` reales en la PC con hardware simulado (requiere g++). Valida la logica, no las bibliotecas reales ni la electronica.
- `tests/banco_firmware/stubs/` debe seguir la API real de Arduino. Si el firmware usa una funcion nueva, agregarla con la misma firma.
- Las pruebas de interfaz requieren Tkinter y se omiten donde no este (por ejemplo, WSL sin `python3-tk`).

---

## 7. Equipo

- **Joaquin:** comunicacion inalambrica.
- **Lucas:** PCB.
- **Lucio y Sebastian:** mecanismos de traccion y direccion. **Sebastian:** adquisicion de componentes.
- **Emir:** firmware del transmisor, ejecutor y camara.
- **Benjamin:** zonas de prueba y misiones analogas.
- **Keila y Ainsworth:** fisica de rodadura e informe de aplicaciones.

---

## 8. Hoja de ruta

1. v3.0 validada en el rover con L9110S. Probar el mando de la v3.1 y publicar la HMI como ejecutable.
2. Ensayos en rampa a 20 grados (CEPIT) y en terreno natural (Sierra).
3. Joystick fisico (`05_Futuro/Joystick/`).
4. Encoders y control PID.
5. PCB definitiva.
6. Camara ESP32-CAM, LiDAR y HMI en Rust (`05_Futuro/Rust_LiDAR/`).
