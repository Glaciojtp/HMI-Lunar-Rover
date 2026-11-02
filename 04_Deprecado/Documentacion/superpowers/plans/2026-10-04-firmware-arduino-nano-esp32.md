# Plan de Implementacion: Firmware Arduino Nano ESP32 Transmisor y Receptor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar y validar los firmwares para Arduino Nano ESP32 (ESP32-S3) tanto para el Transmisor (Dongle USB-RF/Wi-Fi) como para el Receptor a bordo del chasis Rocker-Bogie, con soporte dual Wi-Fi UDP / NRF24L01+ y compatibilidad total con el ecosistema HMI.

**Architecture:** Arquitectura modular asincrona no bloqueante basada en temporizadores de hardware LEDC de ESP32-S3 y sockets UDP / transceptor RF24. Transmisor y receptor comparten la estructura empaquetada de 8 bytes `PaqueteControl.h` e integran maquinas de estados de streaming a 20 Hz, failsafe temporal y telemetria estructurada.

**Tech Stack:** C++ / Arduino Framework (ESP32 Core para Arduino Nano ESP32), FreeRTOS / LEDC hardware timers, `<WiFi.h>`, `<WiFiUdp.h>`, `<RF24.h>`, `<Preferences.h>` (NVS Flash), Python 3 (HMI y tests pytest).

**Spec:** `docs/superpowers/specs/2026-10-04-firmware-arduino-nano-esp32-design.md`

## Global Constraints

- Prohibicion estricta y absoluta de emojis en todo comentario, cadena, documentacion, log y commit.
- Estructura `PaqueteControl` inmutable de exactamente 8 bytes con `__attribute__((packed))`.
- Cero llamadas bloqueantes a `delay()` en los lazos de control de `loop()`.
- Limite angular seguro de servomotores acotado estrictamente a [10, 170] grados.
- Watchdog failsafe de parada obligatoria tras 1000 ms sin tramas de control.
- Frecuencia y canal RF fijos: canal 108 (2.508 GHz) a 250 kbps con direccion `"ROVER"`.
- Credenciales Wi-Fi unificadas: SSID `"ROVER_NET"`, Clave `"rover1234"`, IP `"192.168.4.1"`, Puerto UDP `4210`.

---

### Task 1: Estandarizacion de Cabecera Binaria y Validacion Estatica

**Files:**
- Create: `02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h`
- Modify: `02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/PaqueteControl.h`
- Modify: `02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h`
- Test: `02_Debug_y_Pruebas/HMI_Debug/test_paquete_control_binario.py`

**Interfaces:**
- Consumes: Tipos estandar de C99 `<stdint.h>`.
- Produces: `struct __attribute__((packed)) PaqueteControl` de 8 bytes exactos.

- [ ] **Step 1: Escribir el test unitario de verificacion de empaquetado binario**

Crear `02_Debug_y_Pruebas/HMI_Debug/test_paquete_control_binario.py`:
```python
import struct
import pytest

def test_tamano_paquete_control():
    # Estructura: int16 traccion_izq, int16 traccion_der, uint8 s1, uint8 s2, uint8 s3, uint8 s4
    # Little-endian: <hh4B
    formato = "<hh4B"
    tamano = struct.calcsize(formato)
    assert tamano == 8, f"El tamano esperado es 8 bytes, pero se calculo {tamano}"

def test_empaquetado_y_desempaquetado_valores_limite():
    formato = "<hh4B"
    # Valores de prueba representativos
    trac_izq = -255
    trac_der = 255
    s1, s2, s3, s4 = 10, 90, 170, 90
    empaquetado = struct.pack(formato, trac_izq, trac_der, s1, s2, s3, s4)
    assert len(empaquetado) == 8

    desemp = struct.unpack(formato, empaquetado)
    assert desemp[0] == -255
    assert desemp[1] == 255
    assert desemp[2] == 10
    assert desemp[3] == 90
    assert desemp[4] == 170
    assert desemp[5] == 90
```

- [ ] **Step 2: Ejecutar el test para comprobar su funcionamiento**

Ejecutar: `pytest 02_Debug_y_Pruebas/HMI_Debug/test_paquete_control_binario.py -v`
Resultado esperado: 2 tests passed.

- [ ] **Step 3: Implementar y sincronizar `PaqueteControl.h` en todos los directorios destino**

Escribir en `02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h` y sincronizar en los demas:
```cpp
#ifndef PAQUETE_CONTROL_H
#define PAQUETE_CONTROL_H

#include <stdint.h>

// ==========================================
// ESTRUCTURA BINARIA ESTRICTA DE CONTROL (8 BYTES)
// Rover Lunar V2.0 — Protocolo Rocker-Bogie 4WS
// ==========================================
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // -255 a 255 (Lado Izquierdo: M1, M2, M3)
  int16_t traccion_der;  // -255 a 255 (Lado Derecho:   M4, M5, M6)
  uint8_t angulo_s1;     // S1: Delantero Izq [10 - 170 deg]
  uint8_t angulo_s2;     // S2: Delantero Der [10 - 170 deg]
  uint8_t angulo_s3;     // S3: Trasero Izq   [10 - 170 deg]
  uint8_t angulo_s4;     // S4: Trasero Der   [10 - 170 deg]
};

#endif // PAQUETE_CONTROL_H
```

- [ ] **Step 4: Commit de la cabecera unificada y tests**

```bash
git add 02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/PaqueteControl.h 02_Debug_y_Pruebas/HMI_Debug/test_paquete_control_binario.py
git commit -m "feat: unificar cabecera binaria PaqueteControl.h y agregar test de empaquetado"
```

---

### Task 2: Implementar Firmware Transmisor Arduino Nano ESP32

**Files:**
- Create: `02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre.ino`
- Modify: `02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino`

**Interfaces:**
- Consumes: `PaqueteControl` desde `PaqueteControl.h`.
- Produces: Datagramas UDP a `192.168.4.1:4210` o paquetes RF24 en canal 108; respuestas de handshake `ID:NANO_ESP32:TX:v2.2`.

- [ ] **Step 1: Implementar codigo completo del Transmisor Arduino Nano ESP32**

Implementar soporte hibrido `#define MODO_CONEXION_WIFI 1`:
- Handshake `IDENT` -> `ID:NANO_ESP32:TX:v2.2`.
- `PING` -> `PONG:TX:NANO_ESP32`.
- Modo Wi-Fi: STA hacia `ROVER_NET`, IP de destino `192.168.4.1`, puerto `4210`.
- Modo RF24: SPI hardware con pines D9 (CE), D10 (CSN), D11 (MOSI), D12 (MISO), D13 (SCK).
- LED RGB integrado en GPIO 46 (Rojo), GPIO 0 (Verde), GPIO 45 (Azul), anodo comun.
- Lazo de streaming a 20 Hz (`INTERVALO_ENVIO_MS = 50 ms`) continuo.
- Disparo inmediato ante nueva consigna por USB CDC.
- Reenvio transparente de comandos ASCII de depuracion/calibracion por UDP.
- Reconexion automatica Wi-Fi no bloqueante cada 3000 ms.

- [ ] **Step 2: Verificar sintaxis y consistencia estatica del firmware**

Revisar prototipos, balance de llaves, aserciones `static_assert` e inclusiones.

- [ ] **Step 3: Sincronizar codigo en `02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/`**

Copiar la implementacion para garantizar compatibilidad con perfiles previos.

- [ ] **Step 4: Commit del firmware Transmisor**

```bash
git add 02_Debug_y_Pruebas/Firmware_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre/Transmisor_ArduinoNano_ESP32_v2_2_pre.ino 02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino
git commit -m "feat: implementar firmware transmisor unificado para Arduino Nano ESP32"
```

---

### Task 3: Implementar Firmware Receptor Arduino Nano ESP32

**Files:**
- Modify: `02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre.ino`

**Interfaces:**
- Consumes: Datagramas UDP entrantes en puerto 4210 o tramas RF24 de 8 bytes (`PaqueteControl`).
- Produces: Señales PWM LEDC en Puente H L9110S (D2, D5, D3, D4) y 4 Servomotores (D6, D7, D8, A0); telemetria por USB CDC `TLM:...`.

- [ ] **Step 1: Implementar codigo completo del Receptor Arduino Nano ESP32**

Implementar:
- `#define MODO_CONEXION_WIFI 1` (SoftAP `ROVER_NET`, pass `rover1234`, UDP local `4210`) y alternativa NRF24 (`MODO_CONEXION_WIFI 0`).
- `#define USAR_SERVOS_360_CONTINUOS 1` (conmutador para servos de rotacion continua 360 con pulsos temporizados y NVS Flash `<Preferences.h>`) o `0` (servos 180 clasicos).
- Temporizadores de hardware LEDC:
  - Traccion: Canales 4, 5, 6, 7 (1000 Hz, 8 bits: duty 0 a 255) en D2, D5, D3, D4.
  - Direccion: Canales 0, 1, 2, 3 (50 Hz, 14 bits: 0 a 16383) en D6, D7, D8, A0.
- Failsafe Watchdog: 1000 ms (`TIMEOUT_MS = 1000`) sin tramas = parada total de motores.
- Handshake `IDENT` -> `ID:NANO_ESP32:RX:v2.2`.
- Procesador de comandos de calibracion interactiva (`S1+`, `S1-`, `NEUTRO,...`, `GUARDAR`, `VER`, `MOTORES:ON`, `MOTORES:OFF`, `INV:...`).

- [ ] **Step 2: Verificar limites de seguridad y no-bloqueo**

Asegurar ausencia de llamadas a `delay()` en lazo principal y confinamiento angular a [10, 170] grados.

- [ ] **Step 3: Commit del firmware Receptor**

```bash
git add 02_Debug_y_Pruebas/Firmware_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre/Ejecutor_ArduinoNano_ESP32_v2_2_pre.ino
git commit -m "feat: implementar firmware receptor unificado para Arduino Nano ESP32 v2.2-pre"
```

---

### Task 4: Actualizar Registro de Perfiles de Hardware e Integracion HMI

**Files:**
- Modify: `01_Oficial/HMI/hardware_profiles.py`
- Modify: `02_Debug_y_Pruebas/HMI_Debug/hardware_profiles.py`
- Test: `02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py`

**Interfaces:**
- Consumes: Clases `PerfilHardware` y `HardwareProfileRegistry`.
- Produces: Rutas resueltas de sketches TX y RX para `ARDUINO_NANO_ESP32` y soporte para versiones v2.2.

- [ ] **Step 1: Actualizar pruebas unitarias en `test_hardware_profiles.py`**

Asegurar que reconozca los nuevos handshakes (`ID:NANO_ESP32:TX:v2.2`, `ID:NANO_ESP32:RX:v2.2`).

- [ ] **Step 2: Ejecutar los tests de perfiles de hardware**

Ejecutar: `pytest 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py -v`
Resultado esperado: Tests pasando.

- [ ] **Step 3: Actualizar `hardware_profiles.py` en ambas ubicaciones**

Asegurar que `sketch_tx` y `sketch_rx` resuelvan a las rutas correspondientes.

- [ ] **Step 4: Re-ejecutar suite completa de tests de HMI Debug**

Ejecutar: `pytest 02_Debug_y_Pruebas/HMI_Debug/test_flasher_engine.py 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py -v`

- [ ] **Step 5: Commit de perfiles de hardware**

```bash
git add 01_Oficial/HMI/hardware_profiles.py 02_Debug_y_Pruebas/HMI_Debug/hardware_profiles.py 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py
git commit -m "feat: actualizar perfiles de hardware y handshakes v2.2 para Arduino Nano ESP32"
```

---

### Task 5: Actualizar Documentos de Estado Vivo (`HANDOVER_SESION.md` y `CHANGELOG.md`) y Verificacion Final

**Files:**
- Modify: `HANDOVER_SESION.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Actualizar `CHANGELOG.md`**

Registrar la adicion de los firmwares Transmisor y Receptor v2.2-pre para Arduino Nano ESP32.

- [ ] **Step 2: Actualizar `HANDOVER_SESION.md`**

Actualizar tablas de componentes de software, puertos, pinouts y rutas de firmware activo.

- [ ] **Step 3: Verificacion global de politicas (cero emojis, git status limpio)**

Ejecutar comprobacion contra emojis en archivos modificados y validar que el arbol de git quede ordenado.

- [ ] **Step 4: Commit final de documentacion y estado vivo**

```bash
git add HANDOVER_SESION.md CHANGELOG.md
git commit -m "docs: actualizar handover y changelog con soporte unificado de firmwares Nano ESP32 v2.2-pre"
```
