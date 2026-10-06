# REGISTRO DE CAMBIOS Y CONTROL DE VERSIONES (CHANGELOG)
## PROYECTO: ROVER LUNAR V2.0

> Documento de seguimiento historico y ciclo de vida de versiones para el proyecto Rover Lunar.
> Sigue rigurosamente la politica de transicion: **Beta -> Pre-Release -> Release Oficial**.
> Prohibicion estricta de emojis en todo el documento.

---

## Politica de Ciclo de Vida del Software

1. **Fase Beta (Desarrollo Activo y Pruebas Unitarias):**
   - Todo cambio experimental, nueva funcion o correccion de errores se desarrolla inicialmente como una mini-version o rama `beta`.
   - Se realizan pruebas en banco de trabajo y se documenta cada modificacion en la bitacora de cambios.
   - Los archivos experimentales se ubican en `02_Debug_y_Pruebas/` o se identifican con sufijo `_beta`.
2. **Fase Pre-Release (Validacion Integral de Subsistemas):**
   - Una vez que la serie de cambios beta demuestra estabilidad funcional en hardware real y supera los tests unitarios, se consolida en una `pre-release` (ej. `v2.2-pre`).
   - Se evalua la interoperabilidad entre HMI (Python/Rust), Transmisor y Receptor en condiciones combinadas de traccion, direccion y telemetria.
3. **Fase Release Oficial (Produccion y Despliegue Estable):**
   - Al completarse todos los objetivos planificados del hito y verificarse la ausencia de regresiones, la pre-release se formaliza como `release` oficial definitiva (ej. `v2.1`, `v2.2`).
   - Los archivos de produccion se ubican exclusivamente en `01_Oficial/` y se actualizan los lanzadores inteligentes (`Lanzar_HMI_Rover.bat`, `Compilar_HMI_a_EXE.bat`).

---

## Historial de Versiones

### [v2.2.0-pre] - 2026-10-04 (Pre-Release Experimental Activa)

#### Agregado
- **Firmware Receptor Nano ESP32 (`02_Debug_y_Pruebas/Firmware_v2_2_pre/`):**
  - Sistema de calibracion de punto neutro (STOP absoluto) para servomotores MG90S 360 (rotacion continua).
  - Almacenamiento no volatil en memoria Flash NVS mediante biblioteca nativa `<Preferences.h>`.
  - Comandos interactivos de ajuste fino en tiempo real por puerto serie o Wi-Fi: `S1+`, `S1-`, `S1++`, `S1--`, `S1=1510`, `NEUTRO,...`, `GUARDAR`, `VER`.
  - Maquina de estados no bloqueante con pulsos temporizados (`duracionGiroMs = 140 ms`, `deltaVelGiro = 90 us`) para virajes acotados simetricos.
- **Firmware Transmisor Nano ESP32 (`02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/` y `02_Debug_y_Pruebas/Firmware_Debug/`):**
  - Implementacion de puente USB-PC a Wi-Fi UDP (Modo Estacion STA conectando a `ROVER_NET` en `192.168.4.1:4210`).
  - Diseno especifico para pilotaje por teclado/PC sin joysticks analogicos ni potenciometros fisicos.
  - Streaming continuo a 20 Hz (cada 50 ms) y emision inmediata ante nueva consigna serie.
  - Reenvio transparente por UDP de comandos ASCII directos de calibracion y diagnostico.
  - Telemetria visual con LED RGB integrado (GPIO 46, 0, 45, anodo comun) para enlace, transmision OK y errores.
  - Handshake activo: `IDENT` -> `ID:NANO_ESP32:TX:v2.2`.
- **HMI Python (`01_Oficial/HMI/HMI_Rover_V2_2_pre.py`):**
  - Soporte preparatorio de interfaz para la matriz de calibracion de servos continuos.

---

### [v2.1.0] - 2026-10-03 (Release Oficial Estable de Produccion)

#### Agregado y Consolidado
- **Firmware Receptor Nano ESP32 Oficial (`01_Oficial/Receptor_Rover_NanoESP32/`):**
  - Implementacion de clase `Servo` integrada nativa mediante temporizadores LEDC del ESP32-S3 (canales 0 a 3, 50 Hz, 14 bits), eliminando colisiones de compilacion con librerias externas.
  - Modularizacion de la trama binaria en cabecera independiente [`PaqueteControl.h`](01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/PaqueteControl.h), resolviendo el reordenamiento de prototipos del preprocesador de Arduino IDE.
  - Canales hardware LEDC dedicados para traccion (canales 4 a 7, 1000 Hz, 8 bits) en Puente H L9110S.
  - Polaridad de traccion estandarizada en modo directo con `invertirDirIzq = true` para marcha de avance colineal.
  - Doble enlace de comunicacion: Wi-Fi Nativo SoftAP (`ROVER_NET`, puerto UDP 4210) como modo primario de laboratorio, con soporte seleccionable para NRF24L01+.
  - Watchdog de seguridad failsafe con parada total automatica tras 1000 ms sin tramas validas.
- **Firmware Transmisor ESP32-C3 Oficial (`01_Oficial/Transmisor_PC_ESP32C3/`):**
  - Modo cliente Wi-Fi STA conectando a `ROVER_NET` y transmitiendo paquetes UDP a 20 Hz (cada 50 ms).
  - Reenvio transparente por UDP de comandos ASCII directos de depuracion y test.
- **HMI Python Oficial (`01_Oficial/HMI/HMI_Rover_V2_1.py` y `HMI_Rover_V2.py`):**
  - Matriz de autodeteccion pasiva de perfiles de hardware por USB VID:PID (`hardware_profiles.py`).
  - Motor de flasheo integrado en segundo plano (`flasher_engine.py`) con soporte para `arduino-cli` y `esptool`.
  - Geometria estatica y fija de interfaz grafica (eliminacion de desbordamientos y parpadeos al pulsar teclado).
  - Cinematica de direccion corregida en el canvas interactivo 2D (cajas de ruedas y vectores colineales a angulos reales).
  - Actualizacion de lanzadores Windows: [`Lanzar_HMI_Rover.bat`](Lanzar_HMI_Rover.bat) y [`Compilar_HMI_a_EXE.bat`](Compilar_HMI_a_EXE.bat) configurados a v2.1.

---

### [v2.0.0] - Version Inicial Base

- Implementacion inicial de control para chasis Rocker-Bogie 6x6.
- Comunicacion por radiofrecuencia NRF24L01 a 250 kbps en canal 108.
- Control preliminar con Arduino MKR WAN 1310 y ESP32-C3.
- Interfaz grafica de pilotaje en Python / Tkinter.
