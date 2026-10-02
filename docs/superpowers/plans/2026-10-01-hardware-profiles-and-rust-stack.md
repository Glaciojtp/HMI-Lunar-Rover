# Plan de Implementacion: Perfiles de Hardware, Transmisor Nano ESP32 y Stack Paralelo en Rust

> **Para agentes ejecutores:** SUB-SKILL REQUERIDO: Usar `superpowers:subagent-driven-development` (recomendado) o `superpowers:executing-plans` para implementar este plan tarea por tarea. Los pasos usan la sintaxis de casillas de verificacion (`- [ ]`) para su seguimiento.

**Meta:** Implementar la matriz de perfiles de hardware con autodeteccion, firmware de transmision para Arduino Nano ESP32, flasheo en 1 clic y calibracion pre-despliegue en la suite Debug, junto con la creacion del workspace paralelo completo en Rust (`HMI-Lunar-Rover-Rust`).

**Arquitectura:** Se aisla la logica de perfiles y flasheo en modulos Python independientes (`hardware_profiles.py` y `flasher_engine.py`) dentro de `02_Debug_y_Pruebas/HMI_Debug/` para preservar intacta la aplicacion de produccion. El firmware de transmision se escribe en C++ para Nano ESP32 con mapeo simetrico de pines SPI. En paralelo, se crea el workspace de Rust con `protocol-rover` (`no_std`), aplicacion de escritorio `hmi-gui` en `egui`/`eframe` y firmwares `esp-hal`.

**Tech Stack:** Python 3 (Tkinter, pyserial, pytest), C++ (Arduino ESP32 core, RF24), Rust 2021 (eframe/egui, serialport, tokio, esp-hal).

**Spec:** `docs/superpowers/specs/2026-10-01-hardware-profiles-and-rust-stack-design.md`

## Restricciones Globales
- Prohibicion absoluta de emojis en codigo, mensajes, nombres y documentacion.
- La aplicacion de produccion `01_Oficial/HMI/HMI_Rover_V2.py` no debe ser modificada bajo ninguna circunstancia.
- La configuracion predeterminada oficial del sistema es: Transmisor Nano ESP32 y Receptor Nano ESP32.
- El empaquetado binario del protocolo de radio se fija en exactamente 6 bytes (`Paquete` con traccion_izq: i16, traccion_der: i16, s1: u8, s2: u8).

---

### Task 1: Firmware Transmisor Oficial para Arduino Nano ESP32

**Archivos:**
- Crear: `02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino`
- Referencia: `01_Oficial/Receptor_Rover_NanoESP32/Ejecutor_ArduinoNano_ESP32/Ejecutor_ArduinoNano_ESP32.ino`
- Referencia: `01_Oficial/Transmisor_PC_ESP32C3/Control_ESP32_C3_Optimizado/Control_ESP32_C3_Optimizado.ino`

**Interfaces:**
- Produce: Firmware transmisor USB-CDC a RF24 sobre ESP32-S3 a 115200 bps.
- Protocolo serie: `CMD,izq,der,s1,s2\n`, `IDENT\n` (responde `ID:NANO_ESP32:TX:v2.1\n`), `PING\n` (responde `PONG:TX:NANO_ESP32\n`).
- Pines SPI: D13 (SCK/GPIO48), D12 (MISO/GPIO47), D11 (MOSI/GPIO38), D9 (CE/GPIO18), D10 (CSN/GPIO21).
- LED RGB: Pines integrados `LED_RED`, `LED_GREEN`, `LED_BLUE`.

- [ ] **Paso 1: Escribir el sketch `Transmisor_ArduinoNano_ESP32.ino`**
  Implementar la estructura binaria empaquetada `Paquete`, la inicializacion de radio NRF24L01 con SPI de hardware en canal 108 a 250 kbps `RF24_PA_MAX`, el bucle no bloqueante con `millis()`, el control del LED RGB de estado y el parseo de comandos `IDENT`, `PING` y `CMD`.

- [ ] **Paso 2: Validacion sintactica del sketch**
  Verificar la estructura del codigo mediante chequeo estatico en Python comprobando que no existan llamadas a `delay()`, que los tipos enteros coincidan y que los pines coincidan con el esquematico oficial.

- [ ] **Paso 3: Commit de la Tarea 1**
  ```bash
  git add 02_Debug_y_Pruebas/Firmware_Debug/Transmisor_ArduinoNano_ESP32/Transmisor_ArduinoNano_ESP32.ino
  git commit -m "feat(firmware): crear firmware transmisor oficial para Arduino Nano ESP32 con handshake y led rgb"
  ```

---

### Task 2: Modulo de Perfiles de Hardware y Autodeteccion (`hardware_profiles.py`)

**Archivos:**
- Crear: `02_Debug_y_Pruebas/HMI_Debug/hardware_profiles.py`
- Crear: `02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py`

**Interfaces:**
- Produce: Clase `HardwareProfileRegistry` con metodos:
  - `detectar_perfil(port_info) -> PerfilHardware`
  - `parsear_handshake(respuesta_ident) -> tuple[str, str, str]`
  - `obtener_perfil(nombre_perfil) -> PerfilHardware`
  - `listar_perfiles() -> list[PerfilHardware]`

- [ ] **Paso 1: Escribir pruebas unitarias iniciales en `test_hardware_profiles.py`**
  Probar deteccion pasiva por VID:PID para Arduino Nano ESP32 (`0x2341:0x0070`), ESP32-C3 (`0x303A:0x1001`), MKR 1310 (`0x2341:0x8054`), y parseo de cadenas `ID:NANO_ESP32:TX:v2.1`.

- [ ] **Paso 2: Ejecutar pruebas y verificar fallo**
  ```bash
  pytest 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py -v
  ```
  Esperado: FAIL por modulo no encontrado.

- [ ] **Paso 3: Implementar `hardware_profiles.py`**
  Definir dataclasses `PerfilHardware` con campos `id`, `nombre`, `mcu`, `vid_pid_list`, `fqbn`, `sketch_tx`, `sketch_rx` y la logica de resolucion pasiva y activa.

- [ ] **Paso 4: Ejecutar pruebas y verificar exito**
  ```bash
  pytest 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py -v
  ```
  Esperado: PASS (100% de pruebas superadas).

- [ ] **Paso 5: Commit de la Tarea 2**
  ```bash
  git add 02_Debug_y_Pruebas/HMI_Debug/hardware_profiles.py 02_Debug_y_Pruebas/HMI_Debug/test_hardware_profiles.py
  git commit -m "feat(debug): implementar registro y autodeteccion de perfiles de hardware por VID:PID y handshake"
  ```

---

### Task 3: Motor de Flasheo en 1 Clic y Utilidad de Aprovisionamiento (`flasher_engine.py`)

**Archivos:**
- Crear: `02_Debug_y_Pruebas/HMI_Debug/flasher_engine.py`
- Crear: `02_Debug_y_Pruebas/HMI_Debug/test_flasher_engine.py`

**Interfaces:**
- Produce: Clase `FlasherEngine` con metodos:
  - `verificar_herramientas() -> dict[str, bool]` (`arduino_cli`, `esptool`)
  - `flashear(puerto, perfil, rol, callback_log) -> bool`
  - `sincronizar_calibracion(serial_conn, trims, servos) -> bool`

- [ ] **Paso 1: Escribir pruebas unitarias en `test_flasher_engine.py`**
  Probar construccion de comandos de flasheo (`arduino-cli compile --upload` y `esptool write_flash`), sanitizacion de parametros de puerto y formato de tramas de sincronizacion de calibracion.

- [ ] **Paso 2: Ejecutar pruebas y verificar fallo**
  ```bash
  pytest 02_Debug_y_Pruebas/HMI_Debug/test_flasher_engine.py -v
  ```
  Esperado: FAIL por falta del modulo `flasher_engine.py`.

- [ ] **Paso 3: Implementar `flasher_engine.py`**
  Implementar la ejecucion de subprocesos con captura de stdout en streaming, soporte para `arduino-cli`, fallback a `esptool.py` mediante el ejecutable de Python, y rutina de persistencia NVS/EEPROM.

- [ ] **Paso 4: Ejecutar pruebas y verificar exito**
  ```bash
  pytest 02_Debug_y_Pruebas/HMI_Debug/test_flasher_engine.py -v
  ```
  Esperado: PASS.

- [ ] **Paso 5: Commit de la Tarea 3**
  ```bash
  git add 02_Debug_y_Pruebas/HMI_Debug/flasher_engine.py 02_Debug_y_Pruebas/HMI_Debug/test_flasher_engine.py
  git commit -m "feat(debug): implementar motor de flasheo en 1 clic y sincronizacion de calibracion pre-despliegue"
  ```

---

### Task 4: Integracion en la Interfaz Grafica `HMI_Rover_Debug.py`

**Archivos:**
- Modificar: `02_Debug_y_Pruebas/HMI_Debug/HMI_Rover_Debug.py`

**Interfaces:**
- Consume: `HardwareProfileRegistry` desde `hardware_profiles.py` y `FlasherEngine` desde `flasher_engine.py`.
- Produce:
  - UI de seleccion de perfiles para TX y RX con deteccion automatica.
  - Boton "Subir Firmware" para flasheo en 1 clic por puerto.
  - Boton "Sincronizar Calibracion al Receptor".
  - Boton "Liberar Receptor para Campo".
  - Consola con salida coloreada del flasher.
  - Eliminacion de emojis residuales en la UI (`🛰️`, `🤖`, `⚡`, `🔄`, etc.).

- [ ] **Paso 1: Integrar `hardware_profiles` y `flasher_engine` en `HMI_Rover_Debug.py`**
  Modificar la barra superior de conexion, agregar selectores de perfil de hardware, boton de subida en 1 clic e insignias de estado.

- [ ] **Paso 2: Implementar metodos de callbacks en `HMIRoverDebug`**
  Agregar `iniciar_flasheo()`, `sincronizar_calibracion_rx()`, `liberar_rx_para_despliegue()`, `identificar_puerto_activo()`.

- [ ] **Paso 3: Limpiar todos los emojis residuales de la interfaz**
  Reemplazar simbolos ornamentales por texto formal limpio en botones, titulos de ventanas y canvas 2D.

- [ ] **Paso 4: Prueba de arranque y estabilidad**
  Ejecutar el script en modo headless / diagnostico para verificar que importe sin errores de sintaxis y que inicialice los perfiles.

- [ ] **Paso 5: Commit de la Tarea 4**
  ```bash
  git add 02_Debug_y_Pruebas/HMI_Debug/HMI_Rover_Debug.py
  git commit -m "feat(hmi-debug): integrar matriz de perfiles, flasheo en 1 clic y calibracion pre-despliegue"
  ```

---

### Task 5: Estructuracion del Workspace Paralelo en Rust y Crate `protocol-rover`

**Archivos:**
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/Cargo.toml`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/.gitignore`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/README.md`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/protocol-rover/Cargo.toml`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/protocol-rover/src/lib.rs`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/protocol-rover/tests/test_protocol.rs`

**Interfaces:**
- Produce: Crate `protocol-rover` compatible con `no_std`, con `PaqueteRover` de 6 bytes, metodos de serializacion/deserializacion y pruebas unitarias con `cargo test`.

- [ ] **Paso 1: Inicializar el directorio y manifiesto raíz de Cargo**
  Definir `[workspace]` con los miembros `crates/protocol-rover`, `crates/hmi-gui`, `crates/firmware-tx-esp32`, `crates/firmware-rx-esp32`.

- [ ] **Paso 2: Escribir el crate `protocol-rover` y sus pruebas**
  Implementar `PaqueteRover` empaquetado a 6 bytes con conversiones a bytes y desde bytes, asegurando que `core::mem::size_of::<PaqueteRover>() == 6`.

- [ ] **Paso 3: Ejecutar pruebas unitarias con Cargo**
  ```bash
  cd /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/protocol-rover && cargo test
  ```
  Esperado: PASS (pruebas de tamano y consistencia binaria superadas).

- [ ] **Paso 4: Documentar el workspace en `README.md`**
  Redactar guia de requisitos de Rust y toolchain sin emojis.

---

### Task 6: Aplicacion de Escritorio Nativa en Rust (`hmi-gui`)

**Archivos:**
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui/Cargo.toml`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui/src/main.rs`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui/src/app.rs`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui/src/serial_worker.rs`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui/src/profiles.rs`

**Interfaces:**
- Consume: `protocol-rover`
- Produce: Binario nativo de escritorio para pilotaje del Rover en Rust con `eframe` (egui) y `serialport`.
- Funcionalidades:
  - Sliders de trims independientes para los 6 motores.
  - Sliders y centrado para los 4 servomotores.
  - Selector de puertos COM para Transmisor y Receptor.
  - Hilo asincrono de lectura/escritura serial.
  - Renderizado 2D esquematico del chasis Rocker-Bogie.

- [ ] **Paso 1: Definir dependencias en `crates/hmi-gui/Cargo.toml`**
  Agregar `eframe`, `egui`, `serialport`, `protocol-rover = { path = "../protocol-rover" }`.

- [ ] **Paso 2: Implementar `serial_worker.rs` y `profiles.rs`**
  Manejo no bloqueante de puertos serie con canales mpsc para intercambio de paquetes y escaneo de puertos.

- [ ] **Paso 3: Implementar `app.rs` y `main.rs`**
  Layout de la interfaz grafica, controles de direccion, sliders de trims, captura de teclado (WASD, QE, Space) y visor 2D.

- [ ] **Paso 4: Compilar y verificar aplicacion en Rust**
  ```bash
  cd /mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/hmi-gui && cargo check
  ```
  Esperado: Compilacion limpia con cero advertencias criticas.

---

### Task 7: Firmwares Embebidos en Rust (`esp-hal`)

**Archivos:**
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/firmware-tx-esp32/Cargo.toml`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/firmware-tx-esp32/src/main.rs`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/firmware-rx-esp32/Cargo.toml`
- Crear: `/mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust/crates/firmware-rx-esp32/src/main.rs`

**Interfaces:**
- Consume: `protocol-rover`
- Produce: Firmwares `no_std` en Rust para ESP32-S3 (Arduino Nano ESP32).
  - `firmware-tx-esp32`: Lee tramas desde el puerto serie USB CDC y las transmite por SPI al modulo NRF24L01+.
  - `firmware-rx-esp32`: Recibe tramas por SPI desde el NRF24L01+, genera senales PWM para los 6 motores DC y PWM para los 4 servos de direccion, con timeout failsafe de 1000 ms.

- [ ] **Paso 1: Implementar `firmware-tx-esp32`**
  Configurar perifericos SPI en GPIO 48, 47, 38, 18, 21 y recepcion USB CDC con `esp-hal`.

- [ ] **Paso 2: Implementar `firmware-rx-esp32`**
  Configurar perifericos MCPWM / LEDC para los 6 motores y 4 servos, recepcion de paquetes y parada de seguridad por timeout.

- [ ] **Paso 3: Documentar instrucciones de flasheo con `cargo espflash`**
  Detallar en el README del workspace como flashear directamente desde la linea de comandos.

---

### Task 8: Verificacion Integral, Guia de Usuario y Sincronizacion

**Archivos:**
- Actualizar: `02_Debug_y_Pruebas/Lanzar_HMI_Debug.bat`
- Actualizar: `03_Documentacion_y_Guias/Guias/GUIA_RAPIDA_EQUIPO.md`
- Actualizar: `README.md`
- Actualizar: `AGENTS.md`

- [ ] **Paso 1: Actualizar documentacion tecnica con la nueva arquitectura**
  Documentar la presencia del firmware Nano ESP32 para transmision, el sistema de flasheo y el enlace al workspace paralelo de Rust.

- [ ] **Paso 2: Ejecutar suite de pruebas completa en Python y Rust**
  Verificar que pasen todos los tests unitarios (`pytest` y `cargo test`).

- [ ] **Paso 3: Commit final y resumen de entrega**
  ```bash
  git add 02_Debug_y_Pruebas/ 03_Documentacion_y_Guias/ README.md AGENTS.md
  git commit -m "feat: completar suite de perfiles de hardware, transmisor Nano ESP32 y stack en Rust"
  ```
