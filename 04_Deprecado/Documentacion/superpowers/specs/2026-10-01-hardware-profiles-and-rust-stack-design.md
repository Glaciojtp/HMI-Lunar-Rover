# ESPECIFICACION DE DISENO: SISTEMA DE PERFILES DE HARDWARE, TRANSMISOR NANO ESP32 Y STACK PARALELO EN RUST

**Fecha:** 2026-10-01  
**Estado:** Propuesta aprobada en diseno preliminar  
**Modulo Principal:** Suite Debug (`02_Debug_y_Pruebas/`) y Workspace Paralelo (`HMI-Lunar-Rover-Rust`)  
**Regla Estricta:** Prohibicion absoluta de emojis en codigo, mensajes y documentacion.

---

## 1. Resumen Ejecutivo y Motivacion

El proyecto Rover Lunar V2.0 atraviesa una fase de transicion de hardware hacia el microcontrolador **Arduino Nano ESP32** (ESP32-S3 a 3.3V) como plataforma oficial estandarizada tanto para la recepcion de a bordo (chasis 6x6 Rocker-Bogie + direccion 4WS) como para la transmision terrena (dongle PC y futuro joystick fisico autonomo).

Para garantizar maxima compatibilidad durante esta transicion sin romper la estabilidad del sistema en produccion, se define:
1. Una matriz de perfiles de hardware modular y un sistema de autodeteccion por USB (VID:PID y handshake serie activo) en el HMI Debug (`HMI_Rover_Debug.py`), conservando inalterado el HMI de produccion (`01_Oficial/HMI/HMI_Rover_V2.py`).
2. El desarrollo del firmware oficial de transmision para Arduino Nano ESP32 (`Transmisor_ArduinoNano_ESP32.ino`) con conexion SPI simetrica y LED RGB de estado.
3. Un motor de flasheo en 1 clic desde la propia interfaz grafica para aprovisionar codigo en caliente.
4. Un procedimiento de calibracion pre-despliegue en banco de pruebas para sincronizar parametros al receptor antes de desconectarlo para operar en campo.
5. La creacion de un proyecto paralelo completo en Rust (`HMI-Lunar-Rover-Rust`) en el Escritorio con interfaz grafica nativa (`egui`/`eframe`) y firmwares embebidos (`esp-hal`).
6. Una evaluacion tecnica de viabilidad y costos para futuros modulos de camara y LiDAR de mapeo 3D en cuevas y tubos de lava.

---

## 2. Restricciones y Principios de Diseno

1. **Aislamiento de Produccion:** La interfaz oficial `01_Oficial/HMI/HMI_Rover_V2.py` no debe ser modificada en esta etapa. Todo el desarrollo experimental y de flasheo reside en `02_Debug_y_Pruebas/`.
2. **Plataforma Predeterminada:** La combinacion predeterminada y mas optimizada del sistema es:
   * Transmisor: Arduino Nano ESP32.
   * Receptor: Arduino Nano ESP32.
3. **Cero Emojis:** Queda terminantemente prohibido el uso de emojis en cualquier archivo, comentario, commit o respuesta. Estilo tecnico, sobrio y directo.
4. **Empaquetado Binario Fijo (6 Bytes):** El protocolo de enlace por radiofrecuencia (canal 108, 250 kbps, `RF24_PA_MAX`) mantiene la estructura binaria estricta de 6 bytes con `__attribute__((packed))` en C++ y `#[repr(C, packed)]` en Rust.

---

## 3. Matriz de Perfiles de Hardware y Autodeteccion

### 3.1. Definicion de Perfiles Registrados

| Identificador de Perfil | Microcontrolador | Arquitectura | VID:PID USB | FQBN Arduino-CLI | Rol TX Soportado | Rol RX Soportado |
|---|---|---|---|---|---|---|
| `ARDUINO_NANO_ESP32` | ESP32-S3 | Xtensa LX7 Dual-Core 240 MHz | `2341:0070` (Normal) / `2341:0069` (Bootloader) | `arduino:esp32:nano_nora` | `Transmisor_ArduinoNano_ESP32.ino` | `Ejecutor_ArduinoNano_ESP32.ino` |
| `ESP32_C3_SUPERMINI` | ESP32-C3 | RISC-V Single-Core 160 MHz | `303A:1001` (CDC) / `1A86:7523` (CH340) | `esp32:esp32:esp32c3` | `Control_ESP32_C3_Optimizado.ino` | No recomendado |
| `ARDUINO_MKR_1310` | SAMD21 | ARM Cortex-M0+ 48 MHz | `2341:8054` / `2341:0054` | `arduino:samd:mkrwan1310` | No soportado | `Ejecutor_ArduinoMKR_Optimizado.ino` |

### 3.2. Mecanismo de Identificacion Dual

1. **Deteccion Pasiva:** El HMI escanea puertos serie mediante `serial.tools.list_ports.comports()`. Se evalua la combinacion de `vid`, `pid`, `manufacturer` y `description`. Si coincide con la tabla, el combobox de la UI preselecciona automaticamente el perfil y muestra la insignia de placa identificada.
2. **Deteccion Activa (Handshake):** Al abrir el puerto COM a 115200 bps:
   * El HMI envia la trama de texto: `IDENT\n`.
   * El firmware responde en formato estructurado: `ID:<PLACA>:<ROL>:<VERSION>\n`.
     * Ejemplo TX Nano: `ID:NANO_ESP32:TX:v2.1`
     * Ejemplo RX Nano: `ID:NANO_ESP32:RX:v2.1`
     * Ejemplo RX MKR: `ID:MKR1310:RX:v2.0`
     * Ejemplo TX C3: `ID:ESP32C3:TX:v2.0`
   * Si el microcontrolador no responde a `IDENT\n` (firmware viejo o generico), el HMI recurre a la deteccion pasiva por hardware VID:PID.

---

## 4. Firmware Transmisor Oficial: `Transmisor_ArduinoNano_ESP32.ino`

### 4.1. Ubicacion del Archivo
`02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino`

### 4.2. Conexionado Fisico de la Radio (Simetrico al Receptor)
* **VCC:** 3.3V (con capacitor electrolitico 10-100 uF a GND).
* **GND:** Tierra comun.
* **CE:** Pin D9 (GPIO 18).
* **CSN:** Pin D10 (GPIO 21).
* **MOSI:** Pin D11 (GPIO 38).
* **MISO:** Pin D12 (GPIO 47).
* **SCK:** Pin D13 (GPIO 48).

### 4.3. Lógica y Caracteristicas Clave
* Comunicacion USB CDC nativa a 115200 bps sin retardos bloqueantes.
* Parseo de comandos de texto:
  * `CMD,izq,der,s1,s2\n`: Transmite el paquete binario de 6 bytes por RF24 al canal 108.
  * `IDENT\n`: Responde `ID:NANO_ESP32:TX:v2.1\n`.
  * `PING\n`: Responde `PONG:TX:NANO_ESP32\n`.
* Telemetria visual mediante LED RGB integrado del Nano ESP32:
  * Azul solido: Transmisor en espera de enlace USB.
  * Pulso verde (30 ms): Paquete RF transmitido exitosamente.
  * Pulso rojo (50 ms): Falla de transmision o saturacion de FIFO de radio.

---

## 5. Motor de Flasheo en 1 Clic y Banco de Pruebas

### 5.1. Flasheo Integrado
En la barra superior de `HMI_Rover_Debug.py` se implementa un panel de aprovisionamiento:
* **Selector de Rol:** Boton o toggle para definir el destino del firmware (`TX` o `RX`).
* **Boton "Subir Firmware (1 Clic)":** Ejecuta un subproceso en segundo plano sin congelar la GUI:
  1. Si `arduino-cli` se encuentra en el PATH o en la carpeta de herramientas, ejecuta:  
     `arduino-cli compile --upload -b <FQBN> -p <PUERTO_COM> <RUTA_SKETCH>`
  2. Si `arduino-cli` no esta instalado, ejecuta el modulo estandar `esptool` de Python:  
     `sys.executable -m esptool --chip esp32s3 --port <PUERTO_COM> write_flash 0x0 <BIN_PRECOMPILADO>`
  3. Los mensajes de salida se redirigen en vivo a la consola del HMI con coloracion diferenciada.

### 5.2. Procedimiento de Banco de Pruebas Pre-Despliegue
1. **Conexion Dual:** Se conectan simultaneamente por USB el Transmisor y el Receptor a la PC.
2. **Validacion Cruzada:** Los controles del HMI operan el TX; la radio transmite; el RX en el rover recibe la senal y la retransmite a la PC por su propio cable USB. La UI compara campo por campo y enciende la insignia de enlace validado 1:1.
3. **Sincronizacion de Calibracion:** El operador pulsa `Sincronizar Calibracion al Receptor`. El HMI envia los valores de trim de motores (M1-M6) y centros de servos para guardarse en la memoria NVS del Nano ESP32.
4. **Liberacion para Campo:** El operador presiona `Liberar Receptor para Campo`. El HMI cierra el puerto serie del receptor. Se desconecta el USB del chasis y se enciende la alimentacion por bateria para iniciar el pilotaje libre.

---

## 6. Arquitectura del Proyecto Paralelo en Rust (`HMI-Lunar-Rover-Rust`)

### 6.1. Ubicacion del Workspace
`C:\Users\joaqu\Desktop\HMI-Lunar-Rover-Rust`

### 6.2. Distribucion de Crates
```text
HMI-Lunar-Rover-Rust/
├── Cargo.toml                          # Workspace root
├── crates/
│   ├── protocol-rover/                 # Crate no_std/std con struct Paquete #[repr(C, packed)]
│   ├── hmi-gui/                        # Aplicacion de escritorio nativa (eframe / egui + serialport)
│   ├── firmware-tx-esp32/              # Firmware bare-metal no_std para ESP32-S3 (esp-hal)
│   └── firmware-rx-esp32/              # Firmware bare-metal no_std para ESP32-S3 (esp-hal)
├── README.md                           # Guia de compilacion con cargo y toolchain
└── .gitignore
```

### 6.3. Especificacion de `protocol-rover`
```rust
#![no_std]

#[repr(C, packed)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PaqueteRover {
    pub traccion_izq: i16, // -255 a 255
    pub traccion_der: i16, // -255 a 255
    pub angulo_s1: u8,     // 10 a 170
    pub angulo_s2: u8,     // 10 a 170
}

impl PaqueteRover {
    pub const TAMANIO: usize = 6;
    
    pub fn a_bytes(&self) -> [u8; Self::TAMANIO] {
        unsafe { core::mem::transmute_copy(self) }
    }
    
    pub fn desde_bytes(bytes: &[u8; Self::TAMANIO]) -> Self {
        unsafe { core::mem::transmute_copy(bytes) }
    }
}
```

---

## 7. Hoja de Ruta: Percepcion 3D y LiDAR en Cuevas

Para futuras etapas de investigacion en exploracion subterránea (tubos de lava lunar y mineria):

1. **Beneficios de Rust en Percepcion 3D:**
   * Procesamiento multihilo sin GIL con `rayon` para nubes de puntos densas.
   * Renderizado 3D acelerado por hardware a 60 FPS fijos utilizando `wgpu` o integracion con `Rerun.io` (herramienta lider de telemetria robotica en Rust).
2. **Matriz de Hardware y Costos Estimados:**
   * **Nivel 1 (Micro-LiDAR ToF con Pan-Tilt):** Sensor Benewake TF-Luna ($25 USD) + mecanismo Pan-Tilt ($15 USD) + ESP32-CAM ($15 USD). Costo total: ~$55 USD. Mapeo esferico de puntos sparse compatible directamente con microcontrolador.
   * **Nivel 2 (LiDAR 2D 360° Laser):** Slamtec RPLiDAR A1M8 ($99 USD). Escaneo planar a 10 Hz por UART.
   * **Nivel 3 (Camara Estereo 3D ToF):** Luxonis OAK-D Lite ($149 USD) o Intel RealSense ($300 USD). Requiere SBC a bordo (Raspberry Pi 4/5) con enlace Wi-Fi.
