# REGISTRO DE CAMBIOS Y CONTROL DE VERSIONES (CHANGELOG)
## PROYECTO: ROVER LUNAR V2.0

> Documento de seguimiento historico y ciclo de vida de versiones para el proyecto Rover Lunar.
> Sigue rigurosamente la politica de transicion: **Beta -> Pre-Release -> Release Oficial**.
> Prohibicion estricta de emojis en todo el documento.

---

## Politica

Un solo archivo activo por pieza, editado en el lugar. Los experimentos van en ramas de git. Ver `AGENTS.md`. Esta politica reemplaza al ciclo Beta, Pre-Release y Release basado en copias de archivos.

---

## Historial de Versiones

### [v3.1] - 2026-11-06 (logica verificada en PC, mando pendiente de prueba en el rover)

#### HMI
- Direccion y traccion separadas. `A`, `D`, `Q` y `E` solo orientan las ruedas y no mueven los motores. Solo `W` y `S` mueven los motores, sobre la orientacion elegida.
- Pivote: `Q` + `W` gira en el lugar a la izquierda, `E` + `W` a la derecha. Con `S`, al reves.
- `W` y `S` juntas se anulan. Prioridad de direccion: `Q`, `E`, `A`, `D`.
- La etiqueta del mando combina traccion y direccion (por ejemplo `AVANCE + IZQUIERDA`).

#### Firmware
- Ejecutor: L9110S pasa a ser el puente H por defecto (`PUENTE_H_L298N 0`), porque es el montado en el rover. L298N sigue disponible y se puede elegir al compilar.
- Sin cambios de protocolo: los firmwares siguen informando v3.0 y son compatibles con esta HMI.

#### Pruebas
- El banco de firmware compila el ejecutor en las dos variantes de puente H. Pruebas nuevas para L9110S: pines por sentido, pivote, rampa e inversion por cero sin activar los dos pines a la vez.
- Pruebas de cinematica reescritas para el mando nuevo.

#### Estado
- v3.0 probada en el rover por el equipo: funciona con L9110S.

### [v3.0] - 2026-11-02 (compila y logica verificada en PC, pendiente de hardware)

#### Reorganizacion
- Sistema activo reducido a cuatro archivos en `01_Oficial/`: firmware del transmisor, firmware del ejecutor, HMI normal y HMI debug.
- `04_Legacy_y_Versiones_Previas/`, `02_Debug_y_Pruebas/` y el resto de versiones pasan a `04_Deprecado/`, con indice.
- Rust, LiDAR y joystick pasan a `05_Futuro/`.
- README (con estado actual y capturas de las HMI), AGENTS y esquematico reescritos. `tests/test_estructura.py` hace cumplir la regla.

#### Firmware
- El transmisor es el Access Point; el ejecutor es estacion con canal e IP fijos.
- Protocolo UDP nuevo con secuencia, CRC-8 y telemetria de retorno, incluida la causa del ultimo reinicio.
- Ejecutor: rampas de PWM, inversion por cero, arranque desfasado, servos escalonados, fases por canal en el PCA9685, arranque por etapas, potencia WiFi reducida y salida USB no bloqueante.
- Ejecutor: PCA9685 para servos, L298N por defecto, L9110S seleccionable. Pines corregidos para Nano ESP32.
- Transmisor: envio a 20 Hz fijos y parada si la HMI deja de enviar durante 500 ms.

#### HMI
- `HMI_Rover.py`: envio continuo a 20 Hz en hilo propio, signos reales, cadena de senales de conexion, alerta de reinicio, reconexion USB y parada al perder el foco.
- `HMI_Rover_Debug.py`: dos placas a la vez, comparacion por secuencia, graficas de enviado, recibido y aplicado, marcas de reinicio, perfiles de prueba y exportacion CSV.
- Se retiran el flasheo integrado, los perfiles de hardware, la calibracion NVS, el modo de servos 360 y la telemetria de joystick.

---

### [v2.3.0-pre] - 2026-10-06 (Pre-Release Servos Posicionales Estandar)

#### Modificado y Corregido
- **Firmware Receptor Nano ESP32 (`02_Debug_y_Pruebas/Firmware_v2_3_pre/`):**
  - Eliminacion radical del sistema de calibracion de neutros variables en microsegundos y la maquina de estados de pulsos temporizados (`duracionGiroMs`, `deltaVelGiro`, `ejecutarPulsoGiro()`).
  - Retorno estricto al control angular absoluto directo [10, 170] grados para servomotores posicionales estandar (180 deg) mediante `servo.write(angulo)`.
  - Posicion central neutra fija y estandar a 90 grados exactos en reposo y en el lazo de seguridad failsafe.
  - Supresion de escrituras continuas e innecesarias de nuevas posiciones neutras a memoria Flash NVS.
- **Firmware Transmisor Nano ESP32 (`02_Debug_y_Pruebas/Firmware_v2_3_pre/` y `02_Debug_y_Pruebas/Firmware_Debug/`):**
  - Actualizacion de puente USB-PC sin joysticks con soporte dual Wi-Fi UDP y NRF24L01+ SPI.
  - Transmision angular directa de consignas en grados para S1..S4.
  - Handshake activo: `IDENT` -> `ID:NANO_ESP32:TX:v2.3`.

### [v2.2.0-pre] - 2026-10-04 (Pre-Release Experimental Historica)

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
