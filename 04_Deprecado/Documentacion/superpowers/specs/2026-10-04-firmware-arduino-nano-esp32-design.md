# Documento de Diseno Tecnico: Firmware Arduino Nano ESP32 Transmisor y Receptor
## Proyecto: Rover Lunar V2.0 (Arquitectura Rocker-Bogie 6x6 + 4WS)
### Fecha: 2026-10-04 | Estado: Aprobado | Version de Referencia: v2.2-pre

---

## 1. Vision General y Objetivos de Diseno

El presente documento especifica la arquitectura, interfaces de hardware, protocolos binarios de comunicacion y maquinas de estado para la implementacion de los firmwares correspondientes a la plataforma unificada **Arduino Nano ESP32** (microcontrolador Espressif ESP32-S3 a 3.3V nativo), tanto en el rol de **Transmisor (Dongle USB-RF / Wi-Fi)** como en el rol de **Receptor (Control a bordo del chasis Rocker-Bogie)**.

### Objetivos Clave
1. **Unificacion de Plataforma de Hardware:** Estandarizar ambos nodos sobre el microcontrolador oficial del proyecto (Arduino Nano ESP32, perfil `ARDUINO_NANO_ESP32`).
2. **Arquitectura Hibrida Dual:** Permitir mediante la directiva `#define MODO_CONEXION_WIFI 1` o `0` alternar entre el canal primario de laboratorio (Wi-Fi Nativo SoftAP + UDP en puerto 4210) y el canal de radiofrecuencia (NRF24L01+ a 2.508 GHz / canal 108 a 250 kbps) sin duplicar bases de codigo.
3. **Control Integral de Actuadores en Receptor:** Soportar traccion de 6 motores DC sobre Puente H L9110S mediante 4 canales hardware LEDC a 1000 Hz, y direccion en 4 ruedas (4WS) mediante 4 canales hardware LEDC a 50 Hz con soporte configurable para servos 180 estandar y servos 360 continuos con almacenamiento Flash NVS.
4. **Seguridad y Robustez en Tiempo Real:** Cero llamadas bloqueantes a `delay()` en los lazos de control principales, watchdog failsafe de 1000 ms con corte total de potencia ante perdida de enlace y telemetria estructurada hacia el HMI.
5. **Cumplimiento Estricto de Reglas del Repositorio:** Cero emojis en codigo, cabeceras, documentacion y registros. Respeto al tamano exacto de trama binaria (8 bytes) y a los limites angulares mecanicos [10 deg, 170 deg].

---

## 2. Arquitectura de Comunicaciones y Estructura de Trama

### 2.1. Estructura Binaria de Datos (`PaqueteControl.h`)
Para asegurar la compatibilidad total con la HMI en Python (`HMI_Rover_V2_1.py`, `HMI_Rover_Debug.py`) y el stack paralelo en Rust (`protocol-rover`), la trama se define estrictamente empaquetada:

```cpp
#ifndef PAQUETE_CONTROL_H
#define PAQUETE_CONTROL_H

#include <stdint.h>

struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Traccion lado izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Traccion lado derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izquierdo [10 - 170 deg]
  uint8_t angulo_s2;     // S2: Delantero Derecho   [10 - 170 deg]
  uint8_t angulo_s3;     // S3: Trasero Izquierdo   [10 - 170 deg]
  uint8_t angulo_s4;     // S4: Trasero Derecho     [10 - 170 deg]
};

#endif // PAQUETE_CONTROL_H
```
- **Tamano total:** Exactamente 8 bytes (`sizeof(PaqueteControl) == 8`).
- **Asercion estatica:** Verificacion en tiempo de compilacion mediante `static_assert(sizeof(PaqueteControl) == 8, "PaqueteControl debe tener exactamente 8 bytes");`.

### 2.2. Modos de Comunicacion
- **Canal 1: Wi-Fi Nativo (SoftAP + UDP) [MODO_CONEXION_WIFI 1]:**
  - **Receptor:** Configura punto de acceso SoftAP con SSID `ROVER_NET`, clave `rover1234`, IP fija `192.168.4.1`, puerto UDP local `4210`.
  - **Transmisor:** Configura interfaz en modo estacion (STA), conecta a `ROVER_NET` y envia datagramas UDP unicast dirigidos a `192.168.4.1:4210`.
  - **Tolerancia a fallos:** Reconexion automatica no bloqueante en Transmisor cada 3000 ms si el estado Wi-Fi cae.
- **Canal 2: Radiofrecuencia NRF24L01+ [MODO_CONEXION_WIFI 0]:**
  - **Bus SPI Hardware:** Pines de Arduino Nano ESP32: CE = Pin D9 (GPIO 18), CSN = Pin D10 (GPIO 21), MOSI = Pin D11 (GPIO 38), MISO = Pin D12 (GPIO 47), SCK = Pin D13 (GPIO 48).
  - **Alimentacion:** VCC a 3.3V con capacitor electrolitico obligatorio (10 uF a 100 uF) a GND.
  - **Parametros RF:** Canal 108 (2.508 GHz), `RF24_PA_MAX`, `RF24_250KBPS`, AutoAck deshabilitado (streaming de baja latencia), Pipe `"ROVER"`.

---

## 3. Diseno Detallado: Firmware Transmisor (Dongle USB-RF / Wi-Fi)

### 3.1. Asignacion de Pines y Perifericos
- **USB Serial CDC:** 115200 bps (nativo USB ESP32-S3).
- **LED RGB Integrado (Anodo comun, activo en nivel LOW):**
  - Pin Rojo: GPIO 46
  - Pin Verde: GPIO 0
  - Pin Azul: GPIO 45
- **Estados Visuales:**
  - Azul solido: Transmisor en reposo / listo / enlace activo.
  - Pulso verde no bloqueante (30 ms): Datagrama emitido exitosamente.
  - Pulso rojo no bloqueante (50 ms): Error de transmision, bus SPI sin respuesta o perdida de asociacion Wi-Fi.

### 3.2. Maquina de Estados y Lazo Principal
1. **Streaming Continuo a 20 Hz:** Cada 50 ms (`INTERVALO_ENVIO_MS = 50`), emite la consigna vigente hacia el Rover para alimentar su watchdog failsafe.
2. **Emision Inmediata ante Consigna:** Al recibir un comando valido en el puerto serie, actualiza el estado y emite inmediatamente la trama sin esperar el proximo intervalo de 50 ms.
3. **Parseo de Consignas Seriales:**
   - Handshake:
     - `IDENT` -> `ID:NANO_ESP32:TX:v2.2`
     - `PING` -> `PONG:TX:NANO_ESP32`
   - Parada total:
     - `STOP` / `PARAR` -> Fuerza traccion 0, servos a 90 deg, emite inmediatamente y retorna `STATUS:STOP`.
   - Consignas estructuradas CSV:
     - `CMD,izq,der,s1,s2,s3,s4`
     - Modos de teclado directo: `W`, `S`, `A`, `D`, `PIVOT_IZQ`, `PIVOT_DER`, `CRAB`.
   - Reenvio transparente por UDP:
     - En modo Wi-Fi, cualquier cadena ASCII no reconocida como consigna cinematica (ej. `MOTORES:ON`, `MOTORES:OFF`, `INV:...`, `S1=...`, `NEUTRO,...`, `GUARDAR`, `VER`) es retransmitida de forma transparente hacia el puerto UDP del Rover para permitir configuracion remota sin cables.

---

## 4. Diseno Detallado: Firmware Receptor (A Bordo del Rover)

### 4.1. Asignacion de Pines y Canales Hardware LEDC
- **Traccion Puente H L9110S (LEDC 1000 Hz, 8 bits: duty 0 a 255):**
  - Pin D2 (A1A / GPIO 4): Canal LEDC 4 (Izquierda Avance).
  - Pin D5 (A1B / GPIO 7): Canal LEDC 5 (Izquierda Reversa).
  - Pin D3 (B1A / GPIO 5): Canal LEDC 6 (Derecha Avance).
  - Pin D4 (B1B / GPIO 6): Canal LEDC 7 (Derecha Reversa).
  - Configurado por defecto con `invertirDirIzq = true` para marcha colineal directa.
- **Servomotores de Direccion 4WS (LEDC 50 Hz, 14 bits: duty 0 a 16383):**
  - S1 (Delantero Izquierdo): Pin D6 (GPIO 8) - Canal LEDC 0.
  - S2 (Delantero Derecho):   Pin D7 (GPIO 9) - Canal LEDC 1.
  - S3 (Trasero Izquierdo):   Pin D8 (GPIO 10) - Canal LEDC 2.
  - S4 (Trasero Derecho):     Pin A0 (GPIO 1) - Canal LEDC 3.

### 4.2. Submodulo de Direccion Dual (Estandar 180 vs Rotacion Continua 360)
El receptor incluye la directiva `#define USAR_SERVOS_360_CONTINUOS 1` o `0`:
1. **Modo Servos 360 con Persistencia Flash NVS (`USAR_SERVOS_360_CONTINUOS 1`):**
   - Biblioteca `<Preferences.h>` en namespace `rover_calib`.
   - Parametros almacenados: `neutroS1..neutroS4` (microsegundos exactos de parada), `duracionGiroMs` (por defecto 140 ms), `deltaVelGiro` (por defecto 90 us), `dirS1..dirS4` (sentido individual) e `invertirSentidoServos`.
   - Maquina de estados no bloqueante con pulsos temporizados: al solicitar viraje (teclas `A` o `D`), aplica `deltaVelGiro` durante `duracionGiroMs` y corta de inmediato al neutro exacto, impidiendo el giro descontrolado continuo.
   - Comandos de calibracion interactiva por Serial/UDP: `S1+`, `S1-`, `S1=1510`, `NEUTRO,1500,1500,1500,1500`, `GUARDAR`, `VER`, `INVS1..INVS4`.
2. **Modo Servos 180 Estandar (`USAR_SERVOS_360_CONTINUOS 0`):**
   - Mapeo lineal de grados [10 deg, 170 deg] a microsegundos (500 us a 2500 us).
   - Centrado seguro inicial en 90 deg.

### 4.3. Watchdog Failsafe y Telemetria
- **Temporizador Failsafe:** Variable `ultimaRecepcion`. Si `millis() - ultimaRecepcion > 1000` ms, se dispara la parada total inmediata (`pararMotores()`). Emite por puerto serie una alerta estructurada cada 1000 ms: `TLM:FAILSAFE,0,90,90,90,90,1000,0`.
- **Habilitacion de Traccion:** Variables booleanas `motoresHabilitados` controlables mediante comandos de texto `MOTORES:OFF` (seguridad en banco) y `MOTORES:ON`.
- **Handshake Receptor:** Responde al comando `IDENT` con `ID:NANO_ESP32:RX:v2.2`.

---

## 5. Mapeo de Archivos y Flujo en el Repositorio

1. **Firmware Transmisor Arduino Nano ESP32:**
   - `02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre.ino`
   - `02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h`
   - Actualizacion sincronizada en `02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino`.
2. **Firmware Receptor Arduino Nano ESP32:**
   - `02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre.ino`
   - `02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h`
3. **Integracion con el Sistema HMI:**
   - Actualizar `hardware_profiles.py` en `01_Oficial/HMI/` y `02_Debug_y_Pruebas/HMI_Debug/` para que el sketch de transmision apunte al sketch unificado.
