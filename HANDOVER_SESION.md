# DOCUMENTO DE TRASPASO DE SESION Y ESTADO VIVO (HANDOVER)
## PROYECTO: ROVER LUNAR V2.0

> **PROPOSITO DE ESTE DOCUMENTO:**  
> Este archivo resume el estado exacto del proyecto, arquitectura de hardware, conexiones, diagnosticos tecnicos resueltos y tareas pendientes. Esta disenado para que, al iniciar una **nueva conversacion con la IA** (para reiniciar la ventana de contexto y optimizar el consumo de tokens), el nuevo agente lea este documento y retome el trabajo inmediatamente sin perdida de informacion ni retrasos.

> [!IMPORTANT]
> **REGLA ESTRICTA DE COMUNICACION:** Cero uso de emojis en todo momento (documentacion, codigo, logs y respuestas).

---

## 1. Estado Actual de Versiones y Ciclo de Vida

Se aplica de manera obligatoria el ciclo: **Beta -> Pre-Release -> Release Oficial**.

| Nivel de Version | Estado | Componentes Asociados | Ubicacion de Archivos |
|---|---|---|---|
| **v2.1 Oficial (Release Estable)** | **PRODUCCION ACTIVA** | - Ejecutor Arduino Nano ESP32<br>- Transmisor ESP32-C3<br>- HMI de Pilotaje Python v2.1 | [`01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/`](01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/)<br>[`01_Oficial/Transmisor_PC_ESP32C3/Control_ESP32_C3_Optimizado/`](01_Oficial/Transmisor_PC_ESP32C3/Control_ESP32_C3_Optimizado/)<br>[`01_Oficial/HMI/HMI_Rover_V2_1.py`](01_Oficial/HMI/HMI_Rover_V2_1.py) |
| **v2.2-PRE (Pre-Release Experimental)** | **EN DESARROLLO** | - Ejecutor Nano ESP32 con calibracion NVS de neutro y pulsos de viraje para servos 360<br>- Transmisor Nano ESP32 Wi-Fi UDP (Dongle PC sin joystick)<br>- HMI v2.2-PRE | [`02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/`](02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/)<br>[`02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/`](02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/)<br>[`01_Oficial/HMI/HMI_Rover_V2_2_pre.py`](01_Oficial/HMI/HMI_Rover_V2_2_pre.py) |
| **Mini-Versiones Beta** | **LABORATORIO** | - Modulos de prueba unitaria, scripts de test y bancos de diagnostico | [`02_Debug_y_Pruebas/`](02_Debug_y_Pruebas/) |
| **Stack Paralelo en Rust** | **HOJA DE RUTA** | - GUI nativa egui + protocolos no_std | `C:\Users\joaqu\Desktop\HMI-Lunar-Rover-Rust/` |

---

## 2. Entorno de Hardware y Conexionado de Banco Activo

- **Modo de Comunicacion Actual:** Wi-Fi Nativo (SoftAP + UDP en puerto 4210).
  - El Arduino Nano ESP32 crea el punto de acceso `ROVER_NET` (pass `rover1234`, IP `192.168.4.1`).
  - El Transmisor (ESP32-C3 o Arduino Nano ESP32) conecta en modo estacion STA y envia tramas a `192.168.4.1:4210` a 20 Hz.
- **Puertos Serie USB Conectados en PC:**
  - `COM4`: Transmisor ESP32-C3 o Arduino Nano ESP32 Dongle USB (115200 bps).
  - `COM19`: Receptor / Ejecutor Arduino Nano ESP32 a bordo (115200 bps).
- **Actuadores de Traccion (6 Motores DC Amarillos en Puente H L9110S):**
  - Pin D2 (A1A) / Pin D5 (A1B): Lado Izquierdo (M1, M2, M3). Hardware LEDC canales 4 y 5 (1000 Hz, 8 bits). `invertirDirIzq = true`.
  - Pin D3 (B1A) / Pin D4 (B1B): Lado Derecho (M4, M5, M6). Hardware LEDC canales 6 y 7 (1000 Hz, 8 bits). `invertirDirDer = false`.
- **Actuadores de Direccion (4 Servomotores MG90S 360 de Rotacion Continua):**
  - S1: Delantero Izquierdo (Pin D6, LEDC canal 0, 50 Hz, 14 bits).
  - S2: Delantero Derecho   (Pin D7, LEDC canal 1, 50 Hz, 14 bits).
  - S3: Trasero Izquierdo   (Pin D8, LEDC canal 2, 50 Hz, 14 bits).
  - S4: Trasero Derecho     (Pin A0, LEDC canal 3, 50 Hz, 14 bits).
- **Estructura Binaria de Trama ([`PaqueteControl.h`](01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/PaqueteControl.h)):**
  - Exactamente 8 bytes empaquetados (`traccion_izq: int16`, `traccion_der: int16`, `s1..s4: uint8`).

---

## 3. Diagnosticos Tecnicos Clave Resueltos

### A. Reinicio del Arduino Nano ESP32 a PWM >= 100
- **Causa Fisica:** *Brownout Reset (BOR)* del procesador ESP32-S3. Al conmutar los 6 motores y 4 servos, se producen corrientes de pico transitorias (*inrush*) de 4 A a 6 A que desploman la tension de alimentacion por debajo de 2.8 V.
- **Inviabilidad de Reguladores Lineales LM (LM317, LM78xx, LM1117 a 3.3V):**
  - Para motores y servos es inviable: requieren 5V-6V (a 3.3V no tienen par) y disiparian mas de 10 W de calor puro, quemandose en segundos.
  - Para el Arduino tampoco es necesario: el Arduino Nano ESP32 **ya cuenta con su propio convertidor regulador a 3.3V integrado**, aceptando de 6V a 21V en su pin `VIN`.
- **Solucion Electrica Definitiva (3 Rieles con Star GND):**
  1. **Riel Traccion:** Bateria directa al puente H L9110S + capacitor electrolitico de 1000 uF en bornes.
  2. **Riel Servos:** Bateria -> Regulador conmutado Step-Down Buck (LM2596 o MP1584) ajustado a 5.0V-6.0V + capacitor electrolitico de 1000 uF -> VCC de los 4 servos MG90S.
  3. **Riel Logica (Arduino):** Bateria -> Diodo Schottky (1N5819 o SS34) -> Pin `VIN` del Arduino + capacitor de 470 uF en `VIN`. El diodo actua como UPS local e impide que los motores drenen el capacitor del Arduino.
  4. **Tierra Comun (GND):** Todos los negativos unidos en un unico punto estrella.

### B. Por que los Servos 360 siguen girando mientras se mantiene apretada la tecla "D"
- Los servos MG90S 360 no tienen potenciometro interno de posicion; el ancho del pulso controla **velocidad y sentido de rotacion continua** (no angulo).
- Mientras se mantiene presionada una tecla (`D`), la HMI emite continuamente paquetes a 20 Hz con `s1=60` (~1166 us).
- Como 1166 us < 1500 us de neutro, el motor interno recibe la orden de rotar continuamente a velocidad fija hasta que se suelta la tecla y la HMI envia 90° (~1500 us).
- En la version experimental **v2.2-PRE**, este comportamiento se resuelve con una maquina de estados de pulsos temporizados (`duracionGiroMs = 140 ms`) que corta a neutro exacto al terminar el pulso.

---

## 4. Instrucciones para Iniciar una Nueva Sesion con la IA

Cuando el usuario abra una nueva ventana de chat, el usuario o la IA deben seguir este procedimiento:
1. **Lectura obligatoria:** La nueva sesion de IA debe leer en su primer turno este archivo [`HANDOVER_SESION.md`](HANDOVER_SESION.md) y [`CHANGELOG.md`](CHANGELOG.md).
2. **Respetar la regla de oro:** Prohibicion absoluta de emojis en respuestas, codigo, documentacion y commits.
3. **No modificar la Release Oficial v2.1 directamente:** Cualquier nuevo experimento debe nacer en rama o archivo `beta` o en la pre-release `v2.2-PRE`, pasando por aprobacion antes de tocar los archivos de `01_Oficial/`.
4. **Actualizar este Handover:** Al finalizar tareas significativas, actualizar las tablas de este archivo para la sesion posterior.
