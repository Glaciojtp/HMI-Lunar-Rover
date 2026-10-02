# Workspace Paralelo en Rust: Rover Lunar V2.0

Este repositorio alberga la implementacion integral y paralela en lenguaje Rust para el sistema de control, telemetria y operacion del vehiculo de exploracion robotica Rover Lunar V2.0 con suspension tipo Rocker-Bogie.

## 1. Arquitectura del Workspace

El proyecto esta estructurado como un Cargo Workspace multi-crate modular:

```text
HMI-Lunar-Rover-Rust/
├── Cargo.toml                      # Manifiesto raiz del workspace
├── .gitignore                      # Exclusiones de compilacion
├── README.md                       # Documentacion tecnica del stack
└── crates/
    ├── protocol-rover/             # Crate central no_std de serializacion binaria
    │   ├── Cargo.toml
    │   ├── src/lib.rs
    │   └── tests/test_protocol.rs
    ├── hmi-gui/                    # Estacion terrena de escritorio (egui / eframe)
    │   ├── Cargo.toml
    │   └── src/main.rs
    ├── firmware-tx-esp32/          # Firmware de transmision RF USB-CDC para ESP32
    │   ├── Cargo.toml
    │   └── src/main.rs
    └── firmware-rx-esp32/          # Firmware receptor y control de actuadores para ESP32
        ├── Cargo.toml
        └── src/main.rs
```

---

## 2. Crate `protocol-rover` (no_std)

El crate `protocol-rover` es el nucleo del protocolo de comunicacion entre la estacion terrena (HMI) y los microcontroladores embebidos a bordo del rover.

### Caracteristicas Principales
- **Compatibilidad Embebida (`#![no_std]`):** No requiere asignacion dinamica en heap (`alloc`) ni libreria estandar (`std`), permitiendo su ejecucion directa en sistemas bare-metal.
- **Empaquetado Estricto de 6 Bytes (`#[repr(C, packed)]`):** Tamano verificado en tiempo de compilacion mediante aserciones estaticas (`size_of::<PaqueteRover>() == 6` y `align_of::<PaqueteRover>() == 1`).
- **Consistencia de Endianness:** La serializacion y deserializacion fuerzan orden Little-Endian (`i16::to_le_bytes` e `i16::from_le_bytes`), garantizando interoperabilidad exacta con los microcontroladores SAMD21 (ARM Cortex-M0+), ESP32-C3 (RISC-V) y ESP32-S3 (Xtensa/RISC-V).
- **Seguridad Mecanica Integrada:** Metodo `clamped()` para forzar los rangos seguros de operacion antes de la emision.
- **Prevencion de Referencias Desalineadas (E0793):** Proporciona metodos accesores inline por valor (`traccion_izq()`, `traccion_der()`, `angulo_s1()`, `angulo_s2()`) para evitar comportamiento indefinido al interactuar con campos empaquetados de 16 bits.

### Especificacion de la Trama Binaria

| Offset (Bytes) | Campo | Tipo | Rango Permitido | Descripcion |
|---|---|---|---|---|
| `0..2` | `traccion_izq` | `i16` (LE) | `-255` a `+255` | Potencia PWM lado izquierdo (negativo reversa, positivo avance) |
| `2..4` | `traccion_der` | `i16` (LE) | `-255` a `+255` | Potencia PWM lado derecho (control independiente de trim) |
| `4` | `angulo_s1` | `u8` | `10` a `170` | Angulo servomotor delantero izquierdo (grados) |
| `5` | `angulo_s2` | `u8` | `10` a `170` | Angulo servomotor delantero derecho (grados) |

Constantes de operacion:
- `TAMANO_PAQUETE = 6`
- `ANGULO_MIN = 10`
- `ANGULO_MAX = 170`
- `ANGULO_CENTRO = 90`
- `TRACCION_MIN = -255`
- `TRACCION_MAX = 255`

---

## 3. Crates de Aplicacion y Firmware

### `hmi-gui`
Aplicacion de escritorio nativa multiplataforma (Windows y Linux) basada en `egui` y `eframe`. Provee control en tiempo real mediante teclado (WASD, QE, Space) o joysticks, sliders de trims de traccion, centrado de direccion y telemetria bidireccional por puerto serie.

### `firmware-tx-esp32`
Firmware en Rust embebido para Arduino Nano ESP32 o ESP32-C3 configurado como puente USB-CDC a radiofrecuencia NRF24L01 mediante el bus SPI por hardware en canal 108 a 250 kbps.

### `firmware-rx-esp32`
Firmware en Rust embebido para Arduino Nano ESP32 montado en el chasis del rover. Recibe los paquetes por SPI desde la radio NRF24L01, modula las senales PWM hacia el puente H L9110S para los motores DC de traccion y genera senales PWM hacia los servomotores de direccion. Implementa un lazo no bloqueante con parada automatica por timeout de enlace a los 1000 ms.

---

## 4. Requisitos y Guia de Compilacion

### Herramientas Requeridas
- Rust Toolchain 1.75 o superior (`rustc`, `cargo`).
- Para desarrollo embebido ESP32 (crates `firmware-tx-esp32` y `firmware-rx-esp32`):
  - `espflash` o `cargo-espflash` (`cargo install cargo-espflash`).
  - Target adecuado para el microcontrolador (`rustup target add riscv32imc-unknown-none-elf` para ESP32-C3 o toolchain de Espressif para ESP32-S3).

### Comandos de Verificacion

Ejecutar las pruebas unitarias y de integracion de todo el workspace:
```bash
cargo test --workspace
```

Verificar la compilacion estatica de todos los crates:
```bash
cargo check --workspace
```

Ejecutar pruebas especificas del protocolo de comunicacion:
```bash
cargo test -p protocol-rover
```
