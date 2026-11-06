# MANUAL Y GUÍA DE ESTUDIO INTEGRAL: ROVER LUNAR CEPIT V2.0
## Plataforma Robótica Móvil Rocker-Bogie 6x6 + Dirección 4WS

> **Material de Estudio y Referencia Técnica Oficial**  
> **Proyecto:** Rover Lunar CEPIT V2.0 (Misión Análoga y Aplicación Industrial de Exploración)  
> **Equipo de Desarrollo CEPIT:** Joaquin, Lucas, Lucio, Sebastian, Emir, Benjamin, Keila y Ainsworth.  
> **Documento:** Guía completa de arquitectura, protocolo de tramas, flujo end-to-end de señales, tecnologías, sockets y conectividad inalámbrica.

---

## ÍNDICE DE CONTENIDOS
1. [Visión General del Sistema y Arquitectura de Tres Nodos](#1-visión-general-del-sistema-y-arquitectura-de-tres-nodos)
2. [Protocolo de Comunicación y Formato Detallado de Comandos](#2-protocolo-de-comunicación-y-formato-detallado-de-comandos)
   - [2.1. Nivel 1: De HMI (PC) a Transmisor (Dongle USB Serie)](#21-nivel-1-de-hmi-pc-a-transmisor-dongle-usb-serie)
   - [2.2. Nivel 2: De Transmisor a Receptor (Radiofrecuencia NRF24L01+)](#22-nivel-2-de-transmisor-a-receptor-radiofrecuencia-nrf24l01)
   - [2.3. Comandos de Diagnóstico, Handshake y Calibración NVS](#23-comandos-de-diagnóstico-handshake-y-calibración-nvs)
   - [2.4. Protocolo Histórico / Legado (WindowsFormsApp4)](#24-protocolo-histórico--legado-windowsformsapp4)
3. [Flujo de Mensajes Paso a Paso (Pulsación de Tecla 'W' a Pines Físicos)](#3-flujo-de-mensajes-paso-a-paso-pulsación-de-tecla-w-a-pines-físicos)
   - [3.1. Fase 1: Captura de Evento y Cinemática en la Interfaz (HMI)](#31-fase-1-captura-de-evento-y-cinemática-en-la-interfaz-hmi)
   - [3.2. Fase 2: Transmisión USB Serial CDC hacia el Dongle Transmisor](#32-fase-2-transmisión-usb-serial-cdc-hacia-el-dongle-transmisor)
   - [3.3. Fase 3: Procesamiento en el Transmisor y Conversión Serie-RF](#33-fase-3-procesamiento-en-el-transmisor-y-conversión-serie-rf)
   - [3.4. Fase 4: Propagación Electromagnética Inalámbrica (2.508 GHz)](#34-fase-4-propagación-electromagnética-inalámbrica-2508-ghz)
   - [3.5. Fase 5: Recepción a Bordo del Rover y Drenaje FIFO](#35-fase-5-recepción-a-bordo-del-rover-y-drenaje-fifo)
   - [3.6. Fase 6: Actuación en Hardware (Puente H L9110S y Servos 4WS)](#36-fase-6-actuación-en-hardware-puente-h-l9110s-y-servos-4ws)
   - [3.7. Fase 7: Evento de Soltado de Tecla y Watchdog Failsafe de Emergencia](#37-fase-7-evento-de-soltado-de-tecla-y-watchdog-failsafe-de-emergencia)
4. [Tecnologías, Puertos, Sockets y Conectividad de Red](#4-tecnologías-puertos-sockets-y-conectividad-de-red)
   - [4.1. Tecnologías de Software y Hardware Empleadas](#41-tecnologías-de-software-y-hardware-empleadas)
   - [4.2. ¿Qué son los "Puertos" en este Sistema? (Hardware vs. Serie vs. Red)](#42-qué-son-los-puertos-en-este-sistema-hardware-vs-serie-vs-red)
   - [4.3. ¿Cómo se Conectan los Arduinos Entre Sí?](#43-cómo-se-conectan-los-arduinos-entre-sí)
   - [4.4. Red Wi-Fi, Modo SoftAP y Sockets de Red (Subsistema de Visión / Cámara)](#44-red-wi-fi-modo-softap-y-sockets-de-red-subsistema-de-visión--cámara)
   - [4.5. Justificación de Ingeniería: ¿Por qué Radiofrecuencia NRF24L01 y no Wi-Fi para Tracción?](#45-justificación-de-ingeniería-por-qué-radiofrecuencia-nrf24l01-y-no-wi-fi-para-tracción)
5. [Pinout Oficial y Conexiones Eléctricas](#5-pinout-oficial-y-conexiones-eléctricas)
6. [Reglas Críticas de Seguridad y Lecciones de Laboratorio](#6-reglas-críticas-de-seguridad-y-lecciones-de-laboratorio)
7. [Preguntas Típicas de Examen / Evaluación Técnica](#7-preguntas-típicas-de-examen--evaluación-técnica)

---

## 1. Visión General del Sistema y Arquitectura de Tres Nodos

El **Rover Lunar CEPIT V2.0** es un vehículo robótico de exploración móvil diseñado para operar en terrenos severamente irregulares, superar obstáculos y encarar pendientes de hasta 20° (simulando regolito y tubos de lava lunar o galerías mineras confinadas).

Su arquitectura electromecánica cuenta con:
* **Chasis Rocker-Bogie 6x6:** Sistema de balancín diferencial pasivo que mantiene las 6 ruedas en contacto constante con el suelo. Posee 6 motores de corriente continua (DC) con caja reductora coordinados a través de un puente H doble L9110S.
* **Dirección 4WS (Four-Wheel Steering):** Cuatro servomotores independientes montados en los vértices del chasis (Front-Left, Front-Right, Rear-Left, Rear-Right). Permite maniobras Ackermann, giro sobre su propio eje (Point Turn 360°) y avance lateral diagonal (Modo Cangrejo / Crab Drive).

### Arquitectura de Tres Nodos Jerárquicos

Para garantizar seguridad, desacoplamiento y latencia predecible, el sistema se divide en **tres nodos principales**:

```
+---------------------------------------------------------------------------------+
|                                 1. ESTACIÓN TERRENA                             |
| PC con Windows: Software HMI oficial en Python (Tkinter) o Rust nativo (egui)   |
+---------------------------------------------------------------------------------+
                                        │
                                        │ Cable USB (Serie CDC a 115200 bps)
                                        │ Trama de Texto CSV
                                        ▼
+---------------------------------------------------------------------------------+
|                        2. NODO TRANSMISOR PUENTE (DONGLE TX)                   |
| Placa: Arduino Nano ESP32 (ESP32-S3 a 3.3V) o ESP32-C3 SuperMini                |
| Módulo de Radio: NRF24L01+ conectado por bus SPI de hardware                   |
+---------------------------------------------------------------------------------+
                                        │
                                        │ Enlace Inalámbrico RF (2.4 GHz ISM)
                                        │ Canal 108 (2.508 GHz) a 250 kbps
                                        │ Trama Binaria Empaquetada (8 bytes)
                                        ▼
+---------------------------------------------------------------------------------+
|                    3. NODO RECEPTOR A BORDO DEL ROVER (RX EJECUTOR)             |
| Placa: Arduino Nano ESP32 (ESP32-S3) o Arduino MKR 1310 (SAMD21)               |
| Módulo de Radio: NRF24L01+ Receptor (SPI Hardware)                              |
| Actuadores: Puente H L9110S (6 motores DC) + 4 Servomotores de Dirección (4WS) |
+---------------------------------------------------------------------------------+
```

> **Alternativa sin computadora:** El proyecto también dispone del sketch `Joystick_Arduino_Nano.ino`, un mando físico autónomo con joysticks analógicos y potenciómetro que se comunica directamente por RF con el rover receptor sin necesidad de conectar la PC.

---

## 2. Protocolo de Comunicación y Formato Detallado de Comandos

La comunicación se articula en dos niveles de abstracción: un nivel de **texto legible (ASCII CSV)** entre la PC y el transmisor, y un nivel **binario estricto de bajo consumo** a través del aire por radiofrecuencia.

```
[ Teclado PC ] ──> [ HMI Python ] ──"W,150,150,90,90,90,90\n"──> [ TX ESP32 ] ──0x96 0x00...──> [ RX Rover ]
```

---

### 2.1. Nivel 1: De HMI (PC) a Transmisor (Dongle USB Serie)

La interfaz gráfica en la computadora envía cadenas de texto ASCII finalizadas en salto de línea (`\n`) a través del puerto serie virtual USB (115200 bps, 8 bits de datos, sin paridad, 1 bit de stop: `115200 8-N-1`).

#### Formato Oficial Extendido (4 Servos):
```text
CMD,PotIzq,PotDer,S1,S2,S3,S4\n
```

#### Descripción de cada campo:
| Campo | Tipo | Rango | Descripción |
|---|---|---|---|
| `CMD` | String | `W`, `S`, `A`, `D`, `PIVOT_IZQ`, `PIVOT_DER`, `CRAB`, `STOP` | Letra o identificador del movimiento solicitado. |
| `PotIzq` | Entero | `0` a `255` | Potencia promedio asignada a los motores del lado izquierdo (M1, M2, M3), calculada tras aplicar los trims individuales. |
| `PotDer` | Entero | `0` a `255` | Potencia promedio asignada a los motores del lado derecho (M4, M5, M6), calculada tras aplicar los trims individuales. |
| `S1` | Entero | `10` a `170` (o `0-360`*) | Ángulo en grados del **Servo Delantero Izquierdo (Front-Left)**. 90° es posición recta. |
| `S2` | Entero | `10` a `170` (o `0-360`*) | Ángulo en grados del **Servo Delantero Derecho (Front-Right)**. 90° es posición recta. |
| `S3` | Entero | `10` a `170` (o `0-360`*) | Ángulo en grados del **Servo Trasero Izquierdo (Rear-Left)**. 90° es posición recta. |
| `S4` | Entero | `10` a `170` (o `0-360`*) | Ángulo en grados del **Servo Trasero Derecho (Rear-Right)**. 90° es posición recta. |

*\*Nota: El rango extendido `0-360` aplica únicamente si se han montado servos de rotación continua.*

#### Catálogo de Tramas Típicas Enviadas por la HMI:

* **Avance Recto (Tecla W presionada a potencia 150):**
  ```text
  W,150,150,90,90,90,90\n
  ```
* **Retroceso Recto (Tecla S presionada a potencia 150):**
  ```text
  S,150,150,90,90,90,90\n
  ```
* **Curva Coordinada a la Izquierda (Tecla A en modo Ackermann):**
  ```text
  A,105,150,120,120,60,60\n
  ```
  *(Las ruedas delanteras giran a 120° y las traseras a 60° para trazar la curva sin arrastre, mientras el lado interno reduce potencia).*
* **Curva Coordinada a la Derecha (Tecla D en modo Ackermann):**
  ```text
  D,150,105,60,60,120,120\n
  ```
* **Rotación Sobre su Eje Antihoraria (Tecla Q / Macro PIVOT_IZQ):**
  ```text
  PIVOT_IZQ,150,150,45,135,135,45\n
  ```
  *(Las cuatro esquinas se alinean a 45° tangenciales al centro del chasis; los motores giran en sentido opuesto).*
* **Rotación Sobre su Eje Horaria (Tecla E / Macro PIVOT_DER):**
  ```text
  PIVOT_DER,150,150,135,45,45,135\n
  ```
* **Modo Cangrejo Diagonal Izquierda (Tecla A en modo CRAB):**
  ```text
  CRAB,150,150,135,135,135,135\n
  ```
* **Parada Normal o de Emergencia (Espacio o tecla liberada):**
  ```text
  STOP,0,0,90,90,90,90\n
  ```
  *(También se aceptan las cadenas cortas `STOP\n`, `PARAR\n` o ` \n`).*

---

### 2.2. Nivel 2: De Transmisor a Receptor (Radiofrecuencia NRF24L01+)

El transmisor no reenvía texto por radio, ya que el texto ASCII es pesado e ineficiente. En su lugar, empaqueta los datos en una **estructura binaria pura en C++** con alineación estricta de memoria mediante `__attribute__((packed))`:

```cpp
struct __attribute__((packed)) PaqueteControl {
  int16_t traccion_izq;  // 2 Bytes: -255 a +255 (Signo indica sentido: + avance, - reversa)
  int16_t traccion_der;  // 2 Bytes: -255 a +255 (Signo indica sentido: + avance, - reversa)
  uint8_t angulo_s1;     // 1 Byte:  10 a 170 grados (Servo Delantero Izquierdo)
  uint8_t angulo_s2;     // 1 Byte:  10 a 170 grados (Servo Delantero Derecho)
  uint8_t angulo_s3;     // 1 Byte:  10 a 170 grados (Servo Trasero Izquierdo)
  uint8_t angulo_s4;     // 1 Byte:  10 a 170 grados (Servo Trasero Derecho)
};
```

#### Anatomía Byte a Byte del Paquete de Radio (Tamaño Total: Exactamente 8 Bytes):

| Offset (Byte) | Campo | Tipo de Dato | Representación en Memoria | Rango Válido |
|---|---|---|---|---|
| **0 y 1** | `traccion_izq` | `int16_t` (con signo) | Little-Endian (Byte Bajo primero, Byte Alto después) | `-255` a `+255` |
| **2 y 3** | `traccion_der` | `int16_t` (con signo) | Little-Endian (Byte Bajo primero, Byte Alto después) | `-255` a `+255` |
| **4** | `angulo_s1` | `uint8_t` (sin signo) | Entero sin signo de 8 bits | `10` a `170` |
| **5** | `angulo_s2` | `uint8_t` (sin signo) | Entero sin signo de 8 bits | `10` a `170` |
| **6** | `angulo_s3` | `uint8_t` (sin signo) | Entero sin signo de 8 bits | `10` a `170` |
| **7** | `angulo_s4` | `uint8_t` (sin signo) | Entero sin signo de 8 bits | `10` a `170` |

#### ¿Por qué `__attribute__((packed))`?
Los microcontroladores modernos de 32 bits (como el ESP32-S3 o el SAMD21 de ARM) suelen añadir "bytes de relleno" (*padding*) para que las variables comiencen en direcciones de memoria múltiplos de 4. Si el transmisor y el receptor tienen compiladores o arquitecturas distintas, los bytes quedarían desalineados y los datos llegarían corruptos. Con `packed`, se fuerza al procesador a empaquetar los campos de forma contigua sin ningún byte de desperdicio.

#### Parámetros del Enlace de Radiofrecuencia:
* **Frecuencia / Canal:** **Canal 108** de la banda ISM.  
  $$Frecuencia = 2400\,\text{MHz} + 108\,\text{MHz} = 2508\,\text{MHz} = 2.508\,\text{GHz}$$  
  *Justificación técnica:* Las redes Wi-Fi domésticas (canales 1 al 13) ocupan el rango de 2.412 GHz a 2.472 GHz. El canal 108 opera **por encima de todo el espectro Wi-Fi comercial**, haciendo que la señal del Rover sea inmune a routers y teléfonos celulares.
* **Tasa de transferencia (Data Rate):** `RF24_250KBPS` (250 kilobits por segundo).  
  *Justificación técnica:* Cuanto menor es la tasa de datos, mayor es la sensibilidad del receptor (-94 dBm) y mayor la penetración frente a obstáculos físicos o regolito.
* **Potencia:** `RF24_PA_MAX` (+0 dBm de salida de radio).
* **Dirección del Tubo de Enlace (Pipe):** Cadena de 5 bytes `"ROVER"` (o valor hexadecimal `0xF0F0F0F0E1LL`).
* **Auto-Acknowledge:** Desactivado (`radio.setAutoAck(false)`).  
  *Justificación técnica:* Se utiliza un régimen de **streaming continuo a 20-28 Hz**. Si un paquete se pierde por ruido momentáneo, no se pierde tiempo reintentando: a los 35-50 ms llega una trama más nueva y fresca.

---

### 2.3. Comandos de Diagnóstico, Handshake y Calibración NVS

En la suite de laboratorio y en la versión `HMI_Rover_V2_1_pre.py`, la PC puede dialogar directamente con el firmware a través de comandos de control:

1. **Autodetección y Handshake Activo:**
   * La PC envía: `IDENT\n`
   * El transmisor responde: `ID:<PLACA>:<ROL>:<VERSION>\n`  
     *Ejemplo oficial:* `ID:NANO_ESP32:TX:v2.1`
2. **Prueba de Conectividad (Ping):**
   * La PC envía: `PING\n`
   * El transmisor responde: `PONG:TX:NANO_ESP32\n`
3. **Sincronización de Calibración Pre-Despliegue:**
   * La PC envía los factores de corrección de motores y centros de servos ajustados en la pantalla:
     ```text
     CALIB,m1,m2,m3,m4,m5,m6,s1,s2,s3,s4\n
     ```
   * Seguido de la orden de guardado en memoria permanente Flash:
     ```text
     PERSIST_NVS\n
     ```
     *(NVS = Non-Volatile Storage del ESP32. Permite que el Rover recuerde su calibración tras apagar la batería).*

---

### 2.4. Protocolo Histórico / Legado (WindowsFormsApp4)

En la primera etapa del proyecto (interfaz desarrollada en C# .NET Windows Forms por el grupo anterior), la comunicación era más elemental:
* La PC abría el puerto COM y enviaba cadenas de 3 letras:
  * `"avz\n"` $\rightarrow$ Avanzar
  * `"rct\n"` $\rightarrow$ Retroceder
  * `"izq\n"` $\rightarrow$ Girar a la izquierda
  * `"der\n"` $\rightarrow$ Girar a la derecha
  * `"stp\n"` $\rightarrow$ Parar
* El Rover enviaba telemetría de sensores en una cadena separada por comas:
  ```text
  temp,hum,lux\n
  Ejemplo: "13,62,1\n" (Temperatura 13°C, Humedad 62%, Luminosidad 1 lux)
  ```
* *Limitación superada:* Este sistema anterior no permitía regular la velocidad (PWM proporcional), ni recortar potencias para corregir asimetrías de motores, ni controlar de forma independiente los 4 servomotores de dirección.

---

## 3. Flujo de Mensajes Paso a Paso (Pulsación de Tecla 'W' a Pines Físicos)

A continuación se detalla con precisión cronológica y técnica el camino exacto que recorre la información cuando el operador presiona la tecla **W** en la computadora:

```
[Usuario presiona 'W'] 
       │ 
       ▼ (1) Evento Tkinter <KeyPress> en PC
[HMI Python / HMI_Rover_V2.py]
       │ 
       ▼ (2) Buffer Serie USB CDC a 115200 bps: "W,150,150,90,90,90,90\n"
[Dongle Transmisor: Arduino Nano ESP32 / ESP32-C3]
       │ 
       ▼ (3) Parseo strtok_r() + Empaquetado binario PaqueteControl (8 bytes)
[Transceptor NRF24L01+ Emisor]
       │ 
       ▼ (4) Onda RF en Canal 108 (2.508 GHz) por el aire
[Transceptor NRF24L01+ Receptor a bordo del Rover]
       │ 
       ▼ (5) Lectura por bus SPI Hardware (D9, D10, D11, D12, D13)
[Microcontrolador Ejecutor: Arduino Nano ESP32]
       │ 
       ▼ (6) Generación de Señales Físicas en Pines GPIO
       ├─► Pin D2 (A1A): PWM 150/255 ────► Entrada Puente H L9110S ──► Motores M1, M2, M3 (Giro Avance)
       ├─► Pin D5 (A1B): LOW (0V)    ────► Entrada Puente H L9110S
       ├─► Pin D3 (B1A): PWM 150/255 ────► Entrada Puente H L9110S ──► Motores M4, M5, M6 (Giro Avance)
       ├─► Pin D4 (B1B): LOW (0V)    ────► Entrada Puente H L9110S
       └─► Pines D6, D7, D8, A0      ────► Pulsos PWM 50 Hz (1.5 ms) ─► Servos S1, S2, S3, S4 (Centrados a 90°)
```

---

### 3.1. Fase 1: Captura de Evento y Cinemática en la Interfaz (HMI)
1. **Detección del teclado:** El operador presiona la tecla `W`. El gestor de ventanas de Tkinter dispara el evento `<KeyPress>`.
2. **Filtro Anti-Rebote (Key Repeat Suppression):** En Windows, mantener apretada una tecla genera decenas de eventos automáticos de repetición por segundo. La HMI consulta su diccionario `teclas_presionadas['w']`. Como ya está en `True`, ignora repeticiones espurias para no congestionar el puerto serie.
3. **Cálculo Cinemático:**
   * La interfaz lee los deslizadores de Trim porcentual de los motores (M1 a M6) y los potenciómetros Master (por ejemplo, valor nominal `150`).
   * Calcula el PWM efectivo izquierdo `pot_izq = 150` y derecho `pot_der = 150`.
   * En modo recto, los ángulos de los 4 servomotores se establecen en **90°** (posición neutra de avance).
4. **Construcción de la Trama:** Se ensambla la cadena:
   ```python
   trama = f"W,{pot_izq},{pot_der},90,90,90,90\n"
   # Resultado: "W,150,150,90,90,90,90\n"
   ```

### 3.2. Fase 2: Transmisión USB Serial CDC hacia el Dongle Transmisor
1. La HMI codifica la cadena a bytes ASCII: `trama.encode('ascii')`.
2. Invoca el método `self.serial_conn.write(...)` de la librería `pyserial`.
3. El paquete se transfiere por el cable USB físico mediante la emulación CDC (Communication Device Class) a **115200 baudios**.

### 3.3. Fase 3: Procesamiento en el Transmisor y Conversión Serie-RF
1. El microcontrolador del dongle (Arduino Nano ESP32 o ESP32-C3) ejecuta en su función `loop()` la rutina `leerSerialNoBloqueante()`.
2. Lee byte a byte del puerto serie y los almacena en su arreglo `bufferSerial[128]`. No utiliza ninguna llamada bloqueante `delay()`.
3. Al detectar el carácter de fin de línea `\n`, invoca `procesarComando()`.
4. Mediante la función de tokenización en C++ `strtok_r()` separa los valores por comas:
   * Extrae el comando: `cmd = "W"`
   * Extrae potencias: `potIzq = 150`, `potDer = 150`
   * Extrae ángulos: `s1 = 90`, `s2 = 90`, `s3 = 90`, `s4 = 90`
5. Pasa los ángulos por la función de seguridad: `constrain(s, 10, 170)`.
6. Carga la estructura `PaqueteControl`:
   ```cpp
   datosControl.traccion_izq = 150;
   datosControl.traccion_der = 150;
   datosControl.angulo_s1 = 90;
   datosControl.angulo_s2 = 90;
   datosControl.angulo_s3 = 90;
   datosControl.angulo_s4 = 90;
   ```
7. En el ciclo temporizado por `millis()` (cada 35 a 50 ms), el microcontrolador envía los 8 bytes al chip NRF24L01 mediante el bus SPI:
   ```cpp
   radio.write(&datosControl, sizeof(datosControl));
   ```
8. **Feedback Visual:** Si el transmisor es el Arduino Nano ESP32, dispara un pulso de 30 ms en el **LED verde integrado** indicando transmisión RF exitosa.

### 3.4. Fase 4: Propagación Electromagnética Inalámbrica (2.508 GHz)
1. El módulo NRF24L01 modula la trama en modulación GFSK a 250 kbps en la frecuencia de **2.508 GHz** (Canal 108).
2. La señal viaja por el aire sin colisionar con señales Wi-Fi ni Bluetooth.

### 3.5. Fase 5: Recepción a Bordo del Rover y Drenaje FIFO
1. La antena del módulo NRF24L01 a bordo del rover captura el paquete.
2. El receptor verifica que la dirección de destino coincida con `"ROVER"` y que la suma de comprobación interna (CRC por hardware del chip de radio) sea válida.
3. En el `loop()` del microcontrolador de a bordo (Arduino Nano ESP32 ejecutor), se evalúa `if (radio.available())`.
4. **Drenaje de la pila FIFO:** Para asegurar que el Rover no responda con retraso acumulado, se vacía la memoria intermedia procesando únicamente la última trama recibida:
   ```cpp
   while (radio.available()) {
     radio.read(&paquete, sizeof(paquete));
   }
   ```
5. **Reinicio del Watchdog:** Se actualiza el cronómetro de seguridad:
   ```cpp
   ultimaRecepcion = millis();
   ```

### 3.6. Fase 6: Actuación en Hardware (Puente H L9110S y Servos 4WS)

#### A. Control de Motores DC (Tracción):
Se invoca la función `aplicarControlMotores(150, 150)`:
1. **Lado Izquierdo (Motores M1, M2, M3):**
   * Como `pwmIzq = +150` (positivo $\rightarrow$ avance):
   * Pin **D5** (`A1B` Reversa) se apaga a nivel bajo: `analogWrite(pinA1B, 0);` (0V).
   * Pin **D2** (`A1A` Avance) recibe la señal PWM modulada: `analogWrite(pinA1A, 150);`.
   * El circuito integrado HG7881 / L9110S polariza los terminales de los 3 motores izquierdos, haciéndolos rotar hacia adelante con un ciclo de trabajo del $58.8\%$ ($150/255$).
2. **Lado Derecho (Motores M4, M5, M6):**
   * Como `pwmDer = +150` (positivo $\rightarrow$ avance):
   * Pin **D4** (`B1B` Reversa) se apaga a nivel bajo: `analogWrite(pinB1B, 0);` (0V).
   * Pin **D3** (`B1A` Avance) recibe la señal PWM modulada: `analogWrite(pinB1A, 150);`.
   * Los 3 motores derechos rotan hacia adelante a la misma velocidad.

#### B. Control de Servomotores (Dirección):
El microcontrolador genera señales de tren de pulsos PWM estándar a 50 Hz (período de 20 ms) en los pines dedicados:
* **Pin D6:** Pulso de 1.5 ms para posicionar el **Servo 1 (Front-Left)** a 90°.
* **Pin D7:** Pulso de 1.5 ms para posicionar el **Servo 2 (Front-Right)** a 90°.
* **Pin D8:** Pulso de 1.5 ms para posicionar el **Servo 3 (Rear-Left)** a 90°.
* **Pin A0:** Pulso de 1.5 ms para posicionar el **Servo 4 (Rear-Right)** a 90°.
* *Resultado mecánico:* Los 4 ejes de las esquinas quedan alineados paralelamente al chasis. El Rover avanza en línea recta perfecta.

### 3.7. Fase 7: Evento de Soltado de Tecla y Watchdog Failsafe de Emergencia

#### ¿Qué ocurre cuando el operador suelta la tecla 'W'?
1. Se dispara en la PC el evento `<KeyRelease>`.
2. La HMI detecta que no hay teclas direccionales oprimidas y envía de inmediato:
   ```text
   STOP,0,0,90,90,90,90\n
   ```
3. El transmisor emite una trama binaria con `traccion_izq = 0` y `traccion_der = 0`.
4. El receptor a bordo ejecuta `pararMotores()`:
   * Coloca los pines **D2, D5, D3, D4** en nivel bajo (`analogWrite(pin, 0)`).
   * Los transistores del puente H cortan la corriente y los 6 motores se detienen al instante.

#### ¿Qué ocurre si se corta la comunicación por radio (interferencia o alcance)?
* Si el Rover deja de recibir paquetes durante más de **1000 ms** (1 segundo):
  ```cpp
  if (millis() - ultimaRecepcion > TIMEOUT_MS) {
    pararMotores();
  }
  ```
* Se activa el **Watchdog Failsafe por software**: el vehículo frena en seco de manera autónoma, evitando colisiones o caídas por pérdida de control.

---

## 4. Tecnologías, Puertos, Sockets y Conectividad de Red

---

### 4.1. Tecnologías de Software y Hardware Empleadas

El proyecto integra un stack multidisciplinario de computación embebida y aplicaciones de escritorio:

| Subsistema | Tecnología / Herramienta | Función en el Proyecto |
|---|---|---|
| **Microcontrolador Oficial** | **Arduino Nano ESP32** (ESP32-S3) | Procesador dual-core Tensilica a 240 MHz, lógica nativa a 3.3V, soporte FreeRTOS. Utilizado como receptor a bordo y transmisor USB. |
| **Microcontrolador Alternativo** | **ESP32-C3 SuperMini** (RISC-V) | Microcontrolador de 32 bits a 160 MHz con USB CDC nativo, utilizado en los dongles de transmisión compactos. |
| **Microcontrolador Previo** | **Arduino MKR WAN 1310** (SAMD21) | Procesador ARM Cortex-M0+ a 48 MHz y 3.3V, utilizado en las primeras versiones de receptor a bordo. |
| **Mando Autónomo** | **Arduino Nano Clásico** (ATmega328P) | Microcontrolador AVR de 8 bits a 16 MHz para el joystick de radiocontrol físico. |
| **Transceptores de Radio** | **Nordic Semiconductor NRF24L01+** | Chips de radiofrecuencia a 2.4 GHz en bus SPI de alta velocidad. |
| **Control de Potencia** | **Puente H L9110S (HG7881)** | Etapa de potencia de doble canal H-Bridge para corriente continua bidireccional de 6 motores. |
| **Actuación de Dirección** | **Servomotores TowerPro SG90 / MG90S** | Servos analógicos de 50 Hz para orientación independiente de las ruedas esquineras. |
| **Regulación Eléctrica** | **Módulos Step-Down Buck DC-DC** | Fuentes conmutadas de alta eficiencia para aislar los 5V-6V de los servos sin sobrecalentamiento. |
| **HMI Principal** | **Python 3 + Tkinter + PySerial** | Aplicación gráfica de escritorio para Windows/Linux con panel de control, trims e hilo receptor serie. |
| **Stack Nativo de Rendimiento**| **Rust (egui / eframe / serialport)** | Aplicación de escritorio paralela compilada directamente a código máquina nativo con renderizado acelerado por GPU y simulador cinemático 2D. |
| **Herramientas de Compilación**| **arduino-cli & esptool.py** | Motores en línea de comandos integrados en la GUI para flasheo de firmwares en 1 clic. |

---

### 4.2. ¿Qué son los "Puertos" en este Sistema? (Hardware vs. Serie vs. Red)

Es muy común confundir los distintos conceptos de la palabra **puerto** en una defensa técnica o examen. En este proyecto conviven tres tipos de puertos totalmente distintos:

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                    TIPOS DE PUERTOS                     │
                  └─────────────────────────────────────────────────────────┘
                                               │
         ┌─────────────────────────────────────┼─────────────────────────────────────┐
         ▼                                     ▼                                     ▼
1. PUERTOS FÍSICOS (GPIO)             2. PUERTOS SERIE COM (OS)             3. PUERTOS DE RED (SOCKETS)
Pines del chip:                       Puertos lógicos USB en Windows:       Puertos lógicos TCP/UDP:
- D2, D3, D4, D5 (Puente H)           - COM3, COM4, COM5                    - Puerto 80 (HTTP Web)
- D6, D7, D8, A0 (Servomotores)       - VID/PID (0x2341:0x0070)             - Puerto 81 (Streaming MJPEG)
- D9, D10, D11, D12, D13 (Bus SPI)    - Baudrate: 115200 bps                - Puerto 8888 (Telemetría UDP)
```

1. **Puertos Físicos de Hardware (Pines GPIO):**
   * Son las patillas metálicas de entrada/salida del microcontrolador.
   * *Ejemplo:* Pin D2 configurado como salida PWM para el motor izquierdo; Pin D9 como salida digital CE para habilitar la radio.
2. **Puertos Serie del Sistema Operativo (Puertos COM Virtuales):**
   * En Windows, la conexión USB con el microcontrolador se expone como un puerto serie virtual (ejemplo: `COM3`, `COM4`).
   * La interfaz identifica automáticamente la placa leyendo los códigos de fabricante y producto del USB (**VID:PID**):
     * Arduino Nano ESP32: `0x2341 : 0x0070`
     * ESP32-C3 SuperMini: `0x303A : 0x1001`
     * Arduino MKR 1310: `0x2341 : 0x8054`
3. **Puertos Lógicos de Red (Protocolos TCP/UDP):**
   * Son los identificadores de 16 bits utilizados en la capa de transporte de la pila de red IP (ejemplo: puerto 80 para HTTP, puerto 81 para video streaming).

---

### 4.3. ¿Cómo se Conectan los Arduinos Entre Sí?

Entre el Arduino Transmisor (en la PC) y el Arduino Receptor (a bordo del Rover) **no existe ningún cable físico**.

* La interconexión se establece mediante un **enlace inalámbrico punto a punto por radiofrecuencia (RF)** con los módulos **NRF24L01+**.
* Ambos transceptores se comunican con sus respectivos microcontroladores a través del **bus SPI de hardware** (líneas MOSI, MISO, SCK) más dos líneas de control digital (**CE** para conmutar entre emisión y reposo, y **CSN** para seleccionar el chip en el bus).
* Si dentro del propio Rover se integran dos placas (por ejemplo, el Arduino Nano ESP32 principal y un módulo de cámara ESP32-CAM auxiliar):
  * Se conectan mediante el puerto **UART serie auxiliar (Pines D0/RX y D1/TX cruzados)** compartiendo tierra común (GND).
  * O mediante el **Bus I2C (Pines A4/SDA y A5/SCL)** para compartir datos de sensores inerciales.

---

### 4.4. Red Wi-Fi, Modo SoftAP y Sockets de Red (Subsistema de Visión / Cámara)

El proyecto cuenta con un subsistema de visión y telemetría óptica basado en un módulo **ESP32-CAM (cámara OV2640)** montado sobre un servomotor orientable.

Aquí es donde entra en juego la **red Wi-Fi y los sockets de red**:

```
+---------------------------------------------------------------------------------+
|                          ROVER: MÓDULO ESP32-CAM                                |
|  Crea una red inalámbrica propia en modo SoftAP:                               |
|  - SSID: "ROVER_LUNAR_CEPIT"                                                    |
|  - IP del Servidor: 192.168.4.1                                                 |
+---------------------------------------------------------------------------------+
                                        │
                         Red Wi-Fi 802.11 b/g/n (Canal 1 o 6)
                                        │
                                        ▼
+---------------------------------------------------------------------------------+
|                       ESTACIÓN DE CONTROL / NAVEGADOR PC                        |
|  Se conecta a la red Wi-Fi y abre los sockets de red:                           |
|  1. Socket TCP Puerto 80:  http://192.168.4.1/ (Página Web de Control)          |
|  2. Socket TCP Puerto 81:  http://192.168.4.1:81/stream (Video en Vivo MJPEG)  |
|  3. Socket UDP Puerto 8888: Datagramas rápidos de telemetría / sensores         |
+---------------------------------------------------------------------------------+
```

#### A. Creación de la Red Wi-Fi (Modo SoftAP):
En lugar de depender de un router externo que no existe en una cueva o en un terreno de prueba en la sierra, el ESP32-CAM se autoconfigura como **Access Point por software (SoftAP)**:
```cpp
WiFi.mode(WIFI_AP);
WiFi.softAP("ROVER_LUNAR_CEPIT", "cepit2026");
IPAddress ipLocal = WiFi.softAPIP(); // Por defecto: 192.168.4.1
```
El microcontrolador levanta un servidor DHCP interno que le asigna automáticamente una dirección IP a la computadora que se conecte a su red.

#### B. Sockets y Puertos Utilizados en la Red Wi-Fi:
1. **Socket HTTP / Web Server (Puerto TCP 80):**
   * Escucha peticiones HTTP estándar. Cuando el usuario abre `http://192.168.4.1`, el ESP32 responde con el código HTML/JavaScript que dibuja la vista de la cámara y los deslizadores de brillo/resolución.
2. **Socket de Streaming de Video MJPEG (Puerto TCP 81 o Endpoint `:81/stream`):**
   * Abre un socket TCP persistente que no se cierra.
   * Envía un flujo continuo de imágenes comprimidas en JPEG con la cabecera MIME `multipart/x-mixed-replace; boundary=frame`.
   * Cada vez que la cámara captura un cuadro nuevo, lo envía al socket precedido por su tamaño en bytes, permitiendo ver el video en vivo a 25-30 cuadros por segundo en la pantalla del operador.
3. **Socket UDP para Telemetría Rápida (Puerto UDP típico 8888 o 4210):**
   * A diferencia de TCP (que exige confirmación de recepción / ACK y reenvía paquetes perdidos generando demoras), los sockets UDP envían datagramas sin confirmación.
   * Es la opción ideal si se desea transmitir datos de inclinómetro (pitch, roll) o lecturas de batería por Wi-Fi sin generar retardo acumulativo.
4. **WebSockets (Puerto 80 o 81):**
   * Canal bidireccional dúplex establecido sobre una conexión TCP inicial para enviar paquetes JSON livianos entre la interfaz web y el microcontrolador.

---

### 4.5. Justificación de Ingeniería: ¿Por qué Radiofrecuencia NRF24L01 y no Wi-Fi para Tracción?

Una de las preguntas más importantes en cualquier presentación de este proyecto es:  
**"Si el ESP32 ya tiene Wi-Fi integrado, ¿por qué le agregaron un módulo NRF24L01 externo para mover las ruedas?"**

| Criterio de Ingeniería | Wi-Fi Estándar (802.11 b/g/n) | Radiofrecuencia NRF24L01+ (Canal 108) |
|---|---|---|
| **Determinismo y Latencia** | **No determinista (15 ms a 300 ms):** La pila TCP/IP negocia paquetes y reintenta envíos si hay pérdidas, provocando "tirones" o retardo repentino en el frenado. | **Altamente determinista (< 2 ms):** Comunicación directa por hardware a nivel de paquete crudo (streaming continuo a 20-28 Hz). |
| **Inmunidad a Interferencias** | **Baja:** Los canales 1 al 13 operan entre 2.412 GHz y 2.472 GHz, saturados por teléfonos, laptops y routers cercanos. | **Total:** Configurado en **Canal 108 (2.508 GHz)**, una zona del espectro completamente limpia de Wi-Fi doméstico. |
| **Consumo Eléctrico** | **Alto (150 mA - 250 mA):** Mantener la pila de red y el receptor Wi-Fi activo consume rápidamente la batería del rover. | **Muy Bajo (12 mA - 15 mA):** Ideal para maximizar la autonomía del vehículo sobre el terreno. |
| **Comportamiento ante caídas** | Si la señal se debilita, el handshake TCP se congela mientras intenta reconectarse. | Si una trama no llega, el receptor sigue escuchando y procesa la siguiente sin bloquearse. Si pasan 1000 ms, el Watchdog frena el rover. |
| **Aislamiento de Cargas** | Si la transmisión de video por Wi-Fi satura el procesador o la red, el control de tracción se congelaría. | **Arquitectura Separada:** El video viaja por Wi-Fi en un módulo aislado, mientras la tracción crítica viaja por su propio canal RF dedicado e independiente. |

---

## 5. Pinout Oficial y Conexiones Eléctricas

### 5.1. Nodo Transmisor: Arduino Nano ESP32 (Dongle PC)
Conectado por cable USB a la computadora:

| Pin del NRF24L01 | Pin Arduino Nano ESP32 | GPIO Interno | Función |
|---|---|---|---|
| **VCC** | **3.3V** | — | Alimentación 3.3V regulada (+ Capacitor 10-100 µF) |
| **GND** | **GND** | — | Masa común |
| **CE** | **Pin D9** | GPIO 18 | Habilitación de Radio (Chip Enable) |
| **CSN** | **Pin D10** | GPIO 21 | Chip Select SPI |
| **MOSI** | **Pin D11** | GPIO 38 | Bus SPI Hardware (Master Out) |
| **MISO** | **Pin D12** | GPIO 47 | Bus SPI Hardware (Master In) |
| **SCK** | **Pin D13** | GPIO 48 | Reloj de Bus SPI |
| **LED RGB (Verde)** | **LED_GREEN** | GPIO 0 | Pulso de confirmación de transmisión RF exitosa (30 ms) |
| **LED RGB (Rojo)** | **LED_RED** | GPIO 46 | Alerta de error en radio o saturación FIFO |
| **LED RGB (Azul)** | **LED_BLUE** | GPIO 45 | Estado de reposo / Dongle en espera |

---

### 5.2. Nodo Receptor Oficial: Arduino Nano ESP32 (A Bordo del Rover)
Montado físicamente en el chasis del vehículo:

| Componente | Pin del Módulo | Pin Arduino Nano ESP32 | GPIO Interno | Función / Señal |
|---|---|---|---|---|
| **NRF24L01** | VCC | **3.3V** | — | Salida 3.3V regulada (+ Capacitor electrolítico) |
| **NRF24L01** | GND | **GND** | — | Masa común del chasis |
| **NRF24L01** | CE | **Pin D9** | GPIO 18 | Habilitación de recepción de radio |
| **NRF24L01** | CSN | **Pin D10** | GPIO 21 | Chip Select SPI |
| **NRF24L01** | MOSI | **Pin D11** | GPIO 38 | SPI Hardware |
| **NRF24L01** | MISO | **Pin D12** | GPIO 47 | SPI Hardware |
| **NRF24L01** | SCK | **Pin D13** | GPIO 48 | SPI Hardware |
| **Puente H L9110S** | A1A | **Pin D2** | GPIO 4 | Tracción Izquierda - Avance (PWM 0-255) |
| **Puente H L9110S** | A1B | **Pin D5** | GPIO 7 | Tracción Izquierda - Reversa (PWM 0-255) |
| **Puente H L9110S** | B1A | **Pin D3** | GPIO 5 | Tracción Derecha - Avance (PWM 0-255) |
| **Puente H L9110S** | B1B | **Pin D4** | GPIO 6 | Tracción Derecha - Reversa (PWM 0-255) |
| **Servo S1** | Señal | **Pin D6** | GPIO 8 | Dirección Delantera Izquierda (FL) |
| **Servo S2** | Señal | **Pin D7** | GPIO 9 | Dirección Delantera Derecha (FR) |
| **Servo S3** | Señal | **Pin D8** | GPIO 17 | Dirección Trasera Izquierda (RL) |
| **Servo S4** | Señal | **Pin A0** | GPIO 1 | Dirección Trasera Derecha (RR) |
| **Step-Down DC-DC** | VCC Servos | Alimentación Externa | — | Regulador conmutado aislado a 5V-6V para servos |

---

### 5.3. Pines Libres para Expansión Futura (Arduino Nano ESP32)
* **D0 (RX) y D1 (TX):** Puerto Serie Hardware UART0 libre. Permite interconectar el módulo ESP32-CAM o un GPS sin interferir con la radio.
* **A4 (SDA) y A5 (SCL):** Bus I2C de hardware libre. Diseñado para conectar un sensor IMU / Giroscopio (MPU6050 o BNO055) que mida la inclinación en la rampa a 20° de CEPIT.
* **A1:** Entrada Analógica ADC (12 bits) libre. Diseñada para monitorear el voltaje de la batería LiPo mediante un divisor resistivo.
* **A2 y A3:** Entradas/salidas libres para sensores de distancia por ultrasonido (HC-SR04) o láser ToF (VL53L0X) para frenado autónomo anticolisión.

---

## 6. Reglas Críticas de Seguridad y Lecciones de Laboratorio

Durante el desarrollo del proyecto en el CEPIT se produjeron situaciones de falla física que dieron origen a **cinco reglas de oro de hardware**:

> [!CAUTION]
> **1. ALIMENTACIÓN DEL MÓDULO NRF24L01: NUNCA CONECTAR A 5V**  
> El módulo NRF24L01 tolera niveles lógicos de 5V en sus pines SPI, pero **su pin VCC debe ser alimentado estrictamente con 3.3V**. Conectarlo a la línea de 5V destruye instantáneamente el chip de radiofrecuencia.

> [!IMPORTANT]
> **2. CAPACITOR ELECTROLÍTICO OBLIGATORIO (10 µF a 100 µF)**  
> Es imprescindible soldar un capacitor electrolítico directamente entre las patillas **VCC y GND** de cada módulo NRF24L01. Durante la emisión de radio, el chip demanda picos transitorios de corriente que provocan caídas bruscas de tensión. Sin este capacitor, el sistema sufre una pérdida masiva e intermitente de paquetes.

> [!WARNING]
> **3. ALIMENTACIÓN DE LOS SERVOMOTORES: PROHIBIDO USAR REGULADORES LM7805**  
> Cuatro servomotores bajo esfuerzo mecánico demandan picos de corriente superiores a 2 Amperios. Los reguladores lineales tipo 7805 disipan el exceso de tensión en forma de calor y entran en protección térmica o se queman (lección aprendida tras quemar un SG90 a 8V). Se debe emplear exclusivamente un **regulador conmutado Step-Down (Buck)** regulado a **5V - 6V** con tierra (GND) unida al resto del sistema.

> [!IMPORTANT]
> **4. LÍMITES DE ÁNGULO POR SOFTWARE ([10°, 170°])**  
> Los servomotores analógicos estándar poseen topes mecánicos en 0° y 180°. Forzarlos contra estos topes provoca atascos mecánicos y destruye la piñonería interna. Por software, todo comando se restringe estrictamente mediante la función `constrain(angulo, 10, 170)`.

> [!NOTE]
> **5. CERO DELAYS Y WATCHDOG FAILSAFE DE 1 SEGUNDO**  
> Ningún firmware de control contiene llamadas bloqueantes a `delay()`. Todas las temporizaciones se calculan con contadores no bloqueantes basados en `millis()`. Asimismo, si el receptor no detecta una trama válida durante más de 1000 ms, apaga automáticamente todos los motores a 0 de forma preventiva.

---

## 7. Preguntas Típicas de Examen / Evaluación Técnica

### P1: ¿Qué formato tienen los comandos que viajan entre la PC y el transmisor?
**R:** Es una trama de texto en formato CSV terminada en salto de línea: `CMD,PotIzq,PotDer,S1,S2,S3,S4\n`. Por ejemplo, para avanzar: `W,150,150,90,90,90,90\n`. Contiene el identificador del movimiento, los valores de PWM de cada lado (0-255) y los ángulos individuales de los cuatro servomotores (10-170°).

### P2: ¿Qué formato tienen las tramas que viajan por el aire hacia el Rover?
**R:** Son paquetes binarios estrictamente empaquetados (`__attribute__((packed))`) de exactamente **8 bytes**: dos enteros con signo de 16 bits para la tracción izquierda y derecha (`int16_t`, 4 bytes en total) y cuatro enteros sin signo de 8 bits para los ángulos de los cuatro servos (`uint8_t`, 4 bytes en total).

### P3: ¿Por qué se configuró la radio en el Canal 108?
**R:** Porque el canal 108 corresponde a la frecuencia de **2.508 GHz**, ubicada por encima del espectro del Wi-Fi tradicional (canales 1 al 13, que van de 2.412 a 2.472 GHz). Esto garantiza que la señal del Rover sea inmune a la saturación e interferencias provocadas por teléfonos móviles y redes domésticas.

### P4: ¿Cómo se conectan los Arduinos físicamente? ¿Hay cables entre ellos?
**R:** No hay cables entre el transmisor y el receptor. Se conectan por radiofrecuencia mediante transceptores NRF24L01+. Cada transceptor se comunica con su propio microcontrolador mediante el bus serie sincrónico de alta velocidad **SPI de hardware** (líneas MOSI, MISO, SCK, CSN y CE).

### P5: ¿Se usa red Wi-Fi y sockets en el proyecto? ¿Dónde?
**R:** Sí, pero no para la tracción de los motores. Se utiliza en el subsistema de visión y video mediante el módulo **ESP32-CAM**. El ESP32 crea su propia red inalámbrica en modo **SoftAP** (Access Point con IP `192.168.4.1`). La computadora se conecta a esa red y abre un **socket HTTP en el puerto 80** para la interfaz web y un **socket persistente de streaming MJPEG en el puerto 81** (`/stream`) para ver la transmisión de video en vivo. Para datos de sensores sin retardo se pueden utilizar sockets **UDP** (puerto 8888).

### P6: ¿Qué pasa si el transmisor se desconecta mientras el Rover está avanzando a máxima velocidad?
**R:** Se activa el mecanismo de seguridad **Watchdog Failsafe**. El lazo principal del receptor evalúa el tiempo transcurrido desde la última trama válida con `millis() - ultimaRecepcion`. Al superar los **1000 ms** (1 segundo), el microcontrolador llama a `pararMotores()`, colocando todas las salidas del puente H en 0V y deteniendo el vehículo de forma inmediata.
