# EVALUACIÓN TÉCNICA: MICROPYTHON, ESTANDARIZACIÓN Y ARDUINO UNO Q

> **DOCUMENTO DE ANÁLISIS ESTRATÉGICO — ROVER LUNAR V2.0**  
> Equipo de Desarrollo CEPIT | Evaluación de tecnologías de software embebido y futuros reemplazos para el subsistema de procesamiento a bordo.

---

## 1. MicroPython en Arduino Nano ESP32: ¿Conviene para este Proyecto?

El **Arduino Nano ESP32** soporta oficialmente tanto **C/C++ (Arduino IDE)** como **MicroPython**.

### 1.1. ¿De qué sirve MicroPython?
* **Consola Interactiva (REPL):** Permite escribir comandos en vivo para accionar motores o servos sin tener que compilar y flashear el microcontrolador.
* **Sintaxis idéntica a la HMI de PC:** Facilita la curva de aprendizaje a programadores de Python.

### 1.2. Limitaciones Críticas para el Rover (Por qué C/C++ es Superior):
* **Determinismo y Latencia (Garbage Collector):** MicroPython utiliza un recolector de basura periódico en RAM. Estas pausas aleatorias introducen fluctuaciones (*jitter*) en la generación de PWM y en la lectura analógica de los sticks. C/C++ garantiza **tiempo real estricto**.
* **Rendimiento con Radiofrecuencia NRF24L01+:** La biblioteca `RF24` en C++ está optimizada por hardware mediante registros SPI directos. Los drivers de NRF24 para MicroPython consumen más CPU y tienen riesgo de desborde de búfer ante streaming de 50 Hz.
* **Manejo de Paquetes Binarios Empaquetados:** En C++, la estructura `PaqueteControl` de **8 bytes exactos** se mapea directo en memoria física sin sobrecarga (`__attribute__((packed))`). En MicroPython se requiere serialización manual mediante `struct.pack()`.

> **Veredicto:** Para tareas de radiocontrol continuo, cinemática de tracción y seguridad contra pérdida de enlace, **C/C++ (Arduino framework) es la opción técnicamente correcta y confiable**.

---

## 2. Estandarización de "Todo en Arduino"

Adoptar una arquitectura homogénea dentro del ecosistema moderno de Arduino aporta ventajas directas:

1. **Unificación a 3.3V Nativo:**  
   Al emplear placas modernas (como el **Nano ESP32** en el mando y un reemplazo moderno en el rover), todo el bus SPI, I2C y GPIO opera a 3.3V, eliminando divisores resistivos y protegiendo el NRF24L01 de sobretensiones de 5V.
2. **Librería y Cabecera de Red Compartida (`ProtocoloRover.h`):**  
   Permite compartir un único archivo `.h` entre el mando y el rover con la definición exacta de estructuras, constantes RF (Canal 108 @ 250 kbps) y macros cinemáticas.
3. **Herramientas Nativas de Calibración:**  
   Uso del **Serial Plotter** del Arduino IDE para sintonizar zonas muertas (*deadbands*) de sticks y futurs lazos PID con encoders de efecto Hall.

---

## 3. Análisis Técnico: Arduino UNO Q como Reemplazo del MKR 1310

El **Arduino MKR WAN 1310** actual cuenta con un módulo LoRaWAN que encarece la placa y no se utiliza (el proyecto requiere el enlace NRF24L01 de 2.4 GHz de baja latencia). El **Arduino UNO Q** surge como una alternativa de nueva generación.

### 3.1. ¿Qué es el Arduino UNO Q?
Desarrollado en colaboración entre **Arduino y Qualcomm**, es una placa híbrida tipo **SBC (Single Board Computer)** con arquitectura de **"doble cerebro"**:

```text
+-----------------------------------------------------------------------------------+
|                            ARDUINO UNO Q (DUAL-BRAIN)                             |
|                                                                                   |
|  [ CEREBRO DE ALTO NIVEL - LINUX ]          [ CEREBRO EN TIEMPO REAL - MCU ]      |
|  Qualcomm Dragonwing QRB2210                STM32U585                             |
|  - Quad-Core ARM Cortex-A53 @ 2.0 GHz       - ARM Cortex-M33 @ 160 MHz            |
|  - Sistema Operativo: Debian Linux          - Sistema: Zephyr OS / Arduino RTOS   |
|  - Visión Artificial (OpenCV / AI Edge)     - Generación de PWM para 6 Motores    |
|  - Servidor Web / Video Streaming / ROS2    - Control de Servos S1-S4 (10°-170°)  |
|  - Conexión Cámara USB / MIPI               - Radio NRF24L01 y Watchdog Failsafe  |
|                         \                       /                                 |
|                          <--- RPC Bridge Bus --->                                 |
+-----------------------------------------------------------------------------------+
```

---

### 3.2. Beneficios para el Rover Lunar V2.0

1. **Visión Artificial y Autonomía a Bordo (Sin ESP32-CAM externo):**  
   Su CPU Qualcomm de 2.0 GHz con Linux permite conectar cámaras USB/MIPI y correr **OpenCV** para detección de rocas, seguimiento visual de terreno y navegación autónoma directamente en el chasis.
2. **Separación de Seguridad por Hardware:**  
   Si Linux se sobrecarga procesando imágenes, el microcontrolador **STM32 Cortex-M33 sigue operando motores, radio y el failsafe de parada en microsegundos sin colgarse**.
3. **Soporte Nativo para ROS2 (Robot Operating System):**  
   Permite implementar algoritmos estándar de la industria espacial para odometría, SLAM (mapeo simultáneo y localización) y cinemática inversa avanzada.
4. **Servidor de Video en Tiempo Real:**  
   Capacidad de transmitir video HD vía Wi-Fi hacia la estación terrena directamente desde Linux, reservando la radio NRF24L01 exclusivamente para el canal de teleoperación.

---

### 3.3. Desafíos Técnicos a Considerar

* **Consumo Energético Elevado:** Pasa de ~100 mA (MKR 1310) a **1.0 A – 2.5 A a 5V**. Requiere un regulador Step-Down Buck dedicado (mínimo 5V / 3A a 5A) para no apagarse ante picos de aceleración de los motores.
* **Tiempo de Arranque (Boot Time):** Tarda entre **15 y 30 segundos** en iniciar Debian Linux (a diferencia del arranque casi instantáneo de 0.05 s de un microcontrolador tradicional).
* **Nivel Lógico:** Todos sus pines son de **3.3V estricto** (no tolera 5V en entradas).
* **Curva de Aprendizaje:** Requiere familiarizarse con la suite *Arduino App Lab* y la comunicación inter-procesador mediante RPC Bridge.

---

## 4. Cuadro Comparativo de Alternativas de Reemplazo

| Característica | Arduino MKR 1310 (Actual) | Arduino UNO Q | Arduino UNO R4 WiFi | Arduino GIGA R1 WiFi |
|---|---|---|---|---|
| **Arquitectura** | SAMD21 (Cortex-M0+) | **Quad-Core A53 (Linux) + STM32 M33** | Renesas RA4M1 (M4) + ESP32-S3 | Dual Core Cortex-M7 + M4 |
| **Frecuencia Reloj** | 48 MHz | **2.0 GHz + 160 MHz** | 48 MHz + 240 MHz | 480 MHz + 240 MHz |
| **¿Capaz de Visión Artificial?** | No | **Sí (OpenCV, Detección IA)** | No | Sí (Básica con ArduCam) |
| **Consumo Corriente** | ~100 mA (Muy bajo) | **1000 - 2500 mA (Alto)** | ~150 mA (Bajo) | ~300 mA (Medio) |
| **Tiempo de Arranque** | < 0.1 s (Instantáneo) | **15 - 30 s (Linux)** | < 0.1 s (Instantáneo) | < 0.1 s (Instantáneo) |
| **Complejidad de Código**| Baja | **Media - Alta** | Baja (Sketch estándar) | Media |
| **Aplicación Recomendada**| Telemetría LoRa (No usada) | **Misión con IA, SLAM y Video HD** | **Control de Motores / Tracción simple** | **Robótica avanzada en tiempo real** |

---

## 5. Recomendación para el Equipo

1. **Corto Plazo (Ensayos en rampa de 20° y piso CEPIT):**  
   Mantener el código optimizado del **Arduino MKR 1310**, ya que está probado, vacía búferes de radio a alta tasa y cuenta con watchdog de seguridad.
2. **Si el objetivo futuro es Misión con Visión Artificial y Mapeo:**  
   El **Arduino UNO Q** es la plataforma ideal para dar el salto hacia un rover de exploración autónomo inteligente.
3. **Si el objetivo futuro es solo abaratar y simplificar sin LoRa:**  
   El **Arduino UNO R4 WiFi** o el **Arduino Nano ESP32** son reemplazos directos más livianos, económicos y con consumo de batería mínimo.
