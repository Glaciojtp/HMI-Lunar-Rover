# MANUAL TECNICO DE ESTADO ACTUAL Y FUNCIONAMIENTO DEL SISTEMA
## Proyecto: Rover Lunar V2.0 — Plataforma de Exploracion Movil Rocker-Bogie 6x6 + 4WS

> **DOCUMENTO TECNICO DE OPERACION, ARQUITECTURA Y ESTADO DEL ARTE**  
> Este manual consolida el estado de conservacion tecnico completo, la arquitectura de conexionado de pines, el protocolo de enlace inalambrico de radiofrecuencia, el stack de software dual (Python y Rust) y la guia de puesta en marcha del proyecto **Rover Lunar V2.0**.

---

## 1. Topologia General del Sistema

El sistema opera mediante una arquitectura de tres nodos jerarquicos interconectados:

```
[ ESTACION TERRENA (PC) ]
  ├── Stack Python (HMI_Rover_V2.py / HMI_Rover_Debug.py / simulador_cinematico_rover.py)
  └── Stack Rust Nativo (hmi-gui en egui/eframe con Simulador Plano 2D)
           │
           │  (USB Serial CDC a 115200 bps — Handshake IDENT / Tramas Binarias)
           ▼
[ NODO TRANSMISOR (TX) ]
  Arduino Nano ESP32 (ESP32-S3 a 3.3V) + Transmisor RF NRF24L01+
           │
           │  (Radiofrecuencia 2.508 GHz / Canal 108 a 250 kbps — Paquetes de 6 Bytes)
           ▼
[ NODO RECEPTOR A BORDO (RX) ]
  Arduino Nano ESP32 (ESP32-S3 a 3.3V) + Receptor RF NRF24L01+
  ├── Puente H L9110S (Control bidireccional PWM de 6 motores DC)
  ├── 4 Servomotores de Direccion (S1..S4 para arquitectura 4WS)
  └── Chasis Mecanico Rocker-Bogie 6x6 con Barra Diferencial
```

---

## 2. Arquitectura de Hardware y Conexionado de Pines (Pinout Oficial)

### 2.1. Reglas Criticas de Hardware y Seguridad (Lecciones Aprendidas)

> [!CAUTION]
> **1. ALIMENTACION DEL NRF24L01: NUNCA CONECTAR A 5V**  
> El modulo NRF24L01 tolera 5V en sus pines logicos SPI, pero **su linea VCC debe ser estrictamente alimentada con 3.3V**. Conectar VCC a 5V destruye la radio de inmediato.

> [!IMPORTANT]
> **2. CAPACITOR OBLIGATORIO EN LA RADIO**  
> Es imprescindible soldar un capacitor electrolitico de entre **10 µF y 100 µF** directamente entre los pines **VCC** y **GND** de cada modulo NRF24L01. Sin este capacitor, los transitorios de consumo durante la transmision provocan caidas de tension y perdida masiva de tramas.

> [!WARNING]
> **3. REGULACION PARA SERVOMOTORES (PROHIBIDO LM7805)**  
> Se debe utilizar exclusivamente un regulador conmutado **Step-Down (Buck)** ajustado a **5V - 6V** para alimentar los servomotores de direccion de forma aislada, compartiendo la linea de tierra (GND comun) con el microcontrolador. Los reguladores lineales tipo 7805 se sobrecalientan bajo carga y queman actuadores.

> [!IMPORTANT]
> **4. LIMITES DE ANGULO POR SOFTWARE (10° A 170°)**  
> Para servos analogicos estandar, ningun comando de software puede solicitar angulos fuera de `[10°, 170°]` para prevenir atascos mecanicos y rotura de dientes de engranajes por esfuerzo de corte. Si se activa el modo de servos continuos de 360 grados, el rango se expande a `[0°, 360°]`.

---

### 2.2. Transmisor Oficial: Arduino Nano ESP32 (Dongle USB-RF)
Conectado por puerto USB a la estacion terrena, recibe consignas serie a 115200 bps y transmite por radio NRF24L01:

| Componente Fisico | Pin del Modulo | Pin Arduino Nano ESP32 | GPIO Interno | Funcion / Observacion |
|---|---|---|---|---|
| **NRF24L01** | VCC | **3.3V** | — | Alimentacion logica regulada con capacitor |
| **NRF24L01** | GND | **GND** | — | Tierra comun del sistema |
| **NRF24L01** | CE | **Pin D9** | GPIO 18 | Habilitacion de radio (Chip Enable) |
| **NRF24L01** | CSN | **Pin D10** | GPIO 21 | Chip Select SPI |
| **NRF24L01** | MOSI | **Pin D11** | GPIO 38 | Bus SPI Hardware (Master Out) |
| **NRF24L01** | MISO | **Pin D12** | GPIO 47 | Bus SPI Hardware (Master In) |
| **NRF24L01** | SCK | **Pin D13** | GPIO 48 | Reloj SPI Hardware |
| **LED RGB Integrado** | Rojo | **LED_RED** | GPIO 46 | Indicador de error / parada (Activo en bajo) |
| **LED RGB Integrado** | Verde | **LED_GREEN** | GPIO 0 | Transmision RF exitosa (Activo en bajo) |
| **LED RGB Integrado** | Azul | **LED_BLUE** | GPIO 45 | Enlace serie USB activo (Activo en bajo) |

---

### 2.3. Receptor Oficial a Bordo: Arduino Nano ESP32 (Chasis 6x6 + 4WS)
Montado en el rover, recibe las tramas por radio y comanda los actuadores:

| Componente Fisico | Pin del Modulo | Pin Arduino Nano ESP32 | GPIO Interno | Funcion / Observacion |
|---|---|---|---|---|
| **NRF24L01** | VCC | **3.3V** | — | Salida 3.3V regulada (con capacitor 10-100 µF) |
| **NRF24L01** | GND | **GND** | — | Tierra comun |
| **NRF24L01** | CE | **Pin D9** | GPIO 18 | Habilitacion de radio |
| **NRF24L01** | CSN | **Pin D10** | GPIO 21 | Chip Select SPI |
| **NRF24L01** | MOSI | **Pin D11** | GPIO 38 | Bus SPI Hardware |
| **NRF24L01** | MISO | **Pin D12** | GPIO 47 | Bus SPI Hardware |
| **NRF24L01** | SCK | **Pin D13** | GPIO 48 | Bus SPI Hardware |
| **Puente H L9110S** | A1A | **Pin D2** | GPIO 5 | Traccion Izquierda - Avance (PWM) |
| **Puente H L9110S** | A1B | **Pin D5** | GPIO 8 | Traccion Izquierda - Reversa (PWM) |
| **Puente H L9110S** | B1A | **Pin D3** | GPIO 6 | Traccion Derecha - Avance (PWM) |
| **Puente H L9110S** | B1B | **Pin D4** | GPIO 7 | Traccion Derecha - Reversa (PWM) |
| **Servomotor S1** | Señal | **Pin D6** | GPIO 9 | Direccion Rueda Delantera Izquierda (FL) |
| **Servomotor S2** | Señal | **Pin D7** | GPIO 10 | Direccion Rueda Delantera Derecha (FR) |
| **Servomotor S3** | Señal | **Pin D8** | GPIO 17 | Direccion Rueda Trasera Izquierda (RL) |
| **Servomotor S4** | Señal | **Pin A0** | GPIO 1 | Direccion Rueda Trasera Derecha (RR) |
| **Regulador Step-Down**| Salida 5V-6V | VCC Servos | — | Alimentacion aislada para S1..S4 (GND comun) |

---

## 3. Protocolo de Comunicacion y Enlace Inalambrico

### 3.1. Estructura Binaria de Datos Unificada (Trama de 6 Bytes)
Para garantizar compatibilidad binaria estricta entre arquitecturas heterogeneas sin desalineacion por relleno de memoria (*padding*), el paquete se empaqueta de forma rigida con `__attribute__((packed))` y representacion Little-Endian:

```cpp
struct __attribute__((packed)) Paquete {
  int16_t traccion_izq;  // -255 a 255 (negativo: reversa, positivo: avance)
  int16_t traccion_der;  // -255 a 255 (control independiente para calibracion)
  uint8_t angulo_s1;     // 10 a 170 grados (servomotor FL)
  uint8_t angulo_s2;     // 10 a 170 grados (servomotor FR)
};
```
* **Tamano exacto:** **6 bytes**.
* **Little-Endian:**
  * Bytes 0-1: `traccion_izq` (int16_t).
  * Bytes 2-3: `traccion_der` (int16_t).
  * Byte 4: `angulo_s1` (uint8_t).
  * Byte 5: `angulo_s2` (uint8_t).

### 3.2. Configuracion de Radiofrecuencia NRF24L01
* **Canal:** `108` (Frecuencia: **2.508 GHz**). Se selecciono por encima del espectro Wi-Fi estandar (canales 1 al 13) para evitar interferencias.
* **Potencia:** `RF24_PA_MAX` (+0 dBm).
* **Tasa de datos:** `RF24_250KBPS` (Baja tasa para maximizar penetracion, sensibilidad y alcance).
* **Direccion de enlace (Pipe):** `0xF0F0F0F0E1LL`.

### 3.3. Handshake Activo y Autodeteccion
1. **Autodeteccion Pasiva:** El software evalua los identificadores USB VID:PID en la apertura del puerto:
   * Arduino Nano ESP32: `0x2341:0x0070` (CDC) / `0x2341:0x0069` (DFU).
   * ESP32-C3 SuperMini: `0x303A:0x1001` (CDC).
   * Arduino MKR 1310: `0x2341:0x8054` (CDC).
2. **Handshake Activo:** La estacion terrena envia el comando `IDENT\n`. El microcontrolador responde con la cadena estandarizada:
   ```text
   ID:<PLACA>:<ROL>:<VERSION>
   Ejemplo: ID:NANO_ESP32:TX:v2.1
   ```
3. **Prueba de Conectividad (Ping):** El comando `PING\n` devuelve `PONG:TX:NANO_ESP32\n`.

### 3.4. Mecanismos de Robustez y Seguridad en Tiempo Real
1. **Failsafe de Emergencia por Timeout (1000 ms):** Si transcurren mas de `1000 ms` sin recibir una trama valida de radio en el rover, se ejecuta de inmediato `pararMotores()`, previniendo movimientos no controlados por caida de enlace.
2. **Drenaje de Bufer RF:** El lazo de recepcion vacia completamente la pila FIFO del NRF24L01 en cada ciclo procesando unicamente el paquete mas reciente y descartando tramas obsoletas acumuladas.
3. **Cero Retardos Bloqueantes:** Ningun codigo de control contiene `delay()`. Todas las maquinas de estados y secuencias temporales se gobiernan mediante contadores `millis()` en C++ y temporizadores asincronos en Rust.

---

## 4. Software de Estacion Terrena (Doble Stack)

El proyecto cuenta con dos implementaciones independientes de estacion terrena que coexisten y comparten el mismo protocolo binario:

### 4.1. Stack Python (Produccion y Laboratorio)
Ubicado en el repositorio principal [`HMI-Lunar-Rover`](file:///mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover):
* **`01_Oficial/HMI/HMI_Rover_V2.py`:** Interfaz gráfica oficial de pilotaje basada en Tkinter, con conexion serial directa, sliders de trimado independiente para nivelar la potencia de motores y visualizacion esquematica del chasis.
* **`02_Debug_y_Pruebas/HMI_Debug/HMI_Rover_Debug.py`:** Suite avanzada de laboratorio que integra:
  * Autodeteccion por VID:PID y resolucion de handshake `IDENT`.
  * Flasheador en 1 clic en segundo plano (`flasher_engine.py`) con soporte de `arduino-cli` y `esptool`.
  * Sincronizacion de calibracion pre-despliegue (`CALIB,m1..m6,s1..s4`) y persistencia en memoria no volatil NVS (`PERSIST_NVS`).
  * Boton de liberacion segura de puerto para puesta en marcha autonoma con bateria.
* **`02_Debug_y_Pruebas/HMI_Debug/simulador_cinematico_rover.py`:** Script analitico interactivo que ejecuta simulaciones numericas en plano horizontal ideal, calcula odometria, radios de curvatura ICR y genera mapas de trayectoria en arte ASCII por terminal.

### 4.2. Stack Rust Nativo (`HMI-Lunar-Rover-Rust`)
Ubicado en el workspace paralelo [`HMI-Lunar-Rover-Rust`](file:///mnt/c/Users/joaqu/Desktop/HMI-Lunar-Rover-Rust):
* **`crates/protocol-rover`:** Crate `#![no_std]` que define `PaqueteRover` con empaquetado binario exacto de 6 bytes verificado con asserts en tiempo de compilacion (`static_assertions`).
* **`crates/hmi-gui`:** Aplicacion de escritorio nativa compilada a codigo maquina directo en Rust con biblioteca `eframe`/`egui`:
  * **Hilo serial no bloqueante (`serial_worker.rs`):** Canales `mpsc` para recepcion y transmision sin congelar los FPS de pantalla.
  * **Simulador Plano 2D Integrado (`simulation.rs`):** Renderizado de arena con cuadricula metrica, origen (0,0), huella física del rover con ruedas rotadas, traza historica de trayectoria y HUD de telemetria en tiempo real ($X, Y, \text{Yaw}, v, \omega, R_{\text{ICR}}$).
  * **Tickbox de Servos 360 Grados:** Permite alternar dinamicamente el rango de los deslizadores entre `[10°, 170°]` (estandar) y `[0°, 360°]` (continuo), adaptando los presets (cangrejo a 180° lateral puro) y la inversion modular $(360 - \theta) \pmod{360}$.
  * **Esquema 2D de Chasis:** Dibujo interactivo del mecanismo Rocker-Bogie con vectores de direccion y flechas direccionales.

---

## 5. Guia de Operacion y Comandos de Teclado

### 5.1. Mapeo de Teclas de Pilotaje

| Tecla | Modo Conduccion | Consigna de Traccion | Angulo Servos Delanteros | Angulo Servos Traseros | Accion Resultante |
|---|---|---|---|---|---|
| **W** | Ackermann | Izq: +150, Der: +150 | $S_1 = 90^\circ, S_2 = 90^\circ$ | $S_3 = 90^\circ, S_4 = 90^\circ$ | Avance recto |
| **S** | Ackermann | Izq: -150, Der: -150 | $S_1 = 90^\circ, S_2 = 90^\circ$ | $S_3 = 90^\circ, S_4 = 90^\circ$ | Reversa recta |
| **W + A** | Ackermann | Izq: +105, Der: +150 | $S_1 = 120^\circ, S_2 = 120^\circ$| $S_3 = 60^\circ, S_4 = 60^\circ$ | Curva coordinada a izquierda |
| **W + D** | Ackermann | Izq: +150, Der: +105 | $S_1 = 60^\circ, S_2 = 60^\circ$  | $S_3 = 120^\circ, S_4 = 120^\circ$| Curva coordinada a derecha |
| **S + A** | Ackermann | Izq: -105, Der: -150 | $S_1 = 120^\circ, S_2 = 120^\circ$| $S_3 = 60^\circ, S_4 = 60^\circ$ | Reversa con giro a izquierda |
| **S + D** | Ackermann | Izq: -150, Der: -105 | $S_1 = 60^\circ, S_2 = 60^\circ$  | $S_3 = 120^\circ, S_4 = 120^\circ$| Reversa con giro a derecha |
| **Q** | Point Turn | Izq: -150, Der: +150 | $S_1 = 45^\circ, S_2 = 135^\circ$ | $S_3 = 135^\circ, S_4 = 45^\circ$ | Rotacion 360° en sentido antihorario |
| **E** | Point Turn | Izq: +150, Der: -150 | $S_1 = 135^\circ, S_2 = 45^\circ$ | $S_3 = 45^\circ, S_4 = 135^\circ$ | Rotacion 360° en sentido horario |
| **Espacio** | Failsafe | Izq: 0, Der: 0 | Centrado a $90^\circ$ | Centrado a $90^\circ$ | **PARADA DE EMERGENCIA INMEDIATA** |

---

### 5.2. Procedimiento de Puesta en Marcha

1. **Alimentacion del Rover:** Conectar la bateria al regulador Step-Down de a bordo. Verificar que el LED de encendido del Arduino Nano ESP32 y del modulo de radio NRF24L01 se iluminen.
2. **Conexion del Transmisor:** Conectar el Arduino Nano ESP32 transmisor a la PC mediante cable USB.
3. **Inicio de la Estacion Terrena:**
   * **Opcion A (Rust Nativo):** Ejecutar `Lanzar_HMI_Rust.bat`.
   * **Opcion B (Python):** Ejecutar `Lanzar_HMI_Rover.bat`.
4. **Vinculacion y Handshake:**
   * Seleccionar el puerto COM correspondiente (identificado pasivamente por VID:PID como `Arduino Nano ESP32`).
   * Presionar `[CONECTAR]`. La aplicacion enviara un comando `IDENT` y validara la respuesta de la placa (`ID:NANO_ESP32:TX:v2.1`).
5. **Comprobacion de Pilotaje:**
   * Seleccionar la pestaña `[Simulador]` para observar la odometria proyectada.
   * Probar el accionamiento de avance con la tecla `W` y verificar que las ruedas virtuales y fisicas respondan coordinadamente.
   * Ante cualquier anomalia, presionar la **Barra Espaciadora** para detener inmediatamente toda consigna de traccion.

---

## 6. Estado de Validacion y Bateria de Pruebas Unitarias

El sistema cuenta con cobertura completa de pruebas automatizadas:
* **Workspace Rust (`cargo test --workspace`):** **48 pruebas unitarias aprobadas al 100%**:
  * Validacion estricta del struct `PaqueteRover` a exactamente 6 bytes.
  * Clamping y proteccion de actuadores en rango `[10°, 170°]`.
  * Clamping continuo, presets e inversion modular en modo servos 360°.
  * Integracion numerica de odometria plana y radio de giro ICR en `SimuladorPlano`.
  * Auditoria estricta de erradicacion total de emojis (`test_auditoria_estricta_cero_emojis`).
* **Suite de Pruebas Python (`pytest`):**
  * Verificacion de perfiles de hardware y handshake (`test_hardware_profiles.py`).
  * Validacion del motor de flasheo y saneamiento de puertos (`test_flasher_engine.py`).
  * Ensayos de simulacion cinematica analitica (`simulador_cinematico_rover.py`).
