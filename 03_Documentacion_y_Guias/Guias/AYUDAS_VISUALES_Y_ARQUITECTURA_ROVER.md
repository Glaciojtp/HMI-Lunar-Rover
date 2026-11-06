# AYUDAS VISUALES, DIAGRAMAS Y ARQUITECTURA: ROVER LUNAR CEPIT V2.0
## Material Gráfico de Presentación, Diagramas de Flujo y Esquemas de Hardware

> **Documento de Apoyo Visual para Demostraciones, Defensas Técnicas y Exposición**  
> **Proyecto:** Rover Lunar CEPIT V2.0 — Plataforma Rocker-Bogie 6x6 + 4WS  
> **Equipo CEPIT:** Joaquin, Lucas, Lucio, Sebastian, Emir, Benjamin, Keila y Ainsworth.

---

## 1. Diagrama de Arquitectura Global del Sistema (3 Nodos)

```mermaid
graph TB
    subgraph NODO1 ["1. ESTACIÓN TERRENA (PC WINDOWS)"]
        UI["Interfaz HMI de Pilotaje\n(Python Tkinter / Rust egui)"]
        KB["Entrada de Teclado (WASD)\no Sliders de Calibración"]
        PORT_PC["Puerto USB COM Virtual\n(115200 bps, 8-N-1)"]
        KB --> UI
        UI -->|"Trama de Texto CSV\n'CMD,PotIzq,PotDer,S1,S2,S3,S4\\n'"| PORT_PC
    end

    subgraph NODO2 ["2. DONGLE TRANSMISOR (TX)"]
        PORT_TX["Puerto USB CDC Nativo\nVID:PID 0x2341:0x0070"]
        MCU_TX["Microcontrolador Transmisor\nArduino Nano ESP32 (ESP32-S3)\no ESP32-C3 SuperMini"]
        LED_TX["LED RGB de Estado\n(Verde = TX OK, Rojo = Error)"]
        RF_TX["Transceptor RF NRF24L01+\n(Alimentación 3.3V + Capacitor)"]
        
        PORT_PC ==>|"Cable USB Físico"| PORT_TX
        PORT_TX --> MCU_TX
        MCU_TX --> LED_TX
        MCU_TX -->|"Bus SPI Hardware\n(D11 MOSI, D12 MISO, D13 SCK)"| RF_TX
    end

    subgraph NODO3 ["3. ROVER RECEPTOR A BORDO (RX)"]
        RF_RX["Transceptor RF NRF24L01+\n(Alimentación 3.3V + Capacitor)"]
        MCU_RX["Microcontrolador Ejecutor\nArduino Nano ESP32 (ESP32-S3)\no Arduino MKR 1310"]
        WATCHDOG["Watchdog Failsafe\n(Timeout 1000 ms)"]
        HBRIDGE["Puente H L9110S (HG7881)\nControl Bidireccional PWM"]
        MOTORS["6 Motores DC Tracción (6x6)\nM1, M2, M3 (Izq) | M4, M5, M6 (Der)"]
        SERVOS["4 Servomotores de Dirección (4WS)\nS1 (FL), S2 (FR), S3 (RL), S4 (RR)"]
        
        RF_TX -.->|"Radiofrecuencia 2.508 GHz (Canal 108)\nTrama Binaria PaqueteControl (8 bytes)\nStreaming Continuo a 250 kbps"| RF_RX
        RF_RX -->|"Bus SPI Hardware"| MCU_RX
        MCU_RX --- WATCHDOG
        MCU_RX -->|"PWM Pines D2, D5 (Izq)\nPWM Pines D3, D4 (Der)"| HBRIDGE
        HBRIDGE ==> MOTORS
        MCU_RX -->|"Pulsos 50 Hz (Pines D6, D7, D8, A0)\n[10° a 170°]"| SERVOS
    end

    style NODO1 fill:#1e293b,stroke:#38bdf8,stroke-width:2px,color:#fff
    style NODO2 fill:#0f172a,stroke:#34d399,stroke-width:2px,color:#fff
    style NODO3 fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#fff
```

---

## 2. Diagrama de Secuencia End-to-End: Presionar la Tecla 'W'

Este diagrama ilustra cronológicamente cada milisegundo desde que el dedo del usuario presiona la tecla **W** hasta el giro físico de las 6 ruedas:

```mermaid
sequenceDiagram
    autonumber
    actor Operador as Operador (PC)
    participant HMI as HMI Python (Tkinter)
    participant USB as Puerto Serie USB (COM)
    participant TX as Arduino Nano ESP32 (TX)
    participant RF as Enlace RF 2.508 GHz
    participant RX as Arduino Nano ESP32 (RX)
    participant Hardware as Pines Físicos / Actuadores

    Operador->>HMI: Presiona tecla 'W'
    Note over HMI: 1. Anti-rebote (teclas_presionadas['w'] = True)<br/>2. Calcula trims (Izq=150, Der=150)<br/>3. Centra servos (S1..S4 = 90°)
    HMI->>USB: Escribe: "W,150,150,90,90,90,90\n" (115200 bps)
    USB->>TX: Llega al bufferSerial no bloqueante
    Note over TX: 1. strtok_r() extrae tokens<br/>2. Empaqueta PaqueteControl (8 bytes)<br/>3. Dispara pulso LED verde (30 ms)
    TX->>RF: radio.write(&datosControl, 8 bytes) por SPI
    RF-->>RX: Señal GFSK canal 108 recibida por antena
    Note over RX: 1. radio.available() == true<br/>2. while(radio.available()) vacía FIFO<br/>3. Reinicia timer: ultimaRecepcion = millis()
    RX->>Hardware: Activa pines PWM y servos
    Note over Hardware: - Pin D2 (A1A): PWM 150 (Avance Izq)<br/>- Pin D5 (A1B): 0V (LOW)<br/>- Pin D3 (B1A): PWM 150 (Avance Der)<br/>- Pin D4 (B1B): 0V (LOW)<br/>- Pines D6, D7, D8, A0: Pulsos 1.5 ms (90°)
    Note over Hardware: ¡Las 6 ruedas avanzan y los 4 servos quedan rectos!

    Operador->>HMI: Suelta la tecla 'W'
    HMI->>USB: Escribe: "STOP,0,0,90,90,90,90\n"
    USB->>TX: Parseo de STOP
    TX->>RF: Envía Paquete con traccion = 0
    RF-->>RX: Trama de parada recibida
    RX->>Hardware: pararMotores() -> Pines D2, D5, D3, D4 a 0V
    Note over Hardware: Frenado instantáneo de los 6 motores
```

---

## 3. Diagrama de Secuencia: Watchdog Failsafe por Pérdida de Señal

Muestra qué sucede si se corta la comunicación por radio (interferencia, distancia o apagado del emisor):

```mermaid
sequenceDiagram
    participant TX as Transmisor (TX)
    participant Radio as Canal RF 2.508 GHz
    participant RX as Receptor Rover (RX)
    participant Motores as Motores DC (Ruedas)

    TX->>Radio: Trama periódica t = 0 ms
    Radio->>RX: Paquete recibido OK -> actualiza ultimaRecepcion = millis()
    RX->>Motores: Tracción activa (PWM = 150)

    Note over Radio: ¡SE PIERDE LA SEÑAL DE RADIO!<br/>(Desconexión, obstáculo o apagado)

    Note over RX: t = 200 ms: radio.available() es FALSE
    Note over RX: t = 600 ms: radio.available() es FALSE
    Note over RX: t = 1000 ms: (millis() - ultimaRecepcion > 1000)

    RX->>Motores: ¡DISPARO DE FAILSAFE! pararMotores()
    Note over Motores: Pines D2=0, D5=0, D3=0, D4=0<br/>¡El Rover se clava en el lugar de forma segura!
```

---

## 4. Mapa Visual del Pinout Físico: Arduino Nano ESP32

Diagrama esquemático en arte ASCII de la placa oficial **Arduino Nano ESP32** (ESP32-S3 a 3.3V) a bordo del Rover:

```text
                               ARDUINO NANO ESP32
                                  +-----------+
                                  |   [USB]   |
               (RF24 SCK)  D13 [  ] |           | [  ] D12  (RF24 MISO)
             (RF24 VCC)   3.3V [  ] |           | [  ] D11  (RF24 MOSI)
              (DISPONIBLE) AREF [  ] |           | [  ] D10  (RF24 CSN)
              (Servo 4 S4)   A0 [  ] |           | [  ] D9   (RF24 CE)
       *LIBRE* (Sensor ADC)  A1 [  ] |           | [  ] D8   (Servo 3 S3)
       *LIBRE* (Sensor ADC)  A2 [  ] |           | [  ] D7   (Servo 2 S2)
       *LIBRE* (Sensor ADC)  A3 [  ] |           | [  ] D6   (Servo 1 S1)
        *LIBRE* (I2C SDA)   A4 [  ] |           | [  ] D5   (L9110S A1B - Izq Rev)
        *LIBRE* (I2C SCL)   A5 [  ] |           | [  ] D4   (L9110S B1B - Der Rev)
             *LIBRE* (ADC)  A6 [  ] |           | [  ] D3   (L9110S B1A - Der Av)
             *LIBRE* (ADC)  A7 [  ] |           | [  ] D2   (L9110S A1A - Izq Av)
                 (5V USB)  VBUS [  ] |           | [  ] GND  ------> MASA COMÚN
                               RST [  ] |           | [  ] RST
                 MASA COMÚN   GND [  ] |           | [  ] D0   (RX0 / *LIBRE UART*)
    (Entrada 6V-21V Batería)  VIN [  ] |           | [  ] D1   (TX0 / *LIBRE UART*)
                                  +-----------+
```

### Código de Colores Funcional:
* **Líneas de Radio NRF24L01+ (Bus SPI):** Pines `D9`, `D10`, `D11`, `D12`, `D13` y `3.3V`.
* **Líneas del Puente H L9110S (Motores):** Pines `D2`, `D3`, `D4`, `D5`.
* **Líneas de los Servomotores (Dirección):** Pines `D6` (S1), `D7` (S2), `D8` (S3), `A0` (S4).
* **Pines Libres para Sensores de Misión:**
  * `A4` y `A5`: Giroscopio / IMU por I2C (crucial para rampa de 20°).
  * `A1`: Medición de voltaje de batería (divisor resistivo).
  * `D0` y `D1`: Puerto serie para módulo de visión ESP32-CAM.

---

## 5. Esquema de Alimentación y Buses de Potencia Aislados

```mermaid
graph TD
    subgraph BATERIA_CENTRAL ["FUENTE DE ENERGÍA PRINCIPAL"]
        BATT["Batería LiPo 2S (7.4V - 8.4V)"]
    end

    subgraph ETAPA_MOTORES ["BUS DE POTENCIA 1: TRACCIÓN 6x6"]
        BATT ==>|"Tensión directa (7.4V)"| VCC_MOTORES["VCC Motor Puente H L9110S"]
        VCC_MOTORES ==> M1["Motores Izquierdos M1, M2, M3"]
        VCC_MOTORES ==> M2["Motores Derechos M4, M5, M6"]
    end

    subgraph ETAPA_SERVOS ["BUS DE POTENCIA 2: DIRECCIÓN 4WS"]
        STEPDOWN["Regulador Conmutado Step-Down Buck\n(Salida fija 5.0V - 6.0V / 3A)\n¡Prohibido regulador lineal LM7805!"]
        BATT ==>|"Entrada 7.4V"| STEPDOWN
        STEPDOWN ==>|"Línea aislada 5V-6V"| VCC_SERVOS["VCC Servomotores"]
        VCC_SERVOS --> S1["Servo S1 (FL)"]
        VCC_SERVOS --> S2["Servo S2 (FR)"]
        VCC_SERVOS --> S3["Servo S3 (RL)"]
        VCC_SERVOS --> S4["Servo S4 (RR)"]
    end

    subgraph ETAPA_LOGICA ["BUS DE POTENCIA 3: MICROCONTROLADOR Y RADIO"]
        BATT ==>|"Entrada VIN (Tolera hasta 21V)"| MCU_VIN["VIN Arduino Nano ESP32"]
        REG_NANO["Regulador interno 3.3V de la placa"]
        MCU_VIN --> REG_NANO
        REG_NANO ==>|"3.3V Estabilizado"| RF_VCC["VCC Módulo NRF24L01+\n(¡NUNCA 5V!)"]
        CAP["Capacitor Electrolítico 10-100 µF\nsoldado entre VCC y GND"]
        RF_VCC --- CAP
    end

    GND_COMUN["MASA COMÚN UNIFICADA (GND)\nTodos los negativos interconectados para cerrar el circuito lógico"]
    BATT -.-> GND_COMUN
    STEPDOWN -.-> GND_COMUN
    HBRIDGE -.-> GND_COMUN
    SERVOS -.-> GND_COMUN
    MCU_RX -.-> GND_COMUN
    RF_RX -.-> GND_COMUN

    style BATERIA_CENTRAL fill:#1e293b,stroke:#f59e0b,stroke-width:2px,color:#fff
    style ETAPA_MOTORES fill:#450a0a,stroke:#ef4444,stroke-width:2px,color:#fff
    style ETAPA_SERVOS fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
    style ETAPA_LOGICA fill:#172554,stroke:#3b82f6,stroke-width:2px,color:#fff
    style GND_COMUN fill:#0f172a,stroke:#e2e8f0,stroke-width:3px,color:#fbbf24
```

---

## 6. Cinemática del Chasis Rocker-Bogie: Modos de Conducción

A continuación se muestra cómo se orientan físicamente las ruedas en los distintos modos de operación:

```text
===================================================================================
1. AVANCE RECTO (TECLA W)
   Todos los servos a 90° (neutro). Motores giran en sentido positivo.
   
        [S1: 90°] | M1 |                | M4 | [S2: 90°]
                         \            /
                  | M2 |  ====[CHASIS]====  | M5 |   (Ruedas centrales fijas)
                         /            \
        [S3: 90°] | M3 |                | M6 | [S4: 90°]
        
===================================================================================
2. CURVA ACKERMANN A LA IZQUIERDA (TECLA A)
   Delanteras a 120° (abiertas hacia afuera), Traseras a 60° (coordinadas).
   
        [S1: 120°] \ M1 \               \ M4 \ [S2: 120°]
                          \           /
                   | M2 |  ===[CHASIS]===  | M5 |
                          /           \
        [S3: 60°]  / M3 /               / M6 / [S4: 60°]
        
===================================================================================
3. GIRO EN EL LUGAR / POINT TURN 360° (TECLAS Q / E)
   Las 4 esquinas se orientan a 45° tangenciales a la circunferencia del chasis.
   Motores izquierdos giran en reversa (-150) y derechos en avance (+150).
   
        [S1: 45°]  / M1 /               \ M4 \ [S2: 135°]
                          \           /
                   | M2 |  ===[CHASIS]===  | M5 |
                          /           \
        [S3: 135°] \ M3 \               / M6 / [S4: 45°]
        
===================================================================================
4. MODO CANGREJO / CRAB DRIVE (AVANCE DIAGONAL LATERAL)
   Las 4 ruedas giran exactamente en el mismo ángulo paralelo. El chasis no rota.
   
        [S1: 135°] \ M1 \               \ M4 \ [S2: 135°]
                          \           /
                   | M2 |  ===[CHASIS]===  | M5 |
                          /           \
        [S3: 135°] \ M3 \               \ M6 \ [S4: 135°]
===================================================================================
```

---

## 7. Ficha Técnica Comparativa: Canales de Comunicación

| Parámetro | Cable USB Serie (PC $\rightarrow$ TX) | Radio NRF24L01+ (TX $\rightarrow$ RX) | Wi-Fi SoftAP (Cámara ESP32-CAM) |
|---|---|---|---|
| **Medio Físico** | Cable de cobre USB | Ondas electromagnéticas RF | Ondas electromagnéticas Wi-Fi |
| **Frecuencia / Canal** | Banda base USB | **Canal 108 (2.508 GHz)** | Canal 1 o 6 (2.412 - 2.437 GHz) |
| **Formato de Datos** | Texto ASCII CSV | **Binario empaquetado (8 bytes)** | HTTP / Streams MJPEG / TCP |
| **Tasa de Datos** | 115200 bps | 250 kbps | Hasta 54 Mbps (802.11g) |
| **Latencia Típica** | $< 1\,\text{ms}$ | **$< 2\,\text{ms}$** | $80\,\text{ms} - 250\,\text{ms}$ |
| **Sensibilidad a Interferencias** | Nula (apantallado) | **Inmune** (opera fuera de Wi-Fi) | Alta (comparte banda comercial) |
| **Función en el Rover** | Consola y pilotaje desde PC | **Tracción y dirección crítica** | **Video y telemetría de imagen** |

---

## 8. Tarjetas Resumen de Respuesta Rápida (Cheat-Sheet para Exposición)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ TEMA: ¿CÓMO VIAJA LA INFORMACIÓN?                                                │
│ 1. Usuario aprieta W en la PC.                                                  │
│ 2. HMI Python envía por cable USB: "W,150,150,90,90,90,90\n" a 115200 bps.     │
│ 3. Arduino transmisor extrae datos y arma un paquete binario de 8 bytes.        │
│ 4. Radio NRF24L01 transmite en 2.508 GHz (Canal 108) a 250 kbps.                │
│ 5. Arduino receptor a bordo recibe la trama y vacía la cola FIFO.               │
│ 6. Aplica PWM a Pines D2 y D3 (Puente H L9110S) y pulsos a Pines D6..A0 (Servos)│
│ 7. Ruedas avanzan. Si se corta la señal por 1 segundo, el Rover frena solo.     │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ TEMA: ¿POR QUÉ NO SE USA WI-FI PARA EL MOVIMIENTO?                              │
│ - El Wi-Fi tiene latencia variable (jitter) y si hay congestión genera retardo. │
│ - Si se pierde un paquete TCP, el sistema se congela esperando retransmisión.   │
│ - NRF24L01 en Canal 108 (2.508 GHz) está FUERA de las frecuencias Wi-Fi comunes.│
│ - El Wi-Fi SÍ se usa, pero exclusivamente para la cámara ESP32-CAM en modo      │
│   SoftAP (Access Point en IP 192.168.4.1 con socket de video en puerto 81).     │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ TEMA: REGLAS DE ORO DE HARDWARE (LECCIONES APRENDIDAS EN CEPIT)                 │
│ 1. NRF24L01 NUNCA a 5V: siempre a 3.3V con capacitor de 10-100 µF soldado.       │
│ 2. Servos alimentados con Step-Down conmutado (5V-6V). Prohibido LM7805.        │
│ 3. Límites por software en servos: constrain entre 10° y 170° para no romper piñón│
│ 4. Toda la lógica de control es no bloqueante (cero delays, todo con millis()). │
└─────────────────────────────────────────────────────────────────────────────────┘
```
